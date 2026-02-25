import pytest
import json
from pathlib import Path
from kodadocs.mcp.tools.output import assemble_vitepress_tool


def test_assemble_creates_vitepress_structure(tmp_path):
    output_dir = tmp_path / "docs"
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()

    articles = [
        {"title": "Getting Started", "content": "# Getting Started\n\nWelcome to the app."},
        {"title": "Dashboard Guide", "content": "# Dashboard Guide\n\nUse the dashboard."},
    ]

    result = assemble_vitepress_tool(
        articles=articles, screenshots_dir=str(screenshots_dir),
        brand_color="#3e8fb0", logo_path=None, output_dir=str(output_dir),
        project_name="test-app", product_summary="A test application.",
        discovered_routes=["/", "/dashboard"],
    )
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert parsed["articles_count"] == 2
    assert (output_dir / "index.md").exists()
    assert (output_dir / ".vitepress" / "config.mts").exists()
    assert (output_dir / "getting-started.md").exists()
    assert (output_dir / "dashboard-guide.md").exists()


def test_assemble_applies_brand_color(tmp_path):
    output_dir = tmp_path / "docs"
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()

    assemble_vitepress_tool(
        articles=[{"title": "Test", "content": "# Test"}],
        screenshots_dir=str(screenshots_dir), brand_color="#ff5500",
        logo_path=None, output_dir=str(output_dir),
        project_name="test-app", product_summary="Test.",
        discovered_routes=["/"],
    )
    style_css = output_dir / ".vitepress" / "theme" / "style.css"
    assert style_css.exists()
    assert "#ff5500" in style_css.read_text()


def test_assemble_copies_screenshots(tmp_path):
    output_dir = tmp_path / "docs"
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    (screenshots_dir / "index.png").write_bytes(b"fake-png-data")
    annotated_dir = screenshots_dir / "annotated"
    annotated_dir.mkdir()
    (annotated_dir / "index.png").write_bytes(b"fake-annotated-data")

    assemble_vitepress_tool(
        articles=[{"title": "Home", "content": "# Home"}],
        screenshots_dir=str(screenshots_dir), brand_color="#000000",
        logo_path=None, output_dir=str(output_dir),
        project_name="test-app", product_summary="Test.",
        discovered_routes=["/"],
    )
    assets_dir = output_dir / "assets"
    assert (assets_dir / "index.png").exists()
    assert (assets_dir / "annotated-index.png").exists()


def test_assemble_generates_package_json(tmp_path):
    output_dir = tmp_path / "docs"
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()

    assemble_vitepress_tool(
        articles=[{"title": "Test", "content": "# Test"}],
        screenshots_dir=str(screenshots_dir), brand_color="#3e8fb0",
        logo_path=None, output_dir=str(output_dir),
        project_name="My App", product_summary="Test.",
        discovered_routes=["/"],
    )
    pkg_path = output_dir / "package.json"
    assert pkg_path.exists()
    pkg = json.loads(pkg_path.read_text())
    assert pkg["name"] == "my-app-docs"
    assert "vitepress" in pkg["devDependencies"]


def test_assemble_does_not_overwrite_package_json(tmp_path):
    output_dir = tmp_path / "docs"
    output_dir.mkdir(parents=True)
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    (output_dir / "package.json").write_text('{"name": "custom"}')

    assemble_vitepress_tool(
        articles=[{"title": "Test", "content": "# Test"}],
        screenshots_dir=str(screenshots_dir), brand_color="#3e8fb0",
        logo_path=None, output_dir=str(output_dir),
        project_name="test-app", product_summary="Test.",
        discovered_routes=["/"],
    )
    pkg = json.loads((output_dir / "package.json").read_text())
    assert pkg["name"] == "custom"


def test_assemble_index_contains_product_summary(tmp_path):
    output_dir = tmp_path / "docs"
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()

    assemble_vitepress_tool(
        articles=[{"title": "Test", "content": "# Test"}],
        screenshots_dir=str(screenshots_dir), brand_color="#3e8fb0",
        logo_path=None, output_dir=str(output_dir),
        project_name="test-app", product_summary="An amazing product for testing.",
        discovered_routes=["/", "/about"],
    )
    index_content = (output_dir / "index.md").read_text()
    assert "An amazing product for testing." in index_content
    # Should NOT contain developer-facing artifacts like raw route lists
    assert "Discovered Routes" not in index_content


def test_assemble_sidebar_config(tmp_path):
    output_dir = tmp_path / "docs"
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()

    assemble_vitepress_tool(
        articles=[
            {"title": "Getting Started", "content": "# Getting Started"},
            {"title": "API Reference", "content": "# API Reference"},
        ],
        screenshots_dir=str(screenshots_dir), brand_color="#3e8fb0",
        logo_path=None, output_dir=str(output_dir),
        project_name="test-app", product_summary="Test.",
        discovered_routes=["/"],
    )
    config = (output_dir / ".vitepress" / "config.mts").read_text()
    assert "/getting-started" in config
    assert "/api-reference" in config
    assert "Getting Started" in config
    assert "API Reference" in config


def test_assemble_enables_local_search(tmp_path):
    """config.mts must contain search: { provider: 'local' } (OUT-04)."""
    output_dir = tmp_path / "docs"
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()

    assemble_vitepress_tool(
        articles=[{"title": "Test", "content": "# Test"}],
        screenshots_dir=str(screenshots_dir), brand_color="#3e8fb0",
        logo_path=None, output_dir=str(output_dir),
        project_name="test-app", product_summary="Test.",
        discovered_routes=["/"],
    )
    config = (output_dir / ".vitepress" / "config.mts").read_text()
    assert "provider" in config
    assert "local" in config


def test_assemble_injects_logo_when_provided(tmp_path):
    """Logo file copied to assets/ and config.mts references it (OUT-05)."""
    output_dir = tmp_path / "docs"
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    logo_file = tmp_path / "my-logo.png"
    logo_file.write_bytes(b"fake-logo-data")

    assemble_vitepress_tool(
        articles=[{"title": "Test", "content": "# Test"}],
        screenshots_dir=str(screenshots_dir), brand_color="#3e8fb0",
        logo_path=str(logo_file), output_dir=str(output_dir),
        project_name="test-app", product_summary="Test.",
        discovered_routes=["/"],
    )
    # Logo copied to assets
    assert (output_dir / "assets" / "my-logo.png").exists()
    # Config references it
    config = (output_dir / ".vitepress" / "config.mts").read_text()
    assert "logo" in config
    assert "/assets/my-logo.png" in config


def test_assemble_no_logo_when_not_provided(tmp_path):
    """No logo entry in config when logo_path is None."""
    output_dir = tmp_path / "docs"
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()

    assemble_vitepress_tool(
        articles=[{"title": "Test", "content": "# Test"}],
        screenshots_dir=str(screenshots_dir), brand_color="#3e8fb0",
        logo_path=None, output_dir=str(output_dir),
        project_name="test-app", product_summary="Test.",
        discovered_routes=["/"],
    )
    config = (output_dir / ".vitepress" / "config.mts").read_text()
    assert "logo" not in config


def test_assemble_slug_unicode_normalization(tmp_path):
    """Unicode titles produce correct ASCII slugs via NFKD (OUT-08)."""
    output_dir = tmp_path / "docs"
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()

    assemble_vitepress_tool(
        articles=[
            {"title": "R\u00e9sum\u00e9 Upload", "content": "# R\u00e9sum\u00e9 Upload"},
        ],
        screenshots_dir=str(screenshots_dir), brand_color="#3e8fb0",
        logo_path=None, output_dir=str(output_dir),
        project_name="test-app", product_summary="Test.",
        discovered_routes=["/"],
    )
    assert (output_dir / "resume-upload.md").exists()
    config = (output_dir / ".vitepress" / "config.mts").read_text()
    assert "/resume-upload" in config


def test_assemble_deduplicates_duplicate_title_slugs(tmp_path):
    """Two articles with identical titles produce unique slugs (OUT-08)."""
    output_dir = tmp_path / "docs"
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()

    assemble_vitepress_tool(
        articles=[
            {"title": "FAQ", "content": "# FAQ\n\nFirst FAQ."},
            {"title": "FAQ", "content": "# FAQ\n\nSecond FAQ."},
        ],
        screenshots_dir=str(screenshots_dir), brand_color="#3e8fb0",
        logo_path=None, output_dir=str(output_dir),
        project_name="test-app", product_summary="Test.",
        discovered_routes=["/"],
    )
    assert (output_dir / "faq.md").exists()
    assert (output_dir / "faq-1.md").exists()
    config = (output_dir / ".vitepress" / "config.mts").read_text()
    assert "/faq" in config
    assert "/faq-1" in config
