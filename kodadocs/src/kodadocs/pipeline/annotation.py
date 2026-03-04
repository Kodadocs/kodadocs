import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
from ..models import RunManifest
from rich.console import Console


def extract_elements(dom_data):
    """Extract annotatable elements from DOM data.

    Accepts either:
    - A flat list of elements (new format from page.evaluate)
    - A tree dict with 'children' key (legacy accessibility tree format)
    """
    if not dom_data:
        return []

    # New format: flat list of dicts with role/name/bounds
    if isinstance(dom_data, list):
        return [
            el
            for el in dom_data
            if el.get("name")
            and el.get("bounds")
            and el["bounds"].get("width", 0) > 0
            and el["bounds"].get("height", 0) > 0
        ]

    # Legacy format: accessibility tree with children
    elements = []
    interesting_roles = [
        "button",
        "link",
        "textbox",
        "checkbox",
        "combobox",
        "heading",
        "img",
    ]

    def _walk(node):
        if not node:
            return
        role = node.get("role")
        name = node.get("name")
        bounds = node.get("bounds")
        if role in interesting_roles and bounds and name:
            elements.append({"role": role, "name": name, "bounds": bounds})
        for child in node.get("children", []):
            _walk(child)

    _walk(dom_data)
    return elements


def blur_pii_regions(
    image_path: Path, pii_regions: list, output_path: Path, blur_radius: int = 20
):
    """Apply Gaussian blur to PII-sensitive regions of a screenshot.

    Crops each region, blurs it, and pastes it back. Operates in-place on the
    output image. Regions outside image bounds are clamped silently.
    """
    if not pii_regions:
        return
    if not image_path.exists():
        return

    img = Image.open(image_path)
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

    img.save(output_path)


def annotate_screenshot(
    image_path: Path, elements: list, output_path: Path, brand_color: str = "#3e8fb0"
):
    console = Console()
    if not image_path.exists():
        console.print(f"[red]Error: Screenshot not found at {image_path}[/red]")
        return

    try:
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode != "RGB":
                img = img.convert("RGB")

            draw = ImageDraw.Draw(img)

            # Try to load a font
            try:
                # Common locations for fonts on macOS/Linux
                font_paths = [
                    "/System/Library/Fonts/Cache/Arial.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/Library/Fonts/Arial.ttf",
                ]
                font = None
                for fp in font_paths:
                    if os.path.exists(fp):
                        try:
                            font = ImageFont.truetype(fp, 16)
                            break
                        except Exception:
                            continue
                if not font:
                    font = ImageFont.load_default()
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Font loading failed, using default: {e}[/yellow]"
                )
                font = ImageFont.load_default()

            # Deduplicate elements by name and position to avoid crowding
            seen = set()
            unique_elements = []
            for el in elements:
                key = (el["name"], el["bounds"]["x"], el["bounds"]["y"])
                if key not in seen:
                    unique_elements.append(el)
                    seen.add(key)

            # Limit to top 15 most relevant elements to avoid noise
            unique_elements = unique_elements[:15]

            for i, el in enumerate(unique_elements, 1):
                b = el["bounds"]
                # Draw a small circle with the number
                radius = 12
                center_x = b["x"] + 5  # Offset a bit into the element
                center_y = b["y"] + 5

                # Background circle
                draw.ellipse(
                    [
                        center_x - radius,
                        center_y - radius,
                        center_x + radius,
                        center_y + radius,
                    ],
                    fill=brand_color,
                    outline="white",
                    width=2,
                )

                # Text number
                txt = str(i)
                # Adjust text position based on font
                draw.text((center_x - 4, center_y - 8), txt, fill="white", font=font)

            img.save(output_path)
            return unique_elements

    except Exception as e:
        console.print(f"[red]Error annotating {image_path}: {e}[/red]")
        return []


def annotation_step(manifest: RunManifest):
    console = Console()
    console.print("Running annotation step...")
    project_path = manifest.config.project_path
    brand_color = manifest.config.brand_color or "#3e8fb0"

    annotated_dir = project_path / ".kodadocs" / "screenshots" / "annotated"
    annotated_dir.mkdir(exist_ok=True, parents=True)

    annotated_elements_map = {}

    # PII blur pass — apply before annotation so callouts aren't blurred
    if manifest.config.blur_pii and manifest.pii_regions:
        for route, regions in manifest.pii_regions.items():
            screenshot_rel = manifest.screenshots.get(route)
            if not screenshot_rel or not regions:
                continue
            src_path = project_path / screenshot_rel
            if src_path.exists():
                console.print(
                    f"  Blurring PII in [cyan]{route}[/cyan] ({len(regions)} regions)..."
                )
                blur_pii_regions(src_path, regions, src_path)

    # Iterate over a list of items because we will modify the dictionary during loop
    for route, screenshot_rel_path in list(manifest.screenshots.items()):
        # Only annotate if we have DOM elements for this route
        dom_data = manifest.dom_elements.get(route)
        if not dom_data:
            continue

        elements = extract_elements(dom_data)
        if not elements:
            continue

        src_path = project_path / screenshot_rel_path
        safe_route = route.strip("/").replace("/", "-") or "index"
        dest_path = annotated_dir / f"{safe_route}.png"

        console.print(f"  Annotating [cyan]{route}[/cyan]...")
        placed_elements = annotate_screenshot(
            src_path, elements, dest_path, brand_color
        )

        if placed_elements:
            # Update manifest to use the annotated version if preferred,
            # or just store it for enrichment to know what the numbers mean
            manifest.screenshots[route + "_annotated"] = str(
                dest_path.relative_to(project_path)
            )
            annotated_elements_map[route] = placed_elements

    # Store the flattened/filtered elements back so AI can reference them by number
    manifest.annotated_elements = annotated_elements_map
    console.print("Annotation completed.")
