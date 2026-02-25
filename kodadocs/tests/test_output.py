import pytest
import json
from pathlib import Path
from kodadocs.models import SessionConfig, RunManifest, StepResult, StepStatus, Framework
from unittest.mock import patch


def _make_manifest(tmp_path, articles=None, routes=None, screenshots=None):
    project_path = tmp_path / "project"
    project_path.mkdir(exist_ok=True)
    output_path = tmp_path / "docs"

    config = SessionConfig(
        app_url="http://localhost:3000",
        project_path=project_path,
        output_path=output_path,
        framework=Framework.NEXTJS,
    )
    manifest = RunManifest(session_id="test", config=config)
    manifest.product_summary = "Test product summary"
    manifest.discovered_routes = routes or ["/"]
    manifest.articles = articles or [
        {"title": "Getting Started", "content": "# Getting Started\n\nWelcome."},
    ]
    manifest.screenshots = screenshots or {}
    # Mark Output step as running so it doesn't fail
    manifest.steps["Output"] = StepResult(name="Output", status=StepStatus.RUNNING)
    return manifest


def test_output_creates_index(tmp_path):
    from kodadocs.pipeline.output import output_step

    manifest = _make_manifest(tmp_path)

    with patch("subprocess.run"):
        output_step(manifest)

    index_file = tmp_path / "docs" / "index.md"
    assert index_file.exists()
    content = index_file.read_text()
    assert "Test product summary" in content
    # Should NOT contain developer-facing artifacts
    assert "Auto-Generated" not in content
    assert "Discovered Routes" not in content


def test_output_creates_article_pages(tmp_path):
    from kodadocs.pipeline.output import output_step

    manifest = _make_manifest(tmp_path, articles=[
        {"title": "Getting Started", "content": "# Getting Started\n\nWelcome."},
        {"title": "Dashboard Guide", "content": "# Dashboard\n\nView your data."},
    ])

    with patch("subprocess.run"):
        output_step(manifest)

    assert (tmp_path / "docs" / "getting-started.md").exists()
    assert (tmp_path / "docs" / "dashboard-guide.md").exists()


def test_output_creates_vitepress_config(tmp_path):
    from kodadocs.pipeline.output import output_step

    manifest = _make_manifest(tmp_path)

    with patch("subprocess.run"):
        output_step(manifest)

    config_file = tmp_path / "docs" / ".vitepress" / "config.mts"
    assert config_file.exists()
    content = config_file.read_text()
    assert "defineConfig" in content
    assert "project Docs" in content


def test_output_creates_package_json(tmp_path):
    from kodadocs.pipeline.output import output_step

    manifest = _make_manifest(tmp_path)

    with patch("subprocess.run"):
        output_step(manifest)

    pkg_file = tmp_path / "docs" / "package.json"
    assert pkg_file.exists()
    pkg = json.loads(pkg_file.read_text())
    assert "vitepress" in pkg["devDependencies"]
    assert pkg["devDependencies"]["vitepress"] == "~1.6.0"


def test_output_creates_theme_files(tmp_path):
    from kodadocs.pipeline.output import output_step

    manifest = _make_manifest(tmp_path)

    with patch("subprocess.run"):
        output_step(manifest)

    theme_dir = tmp_path / "docs" / ".vitepress" / "theme"
    assert (theme_dir / "index.ts").exists()
    assert (theme_dir / "style.css").exists()
    css = (theme_dir / "style.css").read_text()
    assert "#3e8fb0" in css


def test_output_copies_screenshots_to_assets(tmp_path):
    from kodadocs.pipeline.output import output_step

    project_path = tmp_path / "project"
    project_path.mkdir()
    ss_dir = project_path / ".kodadocs" / "screenshots"
    ss_dir.mkdir(parents=True)

    # Create a fake screenshot
    (ss_dir / "index.png").write_bytes(b"fake png data")

    manifest = _make_manifest(tmp_path, screenshots={"/": ".kodadocs/screenshots/index.png"})
    manifest.config.project_path = project_path

    with patch("subprocess.run"):
        output_step(manifest)

    assert (tmp_path / "docs" / "assets" / "index.png").exists()


def test_output_hero_links_to_first_article(tmp_path):
    """Hero CTA should link to the first article slug, not hardcoded /getting-started."""
    from kodadocs.pipeline.output import output_step

    manifest = _make_manifest(tmp_path, articles=[
        {"title": "Welcome", "content": "# Welcome\n\nHello there."},
        {"title": "Dashboard Guide", "content": "# Dashboard\n\nView your data."},
    ])

    with patch("subprocess.run"):
        output_step(manifest)

    index_file = tmp_path / "docs" / "index.md"
    content = index_file.read_text()
    assert "link: /welcome" in content
    assert "/getting-started" not in content


def test_output_enables_local_search(tmp_path):
    """Pipeline output_step must produce config.mts with local search enabled (OUT-04)."""
    from kodadocs.pipeline.output import output_step

    manifest = _make_manifest(tmp_path)

    with patch("subprocess.run"):
        output_step(manifest)

    config_file = tmp_path / "docs" / ".vitepress" / "config.mts"
    config = config_file.read_text()
    assert "provider" in config
    assert "local" in config
