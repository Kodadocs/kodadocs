import json
from pathlib import Path
from typing import Optional
from kodadocs.pipeline.annotation import (
    annotate_screenshot,
    extract_elements,
    blur_pii_regions,
)


def annotate_screenshots_tool(
    screenshots_dir: str,
    dom_elements: dict,
    brand_color: str = "#3e8fb0",
    pii_regions: Optional[dict] = None,
) -> str:
    """Annotate screenshots with numbered callouts using Pillow."""
    src_dir = Path(screenshots_dir)
    annotated_dir = src_dir / "annotated"
    annotated_dir.mkdir(parents=True, exist_ok=True)

    # Blur PII regions on base screenshots before annotating
    if pii_regions:
        for route, regions in pii_regions.items():
            if not regions:
                continue
            safe_route = route.strip("/").replace("/", "-") or "index"
            src_path = src_dir / f"{safe_route}.png"
            if src_path.exists():
                blur_pii_regions(src_path, regions, src_path)

    annotated = {}

    for route, raw_elements in dom_elements.items():
        elements = extract_elements(raw_elements)
        if not elements:
            continue

        safe_route = route.strip("/").replace("/", "-") or "index"
        src_path = src_dir / f"{safe_route}.png"

        if not src_path.exists():
            continue

        dest_path = annotated_dir / f"{safe_route}.png"
        placed = annotate_screenshot(src_path, elements, dest_path, brand_color)

        if placed:
            annotated[route] = str(dest_path)

    return json.dumps({"status": "ok", "annotated": annotated})
