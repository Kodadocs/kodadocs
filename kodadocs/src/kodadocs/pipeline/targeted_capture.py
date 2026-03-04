"""Targeted element capture — screenshot specific CSS selectors or clipped regions."""

from pathlib import Path
from typing import Optional

from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from rich.console import Console

from .capture import (
    _navigate_with_layered_wait,
    smart_fill,
    _check_login_success,
    PII_DETECTION_JS,
)
from .annotation import blur_pii_regions


def _apply_padding(image: Image.Image, padding: int) -> Image.Image:
    """Expand canvas with white border of `padding` pixels on all sides."""
    if padding <= 0:
        return image
    new_w = image.width + 2 * padding
    new_h = image.height + 2 * padding
    padded = Image.new("RGB", (new_w, new_h), (255, 255, 255))
    padded.paste(image, (padding, padding))
    return padded


def _offset_pii_regions(
    pii_regions: list[dict],
    viewport_box: dict,
    padding: int,
) -> list[dict]:
    """Translate page-level PII coordinates to element-local coordinates.

    Only returns regions that overlap with the captured viewport_box.
    Coordinates are shifted so (0, 0) is the top-left of the captured element,
    then offset by padding to match the padded canvas.
    """
    vx, vy = viewport_box["x"], viewport_box["y"]
    vw, vh = viewport_box["width"], viewport_box["height"]

    result = []
    for region in pii_regions:
        rx = region.get("x", 0)
        ry = region.get("y", 0)
        rw = region.get("width", 0)
        rh = region.get("height", 0)

        # Check overlap with viewport box
        if rx + rw <= vx or rx >= vx + vw:
            continue
        if ry + rh <= vy or ry >= vy + vh:
            continue

        # Translate to element-local + padding offset
        local_x = max(0, rx - vx) + padding
        local_y = max(0, ry - vy) + padding
        local_w = min(rx + rw, vx + vw) - max(rx, vx)
        local_h = min(ry + rh, vy + vh) - max(ry, vy)

        if local_w > 0 and local_h > 0:
            result.append({
                "x": local_x,
                "y": local_y,
                "width": local_w,
                "height": local_h,
            })
    return result


def capture_targeted(
    targets: list[dict],
    app_url: str,
    auth_config: Optional[dict] = None,
    output_dir: str = ".",
    blur_pii: bool = True,
) -> dict:
    """Capture targeted screenshots of specific elements or clipped regions.

    Each target dict must contain:
      - route: str — the URL path to navigate to
      - label: str — a unique label for the output file
      - selector: str (optional) — CSS selector to screenshot
      - clip: dict (optional) — {x, y, width, height} region to clip
      - padding: int (optional) — pixels of white padding around the capture

    Returns dict with {status, targeted_screenshots: {label: path}}.
    """
    console = Console()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results: dict[str, str] = {}

    # Group targets by route to avoid redundant navigations
    route_groups: dict[str, list[dict]] = {}
    for target in targets:
        route = target["route"]
        route_groups.setdefault(route, []).append(target)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        # Authenticate if needed
        if auth_config and auth_config.get("auth_url"):
            try:
                _navigate_with_layered_wait(page, auth_config["auth_url"], timeout=60000)
                if auth_config.get("username") and auth_config.get("password"):
                    smart_fill(page, auth_config["username"], ["username", "email", "login", "user"])
                    smart_fill(page, auth_config["password"], ["password", "pass"])
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(3000)
                    _check_login_success(page, auth_config["auth_url"])
            except Exception as e:
                console.print(f"[yellow]Auth failed, continuing without login: {e}[/yellow]")

        for route, route_targets in route_groups.items():
            target_url = f"{app_url.rstrip('/')}{route}"
            try:
                _navigate_with_layered_wait(page, target_url)
            except Exception:
                for t in route_targets:
                    results[t["label"]] = ""
                continue

            # Detect PII regions once per route if blur is enabled
            pii_regions: list[dict] = []
            if blur_pii:
                try:
                    pii_regions = page.evaluate(PII_DETECTION_JS)
                except Exception:
                    pass

            for target in route_targets:
                label = target["label"]
                selector = target.get("selector")
                clip = target.get("clip")
                padding = target.get("padding", 0)

                image_path = output_path / f"{label}.png"

                try:
                    if selector:
                        # Selector-based capture
                        locator = page.locator(selector).first
                        locator.wait_for(timeout=5000)
                        screenshot_bytes = locator.screenshot()
                        image_path.write_bytes(screenshot_bytes)

                        # Get bounding box for PII offset calculation
                        bbox = locator.bounding_box()
                        viewport_box = {
                            "x": bbox["x"] if bbox else 0,
                            "y": bbox["y"] if bbox else 0,
                            "width": bbox["width"] if bbox else 0,
                            "height": bbox["height"] if bbox else 0,
                        }
                    elif clip:
                        # Region-based capture
                        page.screenshot(
                            path=str(image_path),
                            clip={
                                "x": clip["x"],
                                "y": clip["y"],
                                "width": clip["width"],
                                "height": clip["height"],
                            },
                        )
                        viewport_box = clip
                    else:
                        continue

                    # Apply padding
                    if padding > 0:
                        img = Image.open(image_path)
                        img = _apply_padding(img, padding)
                        img.save(image_path)

                    # Apply PII blur
                    if blur_pii and pii_regions:
                        local_pii = _offset_pii_regions(pii_regions, viewport_box, padding)
                        if local_pii:
                            blur_pii_regions(image_path, local_pii, image_path)

                    results[label] = str(image_path)

                except Exception:
                    results[label] = ""

        browser.close()

    failed = [k for k, v in results.items() if not v]
    result = {
        "status": "ok",
        "targeted_screenshots": {k: v for k, v in results.items() if v},
    }
    if failed:
        result["failed"] = failed
    return result
