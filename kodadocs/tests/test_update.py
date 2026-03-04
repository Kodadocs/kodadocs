import pytest
import json
from unittest.mock import patch, MagicMock
from kodadocs.models import SessionConfig, RunManifest, StepResult
from kodadocs.pipeline.update import (
    compute_route_diff,
    prune_removed_routes,
    prune_removed_articles,
    selective_capture_step,
    selective_annotation_step,
    incremental_enrichment_step,
)


# ── compute_route_diff ────────────────────────────────────────────────


def test_compute_route_diff_added_removed():
    """Basic set diff: detect added and removed routes."""
    previous = ["/", "/about", "/settings"]
    current = ["/", "/about", "/dashboard"]
    added, removed, changed = compute_route_diff(previous, current)
    assert added == {"/dashboard"}
    assert removed == {"/settings"}
    assert changed == set()


def test_compute_route_diff_with_forced():
    """--routes flag puts existing routes in changed set."""
    previous = ["/", "/dashboard"]
    current = ["/", "/dashboard", "/new"]
    added, removed, changed = compute_route_diff(
        previous, current, forced=["/dashboard"]
    )
    assert added == {"/new"}
    assert removed == set()
    assert changed == {"/dashboard"}


def test_compute_route_diff_forced_ignores_missing():
    """Forced routes that don't exist in current are ignored."""
    previous = ["/", "/about"]
    current = ["/", "/about"]
    added, removed, changed = compute_route_diff(
        previous, current, forced=["/nonexistent"]
    )
    assert added == set()
    assert removed == set()
    assert changed == set()


def test_compute_route_diff_no_changes():
    """Returns all empty when routes are identical."""
    routes = ["/", "/about", "/settings"]
    added, removed, changed = compute_route_diff(routes, routes)
    assert added == set()
    assert removed == set()
    assert changed == set()


def test_compute_route_diff_empty_previous():
    """All current routes are added when previous is empty."""
    added, removed, changed = compute_route_diff([], ["/", "/about"])
    assert added == {"/", "/about"}
    assert removed == set()


def test_compute_route_diff_empty_current():
    """All previous routes are removed when current is empty."""
    added, removed, changed = compute_route_diff(["/", "/about"], [])
    assert added == set()
    assert removed == {"/", "/about"}


# ── prune_removed_routes ─────────────────────────────────────────────


def test_prune_removed_routes(tmp_path):
    """Cleans screenshots, dom_elements, annotated_elements, pii_regions, page_descriptions, route_metadata."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(session_id="test", config=config)

    manifest.screenshots = {
        "/": "screenshots/index.png",
        "/_annotated": "screenshots/annotated/index.png",
        "/old": "screenshots/old.png",
        "/old_annotated": "screenshots/annotated/old.png",
    }
    manifest.dom_elements = {"/": [], "/old": []}
    manifest.annotated_elements = {"/": [], "/old": []}
    manifest.pii_regions = {"/": [], "/old": [{"x": 0}]}
    manifest.page_descriptions = {"/": "Home", "/old": "Old page"}
    manifest.route_metadata = {"/": {"type": "page"}, "/old": {"type": "page"}}

    prune_removed_routes(manifest, {"/old"})

    assert "/old" not in manifest.screenshots
    assert "/old_annotated" not in manifest.screenshots
    assert "/old" not in manifest.dom_elements
    assert "/old" not in manifest.annotated_elements
    assert "/old" not in manifest.pii_regions
    assert "/old" not in manifest.page_descriptions
    assert "/old" not in manifest.route_metadata

    # Surviving routes untouched
    assert "/" in manifest.screenshots
    assert "/" in manifest.dom_elements


def test_prune_removed_routes_empty_set(tmp_path):
    """No-op when removed set is empty."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(session_id="test", config=config)
    manifest.screenshots = {"/": "s.png"}

    prune_removed_routes(manifest, set())
    assert "/" in manifest.screenshots


# ── prune_removed_articles ───────────────────────────────────────────


def test_prune_removed_articles_orphans(tmp_path):
    """Removes articles whose routes are all gone."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(session_id="test", config=config)

    manifest.articles = [
        {"title": "Getting Started", "content": "# Getting Started"},
        {"title": "Old Feature", "content": "# Old Feature"},
    ]
    manifest.confidence_scores = {"Getting Started": 0.9, "Old Feature": 0.8}
    manifest.article_route_map = {
        "Getting Started": ["/"],
        "Old Feature": ["/old-page", "/old-settings"],
    }

    prune_removed_articles(manifest, {"/old-page", "/old-settings"})

    assert len(manifest.articles) == 1
    assert manifest.articles[0]["title"] == "Getting Started"
    assert "Old Feature" not in manifest.confidence_scores
    assert "Old Feature" not in manifest.article_route_map


def test_prune_removed_articles_keeps_shared(tmp_path):
    """Keeps articles that still have surviving routes."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(session_id="test", config=config)

    manifest.articles = [
        {"title": "Dashboard Guide", "content": "# Dashboard"},
    ]
    manifest.confidence_scores = {"Dashboard Guide": 0.85}
    manifest.article_route_map = {
        "Dashboard Guide": ["/dashboard", "/dashboard/settings"],
    }

    # Only one of the article's routes is removed
    prune_removed_articles(manifest, {"/dashboard/settings"})

    assert len(manifest.articles) == 1
    assert manifest.articles[0]["title"] == "Dashboard Guide"
    assert "Dashboard Guide" in manifest.article_route_map


def test_prune_removed_articles_empty_map(tmp_path):
    """No-op when article_route_map is empty (old manifests)."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(session_id="test", config=config)
    manifest.articles = [{"title": "Test", "content": "# Test"}]

    prune_removed_articles(manifest, {"/old"})

    assert len(manifest.articles) == 1


# ── selective_capture_step ───────────────────────────────────────────


def test_selective_capture_scopes_routes(tmp_path):
    """Capture only runs for specified routes, then restores discovered_routes."""
    config = SessionConfig(project_path=tmp_path, app_url="http://localhost:3000")
    manifest = RunManifest(session_id="test", config=config)
    manifest.discovered_routes = ["/", "/about", "/dashboard", "/new"]

    captured_routes = []

    def mock_capture_step(m):
        captured_routes.extend(m.discovered_routes)

    with patch("kodadocs.pipeline.capture.capture_step", mock_capture_step):
        selective_capture_step(manifest, {"/new", "/dashboard"})

    # Only the specified routes were passed to capture
    assert set(captured_routes) == {"/dashboard", "/new"}
    # Original routes are restored
    assert manifest.discovered_routes == ["/", "/about", "/dashboard", "/new"]


def test_selective_capture_restores_on_error(tmp_path):
    """discovered_routes are restored even if capture_step raises."""
    config = SessionConfig(project_path=tmp_path, app_url="http://localhost:3000")
    manifest = RunManifest(session_id="test", config=config)
    manifest.discovered_routes = ["/", "/about"]

    def failing_capture(m):
        raise RuntimeError("capture failed")

    with patch("kodadocs.pipeline.capture.capture_step", failing_capture):
        with pytest.raises(RuntimeError, match="capture failed"):
            selective_capture_step(manifest, {"/new"})

    assert manifest.discovered_routes == ["/", "/about"]


# ── selective_annotation_step ────────────────────────────────────────


def test_selective_annotation_scopes_routes(tmp_path):
    """Annotation only processes specified routes."""
    config = SessionConfig(project_path=tmp_path, blur_pii=False)
    manifest = RunManifest(session_id="test", config=config)

    # Create a dummy screenshot file
    screenshots_dir = tmp_path / ".kodadocs" / "screenshots"
    screenshots_dir.mkdir(parents=True)
    annotated_dir = screenshots_dir / "annotated"
    annotated_dir.mkdir()

    from PIL import Image

    img = Image.new("RGB", (100, 100), "white")
    img.save(screenshots_dir / "new-page.png")

    manifest.screenshots = {
        "/": ".kodadocs/screenshots/index.png",
        "/new-page": ".kodadocs/screenshots/new-page.png",
    }
    manifest.dom_elements = {
        "/": [
            {
                "role": "button",
                "name": "Home",
                "bounds": {"x": 10, "y": 10, "width": 50, "height": 20},
            }
        ],
        "/new-page": [
            {
                "role": "button",
                "name": "Save",
                "bounds": {"x": 10, "y": 10, "width": 50, "height": 20},
            }
        ],
    }

    annotated_calls = []

    def mock_annotate(image_path, elements, output_path, brand_color="#3e8fb0"):
        annotated_calls.append(str(image_path))
        return elements

    with patch("kodadocs.pipeline.annotation.annotate_screenshot", mock_annotate):
        selective_annotation_step(manifest, {"/new-page"})

    # Only /new-page was annotated, not /
    assert len(annotated_calls) == 1
    assert "new-page" in annotated_calls[0]


# ── incremental_enrichment_step ──────────────────────────────────────


def test_incremental_enrichment_skip_ai(tmp_path):
    """skip_ai=True skips enrichment entirely."""
    config = SessionConfig(project_path=tmp_path, skip_ai=True)
    manifest = RunManifest(session_id="test", config=config)
    manifest.articles = [{"title": "Existing", "content": "# Existing"}]

    incremental_enrichment_step(manifest, {"/new"}, set())

    assert len(manifest.articles) == 1


def test_incremental_enrichment_no_api_key(tmp_path):
    """Missing API key skips enrichment."""
    config = SessionConfig(project_path=tmp_path, skip_ai=False)
    manifest = RunManifest(session_id="test", config=config)

    with patch.dict("os.environ", {}, clear=True):
        incremental_enrichment_step(manifest, {"/new"}, set())

    assert len(manifest.articles) == 0


def test_incremental_enrichment_generates_only_new(tmp_path):
    """AI is called only for new routes; existing articles preserved."""
    config = SessionConfig(project_path=tmp_path, skip_ai=False)
    manifest = RunManifest(session_id="test", config=config)
    manifest.product_summary = "A test app"
    manifest.discovered_routes = ["/", "/about", "/new"]
    manifest.screenshots = {"/": "s.png", "/about": "s2.png", "/new": "s3.png"}
    manifest.articles = [
        {"title": "Getting Started", "content": "# Getting Started"},
    ]
    manifest.article_route_map = {"Getting Started": ["/"]}
    manifest.steps["IncrementalEnrichment"] = StepResult(name="IncrementalEnrichment")

    # Mock the Anthropic client
    mock_client = MagicMock()

    # Structure call response: one new article, no updates
    structure_response = MagicMock()
    structure_response.content = [
        MagicMock(
            text=json.dumps(
                {
                    "new_articles": [
                        {
                            "title": "New Page Guide",
                            "description": "Guide for /new",
                            "related_routes": ["/new"],
                            "complexity": "Simple",
                        }
                    ],
                    "updated_articles": [],
                }
            )
        )
    ]
    structure_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    # Content generation response
    content_response = MagicMock()
    content_response.content = [
        MagicMock(
            text=json.dumps(
                {
                    "content": "# New Page Guide\n\nContent here.",
                    "confidence_score": 0.9,
                }
            )
        )
    ]
    content_response.usage = MagicMock(input_tokens=200, output_tokens=300)

    mock_client.messages.create.side_effect = [structure_response, content_response]

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch(
            "kodadocs.pipeline.update.anthropic.Anthropic", return_value=mock_client
        ):
            incremental_enrichment_step(manifest, {"/new"}, set())

    # Original article preserved + new one added
    assert len(manifest.articles) == 2
    titles = [a["title"] for a in manifest.articles]
    assert "Getting Started" in titles
    assert "New Page Guide" in titles
    assert manifest.article_route_map["New Page Guide"] == ["/new"]


def test_incremental_enrichment_merges_articles(tmp_path):
    """Updated articles have their content replaced; new articles appended."""
    config = SessionConfig(project_path=tmp_path, skip_ai=False)
    manifest = RunManifest(session_id="test", config=config)
    manifest.product_summary = "A test app"
    manifest.discovered_routes = ["/", "/dashboard"]
    manifest.screenshots = {"/": "s.png", "/dashboard": "s2.png"}
    manifest.articles = [
        {
            "title": "Dashboard Guide",
            "content": "# Old content",
            "confidence_score": 0.7,
        },
    ]
    manifest.article_route_map = {"Dashboard Guide": ["/dashboard"]}
    manifest.steps["IncrementalEnrichment"] = StepResult(name="IncrementalEnrichment")

    mock_client = MagicMock()

    # Structure response: update existing article
    structure_response = MagicMock()
    structure_response.content = [
        MagicMock(
            text=json.dumps(
                {
                    "new_articles": [],
                    "updated_articles": [
                        {
                            "title": "Dashboard Guide",
                            "additional_routes": ["/dashboard"],
                        }
                    ],
                }
            )
        )
    ]
    structure_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    # Regenerated content
    content_response = MagicMock()
    content_response.content = [
        MagicMock(
            text=json.dumps(
                {
                    "content": "# Dashboard Guide\n\nUpdated content.",
                    "confidence_score": 0.95,
                }
            )
        )
    ]
    content_response.usage = MagicMock(input_tokens=200, output_tokens=300)

    mock_client.messages.create.side_effect = [structure_response, content_response]

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch(
            "kodadocs.pipeline.update.anthropic.Anthropic", return_value=mock_client
        ):
            incremental_enrichment_step(manifest, set(), {"/dashboard"})

    # Article count unchanged, content updated
    assert len(manifest.articles) == 1
    assert "Updated content" in manifest.articles[0]["content"]
    assert manifest.articles[0]["confidence_score"] == 0.95


# ── update command integration ───────────────────────────────────────


def test_update_requires_manifest(tmp_path):
    """Error if no run_manifest.json exists."""
    from typer.testing import CliRunner
    from kodadocs.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["update", str(tmp_path)])
    assert result.exit_code != 0
    assert "No existing manifest" in result.output or "generate" in result.output


def test_update_no_changes_exits_clean(tmp_path):
    """Prints message and exits 0 when routes unchanged."""
    from typer.testing import CliRunner
    from kodadocs.main import app

    # Create a manifest with routes
    config = SessionConfig(project_path=tmp_path, app_url="http://localhost:3000")
    manifest = RunManifest(
        session_id="test",
        config=config,
        config_hash="abc123",
        discovered_routes=["/", "/about"],
        previous_routes=["/", "/about"],
    )

    kodadocs_dir = tmp_path / ".kodadocs"
    kodadocs_dir.mkdir()
    with open(kodadocs_dir / "run_manifest.json", "w") as f:
        f.write(manifest.model_dump_json(indent=2))

    # Mock discovery to return same routes
    def mock_discovery(m):
        m.discovered_routes = ["/", "/about"]

    runner = CliRunner()
    with patch("kodadocs.pipeline.discovery.discovery_step", mock_discovery):
        result = runner.invoke(app, ["update", str(tmp_path)])

    assert result.exit_code == 0
    assert "No changes detected" in result.output


# ── article_route_map populated after enrichment ─────────────────────


def test_article_route_map_populated_after_enrichment(tmp_path):
    """Existing enrichment_step populates the new article_route_map field."""
    from kodadocs.pipeline.enrichment import enrichment_step

    config = SessionConfig(project_path=tmp_path, skip_ai=False)
    manifest = RunManifest(session_id="test", config=config)
    manifest.product_summary = "A test product"
    manifest.discovered_routes = ["/", "/about"]
    manifest.screenshots = {"/": "s.png"}
    manifest.steps["Enrichment"] = StepResult(name="Enrichment")

    mock_client = MagicMock()

    # Structure response
    structure_response = MagicMock()
    structure_response.content = [
        MagicMock(
            text=json.dumps(
                {
                    "articles": [
                        {
                            "title": "Getting Started",
                            "description": "Intro",
                            "related_routes": ["/"],
                            "complexity": "Simple",
                        },
                        {
                            "title": "About",
                            "description": "About page",
                            "related_routes": ["/about"],
                            "complexity": "Simple",
                        },
                    ]
                }
            )
        )
    ]
    structure_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    # Content responses (one per article)
    content1 = MagicMock()
    content1.content = [
        MagicMock(
            text=json.dumps({"content": "# Getting Started", "confidence_score": 0.9})
        )
    ]
    content1.usage = MagicMock(input_tokens=100, output_tokens=200)

    content2 = MagicMock()
    content2.content = [
        MagicMock(text=json.dumps({"content": "# About", "confidence_score": 0.8}))
    ]
    content2.usage = MagicMock(input_tokens=100, output_tokens=200)

    mock_client.messages.create.side_effect = [structure_response, content1, content2]

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch(
            "kodadocs.pipeline.enrichment.anthropic.Anthropic", return_value=mock_client
        ):
            enrichment_step(manifest)

    assert manifest.article_route_map == {
        "Getting Started": ["/"],
        "About": ["/about"],
    }


# ── RunManifest new fields defaults and roundtrip ────────────────────


def test_run_manifest_update_fields_defaults(tmp_path):
    """New RunManifest fields default correctly."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(session_id="test", config=config)
    assert manifest.article_route_map == {}
    assert manifest.previous_routes == []


def test_run_manifest_update_fields_roundtrip(tmp_path):
    """New fields survive serialization roundtrip."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(
        session_id="test",
        config=config,
        article_route_map={"Guide": ["/", "/about"]},
        previous_routes=["/", "/about", "/settings"],
    )
    json_str = manifest.model_dump_json()
    restored = RunManifest.model_validate_json(json_str)
    assert restored.article_route_map == {"Guide": ["/", "/about"]}
    assert restored.previous_routes == ["/", "/about", "/settings"]
