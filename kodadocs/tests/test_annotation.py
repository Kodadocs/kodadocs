from PIL import Image
from kodadocs.pipeline.annotation import (
    extract_elements,
    annotate_screenshot,
    blur_pii_regions,
)


def test_extract_elements_flat_list():
    elements = [
        {
            "role": "button",
            "name": "Save",
            "bounds": {"x": 10, "y": 20, "width": 80, "height": 30},
        },
        {
            "role": "a",
            "name": "Home",
            "bounds": {"x": 100, "y": 5, "width": 60, "height": 20},
        },
        {
            "role": "a",
            "name": "",
            "bounds": {"x": 200, "y": 5, "width": 60, "height": 20},
        },  # empty name
        {
            "role": "div",
            "name": "Hidden",
            "bounds": {"x": 0, "y": 0, "width": 0, "height": 0},
        },  # zero size
    ]
    result = extract_elements(elements)
    assert len(result) == 2
    assert result[0]["name"] == "Save"
    assert result[1]["name"] == "Home"


def test_extract_elements_empty():
    assert extract_elements([]) == []
    assert extract_elements(None) == []
    assert extract_elements({}) == []


def test_extract_elements_legacy_tree():
    tree = {
        "role": "WebArea",
        "name": "page",
        "children": [
            {
                "role": "button",
                "name": "Submit",
                "bounds": {"x": 10, "y": 20, "width": 80, "height": 30},
            },
            {
                "role": "heading",
                "name": "Welcome",
                "bounds": {"x": 0, "y": 0, "width": 200, "height": 40},
            },
            {
                "role": "navigation",
                "name": "nav",
                "children": [
                    {
                        "role": "link",
                        "name": "About",
                        "bounds": {"x": 50, "y": 100, "width": 60, "height": 20},
                    }
                ],
            },
        ],
    }
    result = extract_elements(tree)
    assert len(result) == 3
    names = [el["name"] for el in result]
    assert "Submit" in names
    assert "Welcome" in names
    assert "About" in names


def test_annotate_screenshot_creates_file(tmp_path):
    # Create a simple test image
    img = Image.new("RGB", (200, 200), color="white")
    src = tmp_path / "test.png"
    img.save(src)

    elements = [
        {
            "role": "button",
            "name": "Save",
            "bounds": {"x": 50, "y": 50, "width": 80, "height": 30},
        },
        {
            "role": "link",
            "name": "Home",
            "bounds": {"x": 10, "y": 10, "width": 60, "height": 20},
        },
    ]
    dest = tmp_path / "annotated.png"
    result = annotate_screenshot(src, elements, dest)

    assert dest.exists()
    assert len(result) == 2


def test_annotate_screenshot_missing_file(tmp_path):
    missing = tmp_path / "missing.png"
    dest = tmp_path / "annotated.png"
    result = annotate_screenshot(missing, [], dest)
    assert result is None
    assert not dest.exists()


def test_annotate_screenshot_deduplication(tmp_path):
    img = Image.new("RGB", (200, 200), color="white")
    src = tmp_path / "test.png"
    img.save(src)

    # Same element listed twice
    elements = [
        {
            "role": "button",
            "name": "Save",
            "bounds": {"x": 50, "y": 50, "width": 80, "height": 30},
        },
        {
            "role": "button",
            "name": "Save",
            "bounds": {"x": 50, "y": 50, "width": 80, "height": 30},
        },
    ]
    dest = tmp_path / "annotated.png"
    result = annotate_screenshot(src, elements, dest)
    assert len(result) == 1  # Deduplicated


def test_annotate_screenshot_limits_to_15(tmp_path):
    img = Image.new("RGB", (400, 400), color="white")
    src = tmp_path / "test.png"
    img.save(src)

    elements = [
        {
            "role": "button",
            "name": f"Btn{i}",
            "bounds": {"x": i * 10, "y": i * 10, "width": 50, "height": 20},
        }
        for i in range(25)
    ]
    dest = tmp_path / "annotated.png"
    result = annotate_screenshot(src, elements, dest)
    assert len(result) == 15


def test_blur_pii_regions(tmp_path):
    """Blurring known regions should produce a different image."""
    img = Image.new("RGB", (200, 200), color="white")
    # Draw a checkerboard in the blur region so blur actually changes pixels
    for x in range(50, 100):
        for y in range(50, 100):
            color = (255, 0, 0) if (x + y) % 2 == 0 else (0, 0, 255)
            img.putpixel((x, y), color)
    src = tmp_path / "test.png"
    img.save(src)

    dest = tmp_path / "blurred.png"
    regions = [{"x": 50, "y": 50, "width": 50, "height": 50}]
    blur_pii_regions(src, regions, dest)

    assert dest.exists()
    # Compare a pixel inside the blurred region — checkerboard should be smoothed
    original = Image.open(src)
    blurred = Image.open(dest)
    orig_pixel = original.getpixel((75, 75))
    blur_pixel = blurred.getpixel((75, 75))
    assert orig_pixel != blur_pixel


def test_blur_empty_regions(tmp_path):
    """Empty regions list should be a no-op (no output file created)."""
    img = Image.new("RGB", (100, 100), color="blue")
    src = tmp_path / "test.png"
    img.save(src)

    dest = tmp_path / "blurred.png"
    blur_pii_regions(src, [], dest)
    # Empty regions = early return, no output written
    assert not dest.exists()


def test_blur_out_of_bounds(tmp_path):
    """Regions outside image bounds should not crash."""
    img = Image.new("RGB", (100, 100), color="green")
    src = tmp_path / "test.png"
    img.save(src)

    dest = tmp_path / "blurred.png"
    regions = [
        {"x": 200, "y": 200, "width": 50, "height": 50},  # completely outside
        {"x": 80, "y": 80, "width": 50, "height": 50},  # partially outside
    ]
    blur_pii_regions(src, regions, dest)
    assert dest.exists()


def test_blur_pii_regions_with_label_value_type(tmp_path):
    """blur_pii_regions should work with regions that include type: 'label_value'.

    Documents the contract: blur_pii_regions only reads x/y/width/height and
    ignores any extra fields like 'type'.
    """
    img = Image.new("RGB", (200, 200), color="white")
    # Create a checkerboard pattern in the blur area
    for x in range(20, 80):
        for y in range(20, 80):
            color = (255, 0, 0) if (x + y) % 2 == 0 else (0, 0, 255)
            img.putpixel((x, y), color)
    src = tmp_path / "test.png"
    img.save(src)

    dest = tmp_path / "blurred.png"
    regions = [
        {"x": 20, "y": 20, "width": 60, "height": 60, "type": "label_value"},
        {"x": 100, "y": 100, "width": 40, "height": 40, "type": "input"},
    ]
    blur_pii_regions(src, regions, dest)

    assert dest.exists()
    original = Image.open(src)
    blurred = Image.open(dest)
    # The checkerboard region should be smoothed
    assert original.getpixel((50, 50)) != blurred.getpixel((50, 50))
