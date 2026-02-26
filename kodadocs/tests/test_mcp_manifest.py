import json

from kodadocs.mcp.tools.manifest import save_manifest_tool, load_manifest_tool


def test_save_and_load_manifest(tmp_path):
    manifest_data = {
        "session_id": "test_001",
        "discovered_routes": ["/", "/dashboard"],
        "product_summary": "A task management app.",
        "screenshots": {"/": ".kodadocs/screenshots/index.png"},
        "articles": [{"title": "Getting Started", "content": "# Hello"}],
    }
    result = save_manifest_tool(manifest_data, str(tmp_path))
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert (tmp_path / ".kodadocs" / "run_manifest.json").exists()

    loaded = load_manifest_tool(str(tmp_path))
    loaded_parsed = json.loads(loaded)
    assert loaded_parsed["status"] == "ok"
    assert loaded_parsed["manifest"]["session_id"] == "test_001"
    assert loaded_parsed["manifest"]["discovered_routes"] == ["/", "/dashboard"]


def test_load_manifest_not_found(tmp_path):
    result = load_manifest_tool(str(tmp_path))
    parsed = json.loads(result)
    assert parsed["status"] == "error"
