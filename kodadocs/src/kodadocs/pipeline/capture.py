from playwright.sync_api import (
    sync_playwright,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)
from ..models import RunManifest
from pathlib import Path
import urllib.request
import urllib.error
from PIL import Image
from rich.console import Console


class AuthWallError(Exception):
    """Raised when an authentication wall is detected during capture."""

    pass


PII_DETECTION_JS = """() => {
    const regions = [];

    // --- Strategy 1: Input fields likely containing PII ---
    const piiInputs = document.querySelectorAll(
        'input[type="email"], input[type="tel"], ' +
        'input[name*="email"], input[name*="phone"], input[name*="address"], ' +
        'input[autocomplete="email"], input[autocomplete="tel"], ' +
        'input[autocomplete="name"], input[autocomplete="given-name"], ' +
        'input[autocomplete="family-name"], input[autocomplete="address"]'
    );
    piiInputs.forEach(el => {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
            regions.push({ x: rect.x, y: rect.y, width: rect.width, height: rect.height, type: 'input' });
        }
    });

    // --- Strategy 2: Profile / avatar / account CSS classes ---
    const profileEls = document.querySelectorAll(
        '[class*="profile"], [class*="avatar"], [class*="user-info"], ' +
        '[class*="account-info"], [class*="user-details"], ' +
        '[class*="billing"], [class*="gravatar"], [class*="display-name"]'
    );
    profileEls.forEach(el => {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
            regions.push({ x: rect.x, y: rect.y, width: rect.width, height: rect.height, type: 'profile' });
        }
    });

    // --- Strategy 3: Text nodes matching PII patterns ---
    const emailRe = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/;
    const phoneRe = /(?:\\+?1[-.\\s]?)?\\(?\\d{3}\\)?[-.\\s]?\\d{3}[-.\\s]?\\d{4}/;
    const keyRe = /(?:sk_|pk_|key_|token_|license_)[A-Za-z0-9_-]{8,}/;
    const hexRe = /[0-9a-f]{32,}/i;
    const moneyRe = /\\$\\d[\\d,]*\\.\\d{2}/;
    const maskedRe = /(?:sk_|pk_|key_|token_|license_)[A-Za-z0-9_-]*[\\u25cf\\u2022*]{3,}[A-Za-z0-9_-]*/;

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
        const text = walker.currentNode.textContent;
        if (emailRe.test(text) || phoneRe.test(text) || keyRe.test(text) ||
            hexRe.test(text) || moneyRe.test(text) || maskedRe.test(text)) {
            const parent = walker.currentNode.parentElement;
            if (parent) {
                const rect = parent.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    regions.push({ x: rect.x, y: rect.y, width: rect.width, height: rect.height, type: 'text' });
                }
            }
        }
    }

    // --- Strategy 4: Label-value pairs ---
    const sensitiveLabels = /\\b(name|email|phone|address|city|state|zip|country|billing|shipping|user\\s*id|site\\s*id|plugin\\s*id|public\\s*key|secret\\s*key|license\\s*key|api\\s*key|first\\s*name|last\\s*name|display\\s*name|company|card|payment|amount|total|ip\\s*address)\\b/i;

    // 4a: Table rows — <tr> with <th> label + <td> value
    document.querySelectorAll('tr').forEach(tr => {
        const th = tr.querySelector('th');
        const td = tr.querySelector('td');
        if (th && td && sensitiveLabels.test(th.textContent)) {
            const rect = td.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                regions.push({ x: rect.x, y: rect.y, width: rect.width, height: rect.height, type: 'label_value' });
            }
        }
    });

    // 4b: Definition lists — <dt> label + <dd> value
    document.querySelectorAll('dt').forEach(dt => {
        const dd = dt.nextElementSibling;
        if (dd && dd.tagName === 'DD' && sensitiveLabels.test(dt.textContent)) {
            const rect = dd.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                regions.push({ x: rect.x, y: rect.y, width: rect.width, height: rect.height, type: 'label_value' });
            }
        }
    });

    // 4c: <label> elements — via for attribute or next sibling
    document.querySelectorAll('label').forEach(label => {
        if (!sensitiveLabels.test(label.textContent)) return;
        const forId = label.getAttribute('for');
        let target = forId ? document.getElementById(forId) : label.nextElementSibling;
        if (target) {
            const rect = target.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                regions.push({ x: rect.x, y: rect.y, width: rect.width, height: rect.height, type: 'label_value' });
            }
        }
    });

    // 4d: Generic siblings — <span>/<strong> label + next sibling value
    document.querySelectorAll('span, strong, b').forEach(el => {
        if (!sensitiveLabels.test(el.textContent)) return;
        const sibling = el.nextElementSibling;
        if (sibling) {
            const text = (sibling.textContent || '').trim();
            if (text.length > 0 && text.length <= 50) {
                const rect = sibling.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    regions.push({ x: rect.x, y: rect.y, width: rect.width, height: rect.height, type: 'label_value' });
                }
            }
        }
    });

    // --- Deduplication: collapse overlapping regions by coordinate ---
    const seen = new Set();
    const deduped = [];
    for (const r of regions) {
        const key = Math.round(r.x) + ',' + Math.round(r.y) + ',' + Math.round(r.width) + ',' + Math.round(r.height);
        if (!seen.has(key)) {
            seen.add(key);
            deduped.push(r);
        }
    }
    return deduped;
}"""


def _check_app_reachable(app_url: str, timeout: float = 5.0) -> bool:
    """Quick check if app_url responds to an HTTP request."""
    try:
        req = urllib.request.Request(app_url, method="HEAD")
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except (urllib.error.URLError, OSError):
        return False


def smart_fill(page: Page, value: str, patterns: list):
    """Tries multiple selectors to fill a field."""
    console = Console()
    for pattern in patterns:
        try:
            locators = []
            if pattern == "password":
                locators = [
                    page.get_by_label("password", exact=False),
                    page.get_by_placeholder("password", exact=False),
                    page.locator("input[type='password']"),
                    page.locator("input[name='pwd']"),  # WordPress
                ]
            else:
                locators = [
                    page.get_by_label(pattern, exact=False),
                    page.get_by_placeholder(pattern, exact=False),
                    page.locator(f"input[name*='{pattern}']"),
                    page.locator(f"input[id*='{pattern}']"),
                    page.locator("input[type='email']"),
                    page.locator("input[name='log']"),  # WordPress
                ]

            for locator in locators:
                try:
                    if locator.count() > 0:
                        locator.first.fill(value)
                        return True
                except Exception:
                    continue
        except Exception as e:
            console.print(
                f"[yellow]Warning: Error trying pattern {pattern}: {e}[/yellow]"
            )
            continue
    return False


def _navigate_with_layered_wait(page: Page, url: str, timeout: int = 30000):
    """Layered wait: domcontentloaded -> short networkidle with cap."""
    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout, 10000))
    except PlaywrightTimeoutError:
        pass  # Capped networkidle — proceed after timeout
    page.wait_for_timeout(1000)


def _validate_screenshot(image_path: Path, console: Console, route: str) -> bool:
    """Validate screenshot has sufficient content via pixel entropy."""
    if image_path.stat().st_size < 5000:
        console.print(
            f"  [yellow]Warning: {route} screenshot is very small ({image_path.stat().st_size} bytes).[/yellow]"
        )
        return False
    try:
        img = Image.open(image_path)
        entropy = img.entropy()
        if entropy < 1.0:
            console.print(
                f"  [yellow]Rejecting {route}: low entropy ({entropy:.2f}) — likely blank page.[/yellow]"
            )
            return False
    except Exception:
        pass
    return True


def _detect_auth_wall(page: Page, original_url: str) -> dict:
    """Detect if the current page is an authentication wall.

    Performs two checks on the already-loaded page state:
    1. URL redirect detection — did the page redirect to a login path?
    2. Login form detection — does the page contain a login form?

    Returns {"detected": bool, "reason": str, "method": str}.
    """
    from urllib.parse import urlparse

    current_url = page.url
    original_path = urlparse(original_url).path.lower()
    current_path = urlparse(current_url).path.lower()

    # Check 1: URL redirect to a login path
    login_path_fragments = [
        "/login",
        "/signin",
        "/sign-in",
        "/auth",
        "/wp-login",
        "/sso",
        "/cas/login",
    ]
    redirected_to_login = any(
        frag in current_path for frag in login_path_fragments
    ) and not any(frag in original_path for frag in login_path_fragments)
    if redirected_to_login:
        return {
            "detected": True,
            "reason": f"Redirected from {original_url} to {current_url}",
            "method": "url_redirect",
        }

    # Check 2: Login form detection (password + username/email field)
    try:
        has_password = page.locator("input[type='password']").count() > 0
        has_username = (
            page.locator("input[type='email']").count() > 0
            or page.locator(
                "input[name*='user'], input[name*='email'], input[name*='login']"
            ).count()
            > 0
            or page.locator(
                "input[id*='user'], input[id*='email'], input[id*='login']"
            ).count()
            > 0
        )
        if has_password and has_username:
            return {
                "detected": True,
                "reason": "Page contains a login form (password and username/email fields detected)",
                "method": "form_detection",
            }
    except Exception:
        pass  # If DOM queries fail, skip form detection

    return {"detected": False, "reason": "", "method": ""}


def _check_login_success(page: Page, auth_url: str) -> bool:
    """Check if login succeeded by verifying no auth wall is present."""
    result = _detect_auth_wall(page, auth_url)
    return not result["detected"]


# Patterns to exclude from authenticated route discovery
_AUTH_CRAWL_EXCLUDE_PATTERNS = [
    "/logout",
    "/signout",
    "/sign-out",
    "/login",
    "/signin",
    "/sign-in",
    "/auth/",
    "/api/",
    "/static/",
    "/assets/",
    "/_next/",
    "/favicon",
    "/manifest",
    "/sw.js",
]

_STATIC_EXTENSIONS = {
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".map",
    ".json",
    ".xml",
    ".txt",
    ".pdf",
}

_MAX_AUTHENTICATED_ROUTES = 50


def _discover_authenticated_routes(
    page: Page, app_url: str, max_depth: int = 1
) -> list[str]:
    """Crawl links from the authenticated landing page to discover routes.

    Navigates to app root (authenticated), extracts all <a href> links,
    filters out logout/auth/static/external, and optionally visits each
    discovered page to extract sub-links (breadth-first, depth=1).

    Returns sorted deduplicated list of route paths.
    """
    from urllib.parse import urlparse

    console = Console()
    parsed_app = urlparse(app_url)
    app_origin = f"{parsed_app.scheme}://{parsed_app.netloc}"

    def _extract_links(p: Page) -> list[str]:
        """Extract all href values from <a> tags on the current page."""
        try:
            return p.evaluate(
                """() => {
                    return Array.from(document.querySelectorAll('a[href]'))
                        .map(a => a.href)
                        .filter(href => href && !href.startsWith('javascript:'));
                }"""
            )
        except Exception:
            return []

    def _is_valid_route(href: str) -> bool:
        """Check if href is a valid internal route worth crawling."""
        parsed = urlparse(href)

        # Must be same origin
        href_origin = f"{parsed.scheme}://{parsed.netloc}"
        if href_origin != app_origin:
            return False

        path = parsed.path.lower()

        # Skip anchors-only
        if not path or path == "#":
            return False

        # Skip excluded patterns
        for pattern in _AUTH_CRAWL_EXCLUDE_PATTERNS:
            if pattern in path:
                return False

        # Skip static file extensions
        suffix = Path(path).suffix.lower()
        if suffix in _STATIC_EXTENSIONS:
            return False

        return True

    def _href_to_route(href: str) -> str:
        """Convert absolute href to route path."""
        parsed = urlparse(href)
        route = parsed.path
        if parsed.query:
            route += f"?{parsed.query}"
        return route if route else "/"

    # Navigate to app root (authenticated session should be active)
    try:
        _navigate_with_layered_wait(page, app_url)
    except Exception as e:
        console.print(
            f"[yellow]Could not navigate to {app_url} for route discovery: {e}[/yellow]"
        )
        return []

    # Depth 0: extract links from landing page
    raw_links = _extract_links(page)
    routes: set[str] = set()

    for href in raw_links:
        if _is_valid_route(href):
            routes.add(_href_to_route(href))

    # Depth 1: visit each discovered route and extract sub-links
    if max_depth >= 1:
        depth0_routes = list(routes)[:_MAX_AUTHENTICATED_ROUTES]
        for route in depth0_routes:
            if len(routes) >= _MAX_AUTHENTICATED_ROUTES:
                break
            target = f"{app_url.rstrip('/')}{route}"
            try:
                _navigate_with_layered_wait(page, target)
                sub_links = _extract_links(page)
                for href in sub_links:
                    if _is_valid_route(href):
                        routes.add(_href_to_route(href))
                        if len(routes) >= _MAX_AUTHENTICATED_ROUTES:
                            break
            except Exception:
                continue

    # Cap and return
    result = sorted(routes)[:_MAX_AUTHENTICATED_ROUTES]
    if result:
        console.print(
            f"Discovered [bold]{len(result)}[/bold] route(s) from authenticated crawl"
        )
    return result


def capture_step(manifest: RunManifest):
    console = Console()
    app_url = manifest.config.app_url
    auth = manifest.config.auth
    project_path = manifest.config.project_path
    screenshots_dir = project_path / ".kodadocs" / "screenshots"
    screenshots_dir.mkdir(exist_ok=True, parents=True)
    custom_screenshots_dir = project_path / ".kodadocs" / "custom_screenshots"

    storage_state_path = project_path / ".kodadocs" / "storage_state.json"

    # Pre-check: is the app reachable?
    if not _check_app_reachable(app_url):
        console.print(
            f"[yellow]Could not reach {app_url}. Skipping screenshot capture.[/yellow]"
        )
        console.print(
            "[yellow]Tip: Start your app first, or use --url to specify the correct URL.[/yellow]"
        )
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context_args = {"viewport": {"width": 1280, "height": 720}}
        if storage_state_path.exists():
            console.print(
                f"[cyan]Using saved session from {storage_state_path.name}[/cyan]"
            )
            context_args["storage_state"] = str(storage_state_path)

        context = browser.new_context(**context_args)
        page = context.new_page()

        # 1. Authentication (only if no storage state or forced)
        if auth and auth.auth_url and not storage_state_path.exists():
            console.print(f"Attempting smart login at [blue]{auth.auth_url}[/blue]...")
            try:
                _navigate_with_layered_wait(page, auth.auth_url, timeout=60000)

                user_filled = smart_fill(
                    page, auth.username, ["username", "email", "login", "user"]
                )
                pass_filled = smart_fill(page, auth.password, ["password", "pass"])

                if user_filled and pass_filled:
                    console.print("Found login fields, submitting...")
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(3000)

                    if not _check_login_success(page, auth.auth_url):
                        browser.close()
                        raise AuthWallError(
                            f"Login failed: still on login page after submitting credentials "
                            f"at {auth.auth_url}. Please verify your credentials. "
                            f"Use 'kodadocs init' to reconfigure or pass --user / --pass flags."
                        )

                    context.storage_state(path=str(storage_state_path))
                else:
                    console.print(
                        "[yellow]Could not automatically find login fields. Proceeding anyway...[/yellow]"
                    )
            except AuthWallError:
                raise
            except PlaywrightTimeoutError:
                console.print(f"[red]Login page timeout at {auth.auth_url}[/red]")
            except Exception as e:
                console.print(f"[red]Login attempt failed: {e}[/red]")

        # WordPress runtime sidebar discovery
        wp_meta = manifest.route_metadata.get("__wp_text_domain__")
        if wp_meta:
            from .discovery import _discover_wp_sidebar_routes

            sidebar_routes = _discover_wp_sidebar_routes(
                page, app_url, wp_meta["text_domain"]
            )
            if sidebar_routes:
                existing = set(manifest.discovered_routes)
                new_routes = [r for r in sidebar_routes if r not in existing]
                if new_routes:
                    manifest.discovered_routes = sorted(existing | set(sidebar_routes))
                    console.print(
                        f"Found {len(new_routes)} additional route(s) from admin sidebar"
                    )
            manifest.route_metadata.pop("__wp_text_domain__", None)

        # Generic post-auth DOM crawl for non-file-based-routing apps
        if auth and auth.auth_url and len(manifest.discovered_routes) <= 1:
            console.print(
                "[cyan]Few routes found pre-auth — running authenticated crawl...[/cyan]"
            )
            crawled_routes = _discover_authenticated_routes(page, app_url)
            if crawled_routes:
                existing = set(manifest.discovered_routes)
                new_routes = [r for r in crawled_routes if r not in existing]
                if new_routes:
                    manifest.discovered_routes = sorted(existing | set(crawled_routes))
                    console.print(
                        f"Added [bold]{len(new_routes)}[/bold] route(s) from authenticated crawl"
                    )

        # 2. Capture Loop
        first_route_checked = False
        for route in manifest.discovered_routes:
            target_url = f"{app_url.rstrip('/')}{route}"
            console.print(f"Capturing screenshot for [cyan]{route}[/cyan]...")

            safe_route = route.strip("/").replace("/", "-") or "index"
            image_path = screenshots_dir / f"{safe_route}.png"

            # Check for user-provided custom screenshot override (separate directory)
            custom_path = custom_screenshots_dir / f"{safe_route}.png"
            if custom_path.exists() and custom_path.stat().st_size > 1024:
                console.print(f"  [green]Using custom screenshot for {route}[/green]")
                manifest.screenshots[route] = str(custom_path.relative_to(project_path))
                continue

            try:
                _navigate_with_layered_wait(page, target_url)

                # Auth wall check on first real route
                if not first_route_checked:
                    first_route_checked = True
                    wall = _detect_auth_wall(page, target_url)
                    if wall["detected"]:
                        browser.close()
                        if auth and auth.auth_url:
                            raise AuthWallError(
                                f"Authentication wall detected after login: {wall['reason']}. "
                                f"Your saved session may have expired or login credentials may be invalid. "
                                f"Delete .kodadocs/storage_state.json and re-run, or reconfigure with 'kodadocs init'."
                            )
                        else:
                            raise AuthWallError(
                                f"Authentication wall detected: {wall['reason']}. "
                                f"Your app appears to require login. Run 'kodadocs init' to configure "
                                f"authentication, or pass --user / --pass flags to 'kodadocs generate'."
                            )

                page.screenshot(path=image_path, full_page=True)

                if not _validate_screenshot(image_path, console, route):
                    console.print(
                        f"  [yellow]Screenshot for {route} may be blank or low quality.[/yellow]"
                    )

                try:
                    is_wordpress = manifest.config.framework == "WordPress"
                    elements = page.evaluate(
                        """(isWP) => {
                        const selectors = 'button, a, input, select, textarea, [role="button"], [role="link"], h1, h2, h3, img[alt]';
                        // For WordPress, scope to main content area to skip admin bar/sidebar
                        const root = isWP
                            ? (document.querySelector('#wpbody-content') || document.querySelector('#wpbody') || document)
                            : document;
                        const interactive = root.querySelectorAll(selectors);
                        return Array.from(interactive).map(el => {
                            const rect = el.getBoundingClientRect();
                            return {
                                role: el.tagName.toLowerCase(),
                                name: (el.textContent || '').trim().substring(0, 100) || el.getAttribute('aria-label') || el.getAttribute('alt') || '',
                                bounds: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
                            };
                        }).filter(el => el.name && el.bounds.width > 0 && el.bounds.height > 0 && el.bounds.y >= 0);
                    }""",
                        is_wordpress,
                    )
                    manifest.dom_elements[route] = elements
                except Exception as e:
                    console.print(
                        f"  [yellow]DOM element extraction failed for {route}: {e}[/yellow]"
                    )
                    manifest.dom_elements[route] = []

                # PII region detection
                if manifest.config.blur_pii:
                    try:
                        pii_regions = page.evaluate(PII_DETECTION_JS)
                        if pii_regions:
                            manifest.pii_regions[route] = pii_regions
                    except Exception as e:
                        console.print(
                            f"  [yellow]PII detection failed for {route}: {e}[/yellow]"
                        )

                manifest.screenshots[route] = str(image_path.relative_to(project_path))

            except AuthWallError:
                raise
            except PlaywrightTimeoutError:
                console.print(f"  [red]Timeout capturing {route}[/red]")
            except Exception as e:
                console.print(f"  [red]Failed to capture {route}: {e}[/red]")

        browser.close()
