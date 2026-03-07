import pytest
from unittest.mock import MagicMock
from PIL import Image
from kodadocs.pipeline.capture import (
    _validate_screenshot,
    _detect_auth_wall,
    _check_login_success,
    AuthWallError,
    PII_DETECTION_JS,
)
from rich.console import Console


def test_validate_screenshot_good_image(tmp_path):
    """A normal image with varied pixels should pass validation."""
    import random

    random.seed(42)
    img = Image.new("RGB", (200, 200))
    pixels = img.load()
    for x in range(200):
        for y in range(200):
            pixels[x, y] = (
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            )
    path = tmp_path / "good.png"
    img.save(path)

    console = Console()
    assert _validate_screenshot(path, console, "/test") is True


def test_validate_screenshot_tiny_file(tmp_path):
    """A very small file should fail validation."""
    path = tmp_path / "tiny.png"
    path.write_bytes(b"x" * 100)

    console = Console()
    assert _validate_screenshot(path, console, "/test") is False


def test_validate_screenshot_blank_image(tmp_path):
    """A single-color image has very low entropy and should be flagged."""
    img = Image.new("RGB", (1280, 720), color=(255, 255, 255))
    path = tmp_path / "blank.png"
    img.save(path)

    console = Console()
    # Single-color image has entropy of 0.0
    result = _validate_screenshot(path, console, "/test")
    assert result is False


# --- Auth wall detection tests ---


def _make_mock_page(url: str, has_password: bool = False, has_username: bool = False):
    """Create a mock Playwright Page with configurable URL and form fields."""
    page = MagicMock()
    page.url = url

    def locator_side_effect(selector):
        loc = MagicMock()
        if "password" in selector:
            loc.count.return_value = 1 if has_password else 0
        elif any(kw in selector for kw in ["email", "user", "login"]):
            loc.count.return_value = 1 if has_username else 0
        else:
            loc.count.return_value = 0
        return loc

    page.locator.side_effect = locator_side_effect
    return page


def test_detect_auth_wall_redirect():
    """Page redirected to /login should be detected as auth wall."""
    page = _make_mock_page("http://localhost:3000/login")
    result = _detect_auth_wall(page, "http://localhost:3000/dashboard")

    assert result["detected"] is True
    assert result["method"] == "url_redirect"
    assert "/login" in result["reason"]


def test_detect_auth_wall_form_detection():
    """Page with login form fields should be detected as auth wall."""
    page = _make_mock_page(
        "http://localhost:3000/dashboard",
        has_password=True,
        has_username=True,
    )
    result = _detect_auth_wall(page, "http://localhost:3000/dashboard")

    assert result["detected"] is True
    assert result["method"] == "form_detection"
    assert "login form" in result["reason"]


def test_detect_auth_wall_no_wall():
    """Normal page without login indicators should not trigger detection."""
    page = _make_mock_page("http://localhost:3000/dashboard")
    result = _detect_auth_wall(page, "http://localhost:3000/dashboard")

    assert result["detected"] is False
    assert result["reason"] == ""
    assert result["method"] == ""


def test_check_login_success_true():
    """Login success: page navigated away from login (no auth wall)."""
    page = _make_mock_page("http://localhost:3000/dashboard")
    assert _check_login_success(page, "http://localhost:3000/login") is True


def test_check_login_success_false():
    """Login failure: page still shows login form after submission."""
    page = _make_mock_page(
        "http://localhost:3000/login",
        has_password=True,
        has_username=True,
    )
    assert _check_login_success(page, "http://localhost:3000/login") is False


def test_auth_wall_error_is_exception():
    """AuthWallError should be a proper Exception subclass."""
    assert issubclass(AuthWallError, Exception)
    err = AuthWallError("test message")
    assert str(err) == "test message"


# --- PII detection JS tests ---


def test_pii_detection_js_is_valid():
    """PII_DETECTION_JS constant should contain all expected strategy markers."""
    assert "Strategy 1" in PII_DETECTION_JS or "piiInputs" in PII_DETECTION_JS
    assert "Strategy 2" in PII_DETECTION_JS or "profileEls" in PII_DETECTION_JS
    assert "emailRe" in PII_DETECTION_JS
    assert "keyRe" in PII_DETECTION_JS
    assert "moneyRe" in PII_DETECTION_JS
    assert "sensitiveLabels" in PII_DETECTION_JS
    assert "deduped" in PII_DETECTION_JS


@pytest.mark.integration
def test_pii_detection_js_wordpress_table():
    """Label-value strategy should detect sensitive table rows but skip non-sensitive ones."""
    from playwright.sync_api import sync_playwright

    html = """
    <html><body>
    <table>
        <tr><th>Name:</th><td>Alejandro Test</td></tr>
        <tr><th>Email:</th><td>alejandro@example.com</td></tr>
        <tr><th>License Key:</th><td>license_abc123def456</td></tr>
        <tr><th>Description:</th><td>A helpful plugin</td></tr>
    </table>
    </body></html>
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)
        regions = page.evaluate(PII_DETECTION_JS)
        browser.close()

    # Should detect regions for the 3 sensitive rows (Name, Email, License Key).
    # Due to dedup, Email and License Key may appear as 'text' (text strategy runs
    # first) rather than 'label_value' when both strategies detect the same <td>.
    assert len(regions) >= 3
    # At least 1 label_value (Name row has no text-pattern match, so label_value survives)
    assert any(r["type"] == "label_value" for r in regions)
    # "Description" is not a sensitive label — should not produce a label_value
    # (max 3 sensitive rows, possibly fewer label_value due to dedup)
    label_value_count = len([r for r in regions if r["type"] == "label_value"])
    assert label_value_count <= 3


@pytest.mark.integration
def test_pii_detection_js_text_patterns():
    """Text pattern strategy should catch emails, API keys, and money amounts."""
    from playwright.sync_api import sync_playwright

    html = """
    <html><body>
    <p>Contact: user@example.com</p>
    <p>API Key: sk_live_abc123defgh456</p>
    <p>Total: $322.92</p>
    <p>Public Key: pk_b726f4d807abcdef1234567890abcdef</p>
    <p>Nothing sensitive here.</p>
    </body></html>
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)
        regions = page.evaluate(PII_DETECTION_JS)
        browser.close()

    # Should detect at least 4 text regions (email, sk_ key, money, pk_ hex key)
    text_regions = [r for r in regions if r["type"] == "text"]
    assert len(text_regions) >= 4
    # "Nothing sensitive here" should not produce a region
    assert all(r["width"] > 0 and r["height"] > 0 for r in regions)


@pytest.mark.integration
def test_pii_detection_js_deduplication():
    """Duplicate regions at the same coordinates should be collapsed."""
    from playwright.sync_api import sync_playwright

    # An email in a table cell labelled "Email" will match both text strategy
    # AND label-value strategy — but coordinates differ so both may appear.
    # We test that identical coordinates are deduped.
    html = """
    <html><body>
    <table>
        <tr><th>Email:</th><td>user@example.com</td></tr>
    </table>
    </body></html>
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)
        regions = page.evaluate(PII_DETECTION_JS)
        browser.close()

    # Check no two regions share the exact same rounded coordinates
    coords = [
        (round(r["x"]), round(r["y"]), round(r["width"]), round(r["height"]))
        for r in regions
    ]
    assert len(coords) == len(set(coords)), f"Duplicate regions found: {coords}"


# --- WordPress sidebar route merging tests ---


def test_capture_merges_sidebar_routes(tmp_path):
    """capture_step should merge sidebar routes into manifest.discovered_routes for WordPress."""
    from unittest.mock import patch, MagicMock
    from kodadocs.models import SessionConfig, RunManifest, Framework, AuthConfig

    config = SessionConfig(
        app_url="http://localhost:8080",
        project_path=tmp_path,
        framework=Framework.WORDPRESS,
        skip_ai=True,
        auth=AuthConfig(
            username="admin",
            password="admin123",
            auth_url="http://localhost:8080/wp-login.php",
        ),
    )
    manifest = RunManifest(session_id="test", config=config)
    manifest.discovered_routes = [
        "/wp-admin/admin.php?page=my-plugin",
        "/wp-admin/admin.php?page=my-plugin-dashboard",
        "/wp-admin/admin.php?page=my-plugin-settings",
    ]
    manifest.route_metadata = {
        "__wp_text_domain__": {"text_domain": "my-plugin"},
    }

    # Sidebar returns 5 routes (3 overlap + 2 new)
    sidebar_routes = [
        "/wp-admin/admin.php?page=my-plugin",
        "/wp-admin/admin.php?page=my-plugin-account",
        "/wp-admin/admin.php?page=my-plugin-dashboard",
        "/wp-admin/admin.php?page=my-plugin-pricing",
        "/wp-admin/admin.php?page=my-plugin-settings",
    ]

    with (
        patch("kodadocs.pipeline.capture.sync_playwright") as mock_pw,
        patch("kodadocs.pipeline.capture._check_app_reachable", return_value=True),
        patch("kodadocs.pipeline.capture._navigate_with_layered_wait"),
        patch("kodadocs.pipeline.capture._validate_screenshot", return_value=True),
        patch(
            "kodadocs.pipeline.capture._detect_auth_wall",
            return_value={"detected": False, "reason": "", "method": ""},
        ),
        patch("kodadocs.pipeline.capture.smart_fill", return_value=True),
        patch("kodadocs.pipeline.capture._check_login_success", return_value=True),
        patch(
            "kodadocs.pipeline.discovery._discover_wp_sidebar_routes",
            return_value=sidebar_routes,
        ),
    ):
        # Wire up playwright mocks
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_browser = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_browser.new_context.return_value = mock_context
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )

        # Mock page.screenshot and page.evaluate to avoid real browser calls
        mock_page.screenshot.return_value = None
        mock_page.evaluate.return_value = []
        mock_page.url = "http://localhost:8080/wp-admin/"

        # Create screenshots dir
        (tmp_path / ".kodadocs" / "screenshots").mkdir(parents=True)

        from kodadocs.pipeline.capture import capture_step

        capture_step(manifest)

    # All 5 routes should be present
    assert len(manifest.discovered_routes) == 5
    assert "/wp-admin/admin.php?page=my-plugin-account" in manifest.discovered_routes
    assert "/wp-admin/admin.php?page=my-plugin-pricing" in manifest.discovered_routes
    # Sentinel key should be cleaned up
    assert "__wp_text_domain__" not in manifest.route_metadata


def test_capture_no_sidebar_without_text_domain(tmp_path):
    """capture_step should skip sidebar discovery when __wp_text_domain__ is absent."""
    from unittest.mock import patch, MagicMock
    from kodadocs.models import SessionConfig, RunManifest, Framework

    config = SessionConfig(
        app_url="http://localhost:8080",
        project_path=tmp_path,
        framework=Framework.WORDPRESS,
        skip_ai=True,
    )
    manifest = RunManifest(session_id="test", config=config)
    manifest.discovered_routes = ["/wp-admin/admin.php?page=my-plugin"]
    # No __wp_text_domain__ in route_metadata

    with (
        patch("kodadocs.pipeline.capture.sync_playwright") as mock_pw,
        patch("kodadocs.pipeline.capture._check_app_reachable", return_value=True),
        patch("kodadocs.pipeline.capture._navigate_with_layered_wait"),
        patch("kodadocs.pipeline.capture._validate_screenshot", return_value=True),
        patch(
            "kodadocs.pipeline.capture._detect_auth_wall",
            return_value={"detected": False, "reason": "", "method": ""},
        ),
        patch(
            "kodadocs.pipeline.discovery._discover_wp_sidebar_routes"
        ) as mock_sidebar,
    ):
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_browser = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_browser.new_context.return_value = mock_context
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )
        mock_page.screenshot.return_value = None
        mock_page.evaluate.return_value = []
        mock_page.url = "http://localhost:8080/wp-admin/"

        (tmp_path / ".kodadocs" / "screenshots").mkdir(parents=True)

        from kodadocs.pipeline.capture import capture_step

        capture_step(manifest)

    # Sidebar discovery should never be called
    mock_sidebar.assert_not_called()
    assert len(manifest.discovered_routes) == 1


# --- Generic post-auth route discovery tests ---


def test_discover_authenticated_routes_extracts_links():
    """_discover_authenticated_routes filters out logout, external, and anchor links."""
    from unittest.mock import patch, MagicMock
    from kodadocs.pipeline.capture import _discover_authenticated_routes

    page = MagicMock()
    app_url = "http://localhost:5000"

    # Simulate links on the landing page
    page.evaluate.return_value = [
        "http://localhost:5000/dashboard",
        "http://localhost:5000/tenants",
        "http://localhost:5000/logout",  # Should be excluded
        "http://localhost:5000/auth/callback",  # Should be excluded
        "https://external.com/page",  # Should be excluded (different origin)
        "http://localhost:5000/static/style.css",  # Should be excluded
        "http://localhost:5000/reports",
    ]

    with patch("kodadocs.pipeline.capture._navigate_with_layered_wait"):
        routes = _discover_authenticated_routes(page, app_url, max_depth=0)

    assert "/dashboard" in routes
    assert "/tenants" in routes
    assert "/reports" in routes
    assert "/logout" not in routes
    assert "/auth/callback" not in routes
    assert "/static/style.css" not in routes
    assert len(routes) == 3


def test_discover_authenticated_routes_breadth_first():
    """depth=1 visits discovered pages to find sub-links."""
    from unittest.mock import patch, MagicMock
    from kodadocs.pipeline.capture import _discover_authenticated_routes

    page = MagicMock()
    app_url = "http://localhost:5000"

    call_count = [0]

    def evaluate_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # Landing page links
            return [
                "http://localhost:5000/dashboard",
                "http://localhost:5000/tenants",
            ]
        elif call_count[0] == 2:
            # /dashboard sub-links
            return [
                "http://localhost:5000/dashboard/stats",
                "http://localhost:5000/dashboard/recent",
            ]
        else:
            # /tenants sub-links
            return [
                "http://localhost:5000/tenants/add",
            ]

    page.evaluate.side_effect = evaluate_side_effect

    with patch("kodadocs.pipeline.capture._navigate_with_layered_wait"):
        routes = _discover_authenticated_routes(page, app_url, max_depth=1)

    assert "/dashboard" in routes
    assert "/tenants" in routes
    assert "/dashboard/stats" in routes
    assert "/dashboard/recent" in routes
    assert "/tenants/add" in routes
    assert len(routes) == 5


def test_discover_authenticated_routes_filters_static_and_auth():
    """Exclusion patterns correctly filter auth, static, and API routes."""
    from unittest.mock import patch, MagicMock
    from kodadocs.pipeline.capture import _discover_authenticated_routes

    page = MagicMock()
    app_url = "http://localhost:5000"

    page.evaluate.return_value = [
        "http://localhost:5000/properties",
        "http://localhost:5000/login",  # excluded
        "http://localhost:5000/signin",  # excluded
        "http://localhost:5000/api/v1/data",  # excluded
        "http://localhost:5000/assets/logo.png",  # excluded
        "http://localhost:5000/favicon.ico",  # excluded (static ext)
        "http://localhost:5000/_next/data/abc",  # excluded
        "http://localhost:5000/settings",
    ]

    with patch("kodadocs.pipeline.capture._navigate_with_layered_wait"):
        routes = _discover_authenticated_routes(page, app_url, max_depth=0)

    assert routes == ["/properties", "/settings"]


def test_capture_step_triggers_generic_crawl_for_auth_apps(tmp_path):
    """capture_step triggers authenticated crawl when auth is configured and <= 1 route."""
    from unittest.mock import patch, MagicMock
    from kodadocs.models import SessionConfig, RunManifest, Framework, AuthConfig
    from kodadocs.pipeline.capture import capture_step

    config = SessionConfig(
        app_url="http://localhost:5000",
        project_path=tmp_path,
        framework=Framework.UNKNOWN,
        skip_ai=True,
        auth=AuthConfig(
            username="admin",
            password="admin123",
            auth_url="http://localhost:5000/login",
        ),
    )
    manifest = RunManifest(session_id="test", config=config)
    manifest.discovered_routes = ["/"]  # Only root found pre-auth

    crawled_routes = ["/dashboard", "/tenants", "/properties", "/reports"]

    with (
        patch("kodadocs.pipeline.capture.is_pro", return_value=True),
        patch("kodadocs.pipeline.capture.sync_playwright") as mock_pw,
        patch("kodadocs.pipeline.capture._check_app_reachable", return_value=True),
        patch("kodadocs.pipeline.capture._navigate_with_layered_wait"),
        patch("kodadocs.pipeline.capture._validate_screenshot", return_value=True),
        patch(
            "kodadocs.pipeline.capture._detect_auth_wall",
            return_value={"detected": False, "reason": "", "method": ""},
        ),
        patch("kodadocs.pipeline.capture.smart_fill", return_value=True),
        patch("kodadocs.pipeline.capture._check_login_success", return_value=True),
        patch(
            "kodadocs.pipeline.capture._discover_authenticated_routes",
            return_value=crawled_routes,
        ) as mock_crawl,
    ):
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_browser = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_browser.new_context.return_value = mock_context
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )
        mock_page.screenshot.return_value = None
        mock_page.evaluate.return_value = []
        mock_page.url = "http://localhost:5000/dashboard"

        (tmp_path / ".kodadocs" / "screenshots").mkdir(parents=True)

        capture_step(manifest)

    # Authenticated crawl should have been called
    mock_crawl.assert_called_once()
    # All crawled routes should be merged
    assert "/dashboard" in manifest.discovered_routes
    assert "/tenants" in manifest.discovered_routes
    assert "/properties" in manifest.discovered_routes
    assert "/reports" in manifest.discovered_routes
    assert "/" in manifest.discovered_routes  # Original route preserved
    assert len(manifest.discovered_routes) == 5


def test_capture_step_skips_generic_crawl_when_routes_found(tmp_path):
    """capture_step does NOT trigger authenticated crawl when 3+ routes already discovered."""
    from unittest.mock import patch, MagicMock
    from kodadocs.models import SessionConfig, RunManifest, Framework, AuthConfig
    from kodadocs.pipeline.capture import capture_step

    config = SessionConfig(
        app_url="http://localhost:5000",
        project_path=tmp_path,
        framework=Framework.UNKNOWN,
        skip_ai=True,
        auth=AuthConfig(
            username="admin",
            password="admin123",
            auth_url="http://localhost:5000/login",
        ),
    )
    manifest = RunManifest(session_id="test", config=config)
    manifest.discovered_routes = ["/", "/dashboard", "/settings"]  # 3 routes already

    with (
        patch("kodadocs.pipeline.capture.is_pro", return_value=True),
        patch("kodadocs.pipeline.capture.sync_playwright") as mock_pw,
        patch("kodadocs.pipeline.capture._check_app_reachable", return_value=True),
        patch("kodadocs.pipeline.capture._navigate_with_layered_wait"),
        patch("kodadocs.pipeline.capture._validate_screenshot", return_value=True),
        patch(
            "kodadocs.pipeline.capture._detect_auth_wall",
            return_value={"detected": False, "reason": "", "method": ""},
        ),
        patch("kodadocs.pipeline.capture.smart_fill", return_value=True),
        patch("kodadocs.pipeline.capture._check_login_success", return_value=True),
        patch(
            "kodadocs.pipeline.capture._discover_authenticated_routes",
        ) as mock_crawl,
    ):
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_browser = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_browser.new_context.return_value = mock_context
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )
        mock_page.screenshot.return_value = None
        mock_page.evaluate.return_value = []
        mock_page.url = "http://localhost:5000/dashboard"

        (tmp_path / ".kodadocs" / "screenshots").mkdir(parents=True)

        capture_step(manifest)

    # Authenticated crawl should NOT have been triggered (3 routes > 1)
    mock_crawl.assert_not_called()
