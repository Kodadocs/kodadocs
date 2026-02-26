import json
from unittest.mock import patch
from kodadocs.mcp.tools.capture import capture_screenshots_tool


def test_capture_screenshots_no_app(tmp_path):
    """Returns error when app is unreachable."""
    result = capture_screenshots_tool(
        routes=["/"],
        app_url="http://localhost:99999",
        auth=None,
        output_dir=str(tmp_path / "screenshots"),
    )
    parsed = json.loads(result)
    assert parsed["status"] == "error"
    assert "could not reach" in parsed["message"].lower()


def test_capture_screenshots_creates_output_dir(tmp_path):
    """Output directory is created if it doesn't exist."""
    output_dir = tmp_path / "screenshots"
    assert not output_dir.exists()
    with patch("kodadocs.mcp.tools.capture._check_app_reachable", return_value=False):
        capture_screenshots_tool(
            routes=["/"],
            app_url="http://localhost:3000",
            auth=None,
            output_dir=str(output_dir),
        )
    assert output_dir.exists()


def test_capture_screenshots_with_auth_dict(tmp_path):
    """Auth dict is properly handled without crashing."""
    output_dir = tmp_path / "screenshots"
    with patch("kodadocs.mcp.tools.capture._check_app_reachable", return_value=False):
        result = capture_screenshots_tool(
            routes=["/dashboard"],
            app_url="http://localhost:3000",
            auth={
                "username": "admin",
                "password": "pass",
                "auth_url": "http://localhost:3000/login",
            },
            output_dir=str(output_dir),
        )
    parsed = json.loads(result)
    assert parsed["status"] == "error"
