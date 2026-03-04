"""GIF recorder — capture multi-step browser interactions as animated GIFs."""

from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, ImageFilter
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from .capture import (
    _navigate_with_layered_wait,
    smart_fill,
    _check_login_success,
    PII_DETECTION_JS,
)

MAX_FRAMES = 30


def _blur_pii_on_image(
    img: Image.Image, pii_regions: list[dict], blur_radius: int = 20
) -> Image.Image:
    """Apply Gaussian blur to PII regions on an in-memory Pillow Image."""
    if not pii_regions:
        return img
    if img.mode != "RGB":
        img = img.convert("RGB")

    img_w, img_h = img.size
    for region in pii_regions:
        x = max(0, int(region.get("x", 0)))
        y = max(0, int(region.get("y", 0)))
        w = int(region.get("width", 0))
        h = int(region.get("height", 0))
        x2 = min(img_w, x + w)
        y2 = min(img_h, y + h)
        if x2 <= x or y2 <= y:
            continue
        cropped = img.crop((x, y, x2, y2))
        blurred = cropped.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        img.paste(blurred, (x, y))
    return img


def _execute_step(page, step: dict, app_url: str) -> None:
    """Execute a single interaction step on the page.

    Supported actions:
      - navigate: go to step["target"] (relative path or full URL)
      - click: click the element matching step["target"] CSS selector
      - type: type step["value"] into the element matching step["target"]
      - scroll: scroll by step["value"] pixels (positive = down)
      - wait: wait for step["value"] milliseconds
      - hover: hover over the element matching step["target"]
    """
    action = step["action"]
    target = step.get("target", "")
    value = step.get("value", "")
    wait_after = step.get("wait_after", 500)

    if action == "navigate":
        if target.startswith("http"):
            url = target
        else:
            url = f"{app_url.rstrip('/')}{target}"
        _navigate_with_layered_wait(page, url)

    elif action == "click":
        locator = page.locator(target).first
        locator.wait_for(timeout=5000)
        locator.click()

    elif action == "type":
        locator = page.locator(target).first
        locator.wait_for(timeout=5000)
        locator.fill(str(value))

    elif action == "scroll":
        try:
            pixels = int(value) if value else 300
        except (ValueError, TypeError):
            pixels = 300
        page.evaluate(f"window.scrollBy(0, {pixels})")

    elif action == "wait":
        ms = int(value) if value else 1000
        page.wait_for_timeout(ms)

    elif action == "hover":
        locator = page.locator(target).first
        locator.wait_for(timeout=5000)
        locator.hover()

    # Post-action wait for visual settling
    if action != "wait" and wait_after > 0:
        page.wait_for_timeout(wait_after)


def record_gif(
    steps: list[dict],
    app_url: str,
    auth_config: Optional[dict] = None,
    output_dir: str = ".",
    label: str = "recording",
    frame_duration_ms: int = 2500,
    width: int = 1280,
    height: int = 720,
    blur_pii: bool = True,
) -> dict:
    """Record a multi-step browser interaction as an animated GIF.

    Each step dict must contain:
      - action: str — one of: navigate, click, type, scroll, wait, hover
      - target: str (optional) — CSS selector or URL path
      - value: str (optional) — text to type, scroll pixels, or wait ms
      - wait_after: int (optional) — ms to wait after action (default 500)

    Args:
      frame_duration_ms: How long each frame displays in the GIF (default 2500ms / 2.5s).

    Returns dict with {status, gif_path, frame_count, duration_seconds, file_size_bytes}.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    gif_path = output_path / f"{label}.gif"

    # Cap steps to MAX_FRAMES
    capped_steps = steps[:MAX_FRAMES]
    frames: list[Image.Image] = []
    failed_steps: list[int] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": width, "height": height})
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
            except Exception:
                pass

        for step_idx, step in enumerate(capped_steps):
            try:
                _execute_step(page, step, app_url)
            except Exception:
                failed_steps.append(step_idx)

            # Capture viewport screenshot as frame
            try:
                screenshot_bytes = page.screenshot()
                img = Image.open(BytesIO(screenshot_bytes))
                if img.mode != "RGB":
                    img = img.convert("RGB")
                # Resize to target dimensions if needed
                if img.size != (width, height):
                    img = img.resize((width, height), Image.LANCZOS)

                # PII blur per frame
                if blur_pii:
                    try:
                        pii_regions = page.evaluate(PII_DETECTION_JS)
                        if pii_regions:
                            img = _blur_pii_on_image(img, pii_regions)
                    except Exception:
                        pass

                frames.append(img)
            except Exception:
                pass

        browser.close()

    if not frames:
        return {
            "status": "error",
            "message": "No frames captured",
            "gif_path": "",
            "frame_count": 0,
            "duration_seconds": 0,
            "file_size_bytes": 0,
        }

    # Quantize frames for GIF palette (256 colors max)
    quantized = [f.quantize(colors=256, method=Image.Quantize.MEDIANCUT) for f in frames]

    # Assemble GIF
    quantized[0].save(
        gif_path,
        save_all=True,
        append_images=quantized[1:],
        duration=frame_duration_ms,
        loop=0,
        optimize=True,
    )

    duration_seconds = round(len(frames) * frame_duration_ms / 1000, 2)
    file_size = gif_path.stat().st_size

    result: dict = {
        "status": "ok",
        "gif_path": str(gif_path),
        "frame_count": len(frames),
        "duration_seconds": duration_seconds,
        "file_size_bytes": file_size,
    }

    warnings: list[str] = []
    if failed_steps:
        warnings.append(f"Steps {failed_steps} failed during recording.")
    if file_size > 10_000_000:
        warnings.append(
            f"GIF is large ({file_size // 1_000_000}MB). "
            "Consider reducing fps or dimensions."
        )
    if warnings:
        result["warnings"] = warnings

    return result
