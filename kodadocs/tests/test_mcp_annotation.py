import json
from pathlib import Path
from PIL import Image
from kodadocs.mcp.tools.annotation import annotate_screenshots_tool


def _create_test_screenshot(path: Path, width=1280, height=720):
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    img.save(path)


def test_annotate_empty_elements(tmp_path):
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    _create_test_screenshot(screenshots_dir / "index.png")
    result = annotate_screenshots_tool(
        screenshots_dir=str(screenshots_dir),
        dom_elements={},
        brand_color="#3e8fb0",
    )
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert parsed["annotated"] == {}


def test_annotate_with_elements(tmp_path):
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    _create_test_screenshot(screenshots_dir / "dashboard.png")
    elements = {
        "/dashboard": [
            {
                "role": "button",
                "name": "Save",
                "bounds": {"x": 100, "y": 200, "width": 80, "height": 30},
            },
            {
                "role": "link",
                "name": "Settings",
                "bounds": {"x": 300, "y": 50, "width": 100, "height": 20},
            },
        ]
    }
    result = annotate_screenshots_tool(
        screenshots_dir=str(screenshots_dir),
        dom_elements=elements,
        brand_color="#ff0000",
    )
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert "/dashboard" in parsed["annotated"]
    assert Path(parsed["annotated"]["/dashboard"]).exists()


def test_annotate_missing_screenshot(tmp_path):
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    elements = {
        "/missing": [
            {
                "role": "button",
                "name": "Click",
                "bounds": {"x": 10, "y": 10, "width": 50, "height": 20},
            },
        ]
    }
    result = annotate_screenshots_tool(
        screenshots_dir=str(screenshots_dir),
        dom_elements=elements,
        brand_color="#3e8fb0",
    )
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert parsed["annotated"] == {}
