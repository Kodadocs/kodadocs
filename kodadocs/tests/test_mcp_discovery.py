import json
from unittest.mock import patch, MagicMock
from kodadocs.mcp.tools.discovery import discover_routes_tool


def test_discover_routes_returns_json(tmp_path):
    """Tool always returns valid JSON with expected top-level keys."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
    (tmp_path / "package.json").write_text('{"dependencies": {"next": "14.0.0"}}')

    result = discover_routes_tool(str(tmp_path))
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert "discovered_routes" in parsed
    assert "route_metadata" in parsed
    assert "framework" in parsed
    assert "detected_services" in parsed
    assert "ui_components" in parsed
    assert "deployment_platform" in parsed


def test_discover_routes_nextjs_app_router(tmp_path):
    """Discovers Next.js App Router pages correctly."""
    (tmp_path / "package.json").write_text('{"dependencies": {"next": "14.0.0"}}')
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
    (tmp_path / "app" / "about").mkdir()
    (tmp_path / "app" / "about" / "page.tsx").write_text(
        "export default function About() {}"
    )
    (tmp_path / "app" / "dashboard").mkdir()
    (tmp_path / "app" / "dashboard" / "page.tsx").write_text(
        "export default function Dashboard() {}"
    )

    result = discover_routes_tool(str(tmp_path))
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert "/" in parsed["discovered_routes"]
    assert "/about" in parsed["discovered_routes"]
    assert "/dashboard" in parsed["discovered_routes"]
    assert parsed["framework"] == "Next.js"


def test_discover_routes_nextjs_pages_router(tmp_path):
    """Discovers Next.js Pages Router with index normalization."""
    (tmp_path / "package.json").write_text('{"dependencies": {"next": "14.0.0"}}')
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "index.tsx").write_text("export default function Home() {}")
    (tmp_path / "pages" / "settings.tsx").write_text(
        "export default function Settings() {}"
    )

    result = discover_routes_tool(str(tmp_path))
    parsed = json.loads(result)
    assert "/" in parsed["discovered_routes"]
    assert "/settings" in parsed["discovered_routes"]


def test_discover_routes_sveltekit(tmp_path):
    """Discovers SvelteKit +page.svelte routes."""
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"@sveltejs/kit": "2.0.0"}}'
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "routes").mkdir(parents=True)
    (tmp_path / "src" / "routes" / "+page.svelte").write_text("<h1>Home</h1>")
    (tmp_path / "src" / "routes" / "about").mkdir()
    (tmp_path / "src" / "routes" / "about" / "+page.svelte").write_text(
        "<h1>About</h1>"
    )

    result = discover_routes_tool(str(tmp_path))
    parsed = json.loads(result)
    assert parsed["framework"] == "SvelteKit"
    assert "/" in parsed["discovered_routes"]
    assert "/about" in parsed["discovered_routes"]


def test_discover_routes_react_router(tmp_path):
    """Discovers React Router route definitions via regex."""
    (tmp_path / "package.json").write_text('{"dependencies": {"react": "18.0.0"}}')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text(
        """
import { Route } from "react-router-dom";
<Route path="/dashboard" element={<Dashboard />} />
<Route path="/settings" element={<Settings />} />
"""
    )

    result = discover_routes_tool(str(tmp_path))
    parsed = json.loads(result)
    assert "/dashboard" in parsed["discovered_routes"]
    assert "/settings" in parsed["discovered_routes"]


def test_discover_routes_framework_override(tmp_path):
    """Explicit framework parameter skips auto-detection."""
    (tmp_path / "package.json").write_text('{"dependencies": {"next": "14.0.0"}}')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "routes").mkdir(parents=True)
    (tmp_path / "src" / "routes" / "+page.svelte").write_text("<h1>Home</h1>")

    # Force SvelteKit even though package.json says Next.js
    result = discover_routes_tool(str(tmp_path), framework="SvelteKit")
    parsed = json.loads(result)
    assert parsed["framework"] == "SvelteKit"
    assert "/" in parsed["discovered_routes"]


def test_discover_routes_services_detection(tmp_path):
    """Detects services from package.json dependencies."""
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"next": "14.0.0", "@supabase/supabase-js": "2.0.0", "stripe": "14.0.0"}}'
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")

    result = discover_routes_tool(str(tmp_path))
    parsed = json.loads(result)
    assert "supabase" in parsed["detected_services"]
    assert "stripe" in parsed["detected_services"]


def test_discover_routes_dynamic_segments(tmp_path):
    """Dynamic route segments are flagged in metadata."""
    (tmp_path / "package.json").write_text('{"dependencies": {"next": "14.0.0"}}')
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
    (tmp_path / "app" / "users").mkdir()
    (tmp_path / "app" / "users" / "[id]").mkdir()
    (tmp_path / "app" / "users" / "[id]" / "page.tsx").write_text(
        "export default function User() {}"
    )

    result = discover_routes_tool(str(tmp_path))
    parsed = json.loads(result)
    assert "/users/[id]" in parsed["discovered_routes"]
    assert parsed["route_metadata"]["/users/[id]"]["dynamic"] is True


def test_discover_routes_middleware_classification(tmp_path):
    """Next.js middleware classifies routes as public/protected."""
    (tmp_path / "package.json").write_text('{"dependencies": {"next": "14.0.0"}}')
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
    (tmp_path / "app" / "dashboard").mkdir()
    (tmp_path / "app" / "dashboard" / "page.tsx").write_text(
        "export default function Dashboard() {}"
    )
    (tmp_path / "middleware.ts").write_text(
        """
export const config = {
  matcher: ['/dashboard/:path*']
};
export default function middleware(req) {
  if (!isAuthed) redirect('/login');
}
"""
    )

    result = discover_routes_tool(str(tmp_path))
    parsed = json.loads(result)
    assert parsed["route_metadata"]["/dashboard"].get("visibility") == "protected"


def test_discover_routes_empty_project(tmp_path):
    """Empty project returns ['/'] fallback without crashing."""
    # Mock Playwright so the crawler fallback doesn't hit a real server
    mock_page = MagicMock()
    mock_page.query_selector_all.return_value = []
    mock_page.goto.return_value = None
    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium.launch.return_value = mock_browser

    mock_pw = MagicMock()
    mock_pw.__enter__ = MagicMock(return_value=mock_pw_instance)
    mock_pw.__exit__ = MagicMock(return_value=False)

    with patch(
        "playwright.sync_api.sync_playwright", return_value=mock_pw
    ):
        result = discover_routes_tool(str(tmp_path))
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert "/" in parsed["discovered_routes"]


def test_discover_routes_crawler_fallback(tmp_path):
    """With app_url and few static routes, attempts Playwright crawl."""
    mock_page = MagicMock()
    mock_page.query_selector_all.return_value = []
    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium.launch.return_value = mock_browser

    mock_pw = MagicMock()
    mock_pw.__enter__ = MagicMock(return_value=mock_pw_instance)
    mock_pw.__exit__ = MagicMock(return_value=False)

    with patch(
        "playwright.sync_api.sync_playwright", return_value=mock_pw
    ):
        result = discover_routes_tool(
            str(tmp_path), app_url="http://localhost:3000"
        )
    parsed = json.loads(result)
    assert parsed["status"] == "ok"


def test_discover_routes_invalid_path():
    """Non-existent path returns error status."""
    result = discover_routes_tool("/nonexistent/path/that/does/not/exist")
    parsed = json.loads(result)
    assert parsed["status"] == "error"
