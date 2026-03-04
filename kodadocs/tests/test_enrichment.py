import json
import re
from unittest.mock import patch
from kodadocs.models import SessionConfig, RunManifest


def test_skip_ai_leaves_articles_empty(tmp_path):
    """When skip_ai=True, enrichment skips without creating placeholder articles."""
    from kodadocs.pipeline.enrichment import enrichment_step

    config = SessionConfig(
        app_url="http://localhost:3000",
        project_path=tmp_path,
        skip_ai=True,
    )
    manifest = RunManifest(session_id="test", config=config)

    enrichment_step(manifest)

    assert len(manifest.articles) == 0


def test_skip_ai_preserves_existing_articles(tmp_path):
    """When skip_ai=True and articles already exist, don't touch them."""
    from kodadocs.pipeline.enrichment import enrichment_step

    config = SessionConfig(
        app_url="http://localhost:3000",
        project_path=tmp_path,
        skip_ai=True,
    )
    manifest = RunManifest(session_id="test", config=config)
    manifest.articles = [{"title": "Existing", "content": "# Existing"}]

    enrichment_step(manifest)

    assert len(manifest.articles) == 1
    assert manifest.articles[0]["title"] == "Existing"


def test_no_api_key_skips_enrichment(tmp_path):
    from kodadocs.pipeline.enrichment import enrichment_step

    config = SessionConfig(
        app_url="http://localhost:3000",
        project_path=tmp_path,
        skip_ai=False,
    )
    manifest = RunManifest(session_id="test", config=config)

    with patch.dict("os.environ", {}, clear=True):
        enrichment_step(manifest)

    assert len(manifest.articles) == 0


def test_json_extraction_from_code_block():
    """Test the regex patterns used to extract JSON from AI responses."""
    # Code block format
    text = '```json\n{"articles": [{"title": "Test"}]}\n```'
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    assert match is not None
    data = json.loads(match.group(1))
    assert data["articles"][0]["title"] == "Test"


def test_json_extraction_from_raw_braces():
    """Test fallback regex for raw JSON."""
    text = 'Here is the plan:\n{"articles": [{"title": "Guide"}]}'
    match = re.search(r"\{.*\}", text, re.DOTALL)
    assert match is not None
    data = json.loads(match.group(0))
    assert data["articles"][0]["title"] == "Guide"
