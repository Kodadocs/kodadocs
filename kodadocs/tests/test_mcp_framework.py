from kodadocs.mcp.tools.framework import detect_framework_tool


def test_detect_framework_nextjs(tmp_path):
    package_json = tmp_path / "package.json"
    package_json.write_text('{"dependencies": {"next": "14.0.0", "react": "18.0.0"}}')
    result = detect_framework_tool(str(tmp_path))
    assert result == "Next.js"


def test_detect_framework_unknown(tmp_path):
    result = detect_framework_tool(str(tmp_path))
    assert result == "Unknown"


def test_detect_framework_django(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("django==4.2\n")
    result = detect_framework_tool(str(tmp_path))
    assert result == "Django"
