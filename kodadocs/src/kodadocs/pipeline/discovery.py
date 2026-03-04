from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Set, Dict, Any, Optional, TYPE_CHECKING
from rich.console import Console
from ..models import RunManifest, Framework
from ..utils.framework import (
    detect_frameworks,
    detect_services,
    detect_ui_components,
    detect_deployment,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Files that are Next.js internals, not user-facing pages
NEXTJS_INTERNAL_FILES = {
    "loading",
    "error",
    "not-found",
    "layout",
    "template",
    "default",
    "global-error",
}


def _extract_text_domain(project_path: Path) -> Optional[str]:
    """Extract the WordPress text domain from PHP plugin headers."""
    for php_file in project_path.rglob("*.php"):
        content = php_file.read_text(errors="ignore")
        match = re.search(r"Text Domain:\s*([\w-]+)", content)
        if match:
            return match.group(1)
    return None


def _discover_wordpress_routes(project_path: Path) -> List[str]:
    """Discover WordPress admin pages by scanning PHP plugin headers and menu registrations."""
    text_domain = _extract_text_domain(project_path)

    if not text_domain:
        return []

    slugs: Set[str] = set()
    for php_file in project_path.rglob("*.php"):
        content = php_file.read_text(errors="ignore")
        if "add_menu_page" in content or "add_submenu_page" in content:
            matches = re.findall(
                rf"['\"]({re.escape(text_domain)}(?:-[\w]+)*)['\"]", content
            )
            slugs.update(matches)

    return [f"/wp-admin/admin.php?page={slug}" for slug in sorted(slugs)]


def _discover_wp_sidebar_routes(
    page: Page, app_url: str, text_domain: str
) -> List[str]:
    """Scrape the live WordPress admin sidebar for plugin routes.

    Navigates to /wp-admin/ on an already-authenticated Page and extracts
    sidebar links whose ``page=`` query parameter starts with the plugin's
    text domain.  Returns a sorted, deduplicated list in
    ``/wp-admin/admin.php?page={slug}`` format.

    Returns an empty list on any failure (graceful degradation).
    """
    try:
        admin_url = f"{app_url.rstrip('/')}/wp-admin/"
        page.goto(admin_url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass  # capped networkidle — proceed after timeout

        hrefs: list[str] = page.evaluate("""() => {
            const links = document.querySelectorAll('#adminmenu a[href]');
            return Array.from(links).map(a => a.getAttribute('href'));
        }""")

        slugs: set[str] = set()
        for href in hrefs:
            if not href or "page=" not in href:
                continue
            # Extract the page= parameter value
            match = re.search(r"[?&]page=([^&]+)", href)
            if match:
                slug = match.group(1)
                if slug.startswith(text_domain):
                    slugs.add(slug)

        return [f"/wp-admin/admin.php?page={slug}" for slug in sorted(slugs)]
    except Exception:
        return []


def _strip_route_groups(route: str) -> str:
    """Remove Next.js/SvelteKit route groups like (auth), (marketing) from a route path."""
    return "/".join(
        [p for p in route.split("/") if not (p.startswith("(") and p.endswith(")"))]
    )


def _is_dynamic_segment(segment: str) -> bool:
    """Check if a route segment is a dynamic parameter like [slug] or [...catchAll]."""
    return segment.startswith("[") and segment.endswith("]")


def _route_has_dynamic_segments(route: str) -> bool:
    """Check if any segment in the route is dynamic."""
    return any(_is_dynamic_segment(seg) for seg in route.split("/") if seg)


def _discover_nextjs_routes(
    project_path: Path, route_metadata: Dict[str, Dict[str, Any]]
) -> Set[str]:
    """Discover Next.js routes from both App Router and Pages Router."""
    routes: Set[str] = set()

    # App Router: app/ directory
    app_dir = project_path / "app"
    if not app_dir.exists():
        app_dir = project_path / "src" / "app"

    if app_dir.exists():
        for root, dirs, files in os.walk(app_dir):
            rel_path = Path(root).relative_to(app_dir)

            # Skip if this directory contains route.ts/route.js (it's an API endpoint)
            if any(
                f in files for f in ("route.ts", "route.js", "route.tsx", "route.jsx")
            ):
                api_route = "/" + str(rel_path) if str(rel_path) != "." else "/"
                api_route = _strip_route_groups(api_route)
                if api_route:
                    route_metadata[api_route] = {
                        "type": "api",
                        "dynamic": _route_has_dynamic_segments(api_route),
                    }
                continue

            if "page.tsx" in files or "page.js" in files or "page.jsx" in files:
                route = "/" + str(rel_path) if str(rel_path) != "." else "/"
                route = _strip_route_groups(route)
                if not route:
                    route = "/"

                is_dynamic = _route_has_dynamic_segments(route)
                route_metadata[route] = {"type": "page", "dynamic": is_dynamic}
                routes.add(route)

    # Pages Router: pages/ directory
    pages_dir = project_path / "pages"
    if not pages_dir.exists():
        pages_dir = project_path / "src" / "pages"

    if pages_dir.exists():
        for root, dirs, files in os.walk(pages_dir):
            # Skip _app, _document, api directories
            dirs[:] = [d for d in dirs if d != "api"]

            for file in files:
                if not file.endswith((".tsx", ".js", ".jsx", ".ts")):
                    continue
                stem = Path(file).stem
                if stem.startswith("_"):
                    continue

                rel_path = (Path(root) / file).relative_to(pages_dir)
                route = "/" + str(rel_path.with_suffix(""))
                if route.endswith("/index"):
                    route = route[:-6]
                if not route:
                    route = "/"

                is_dynamic = _route_has_dynamic_segments(route)
                route_metadata[route] = {"type": "page", "dynamic": is_dynamic}
                routes.add(route)

    return routes


def _discover_sveltekit_routes(
    project_path: Path, route_metadata: Dict[str, Dict[str, Any]]
) -> Set[str]:
    """Discover SvelteKit routes from src/routes/ directory."""
    routes: Set[str] = set()
    routes_dir = project_path / "src" / "routes"
    if not routes_dir.exists():
        return routes

    for root, dirs, files in os.walk(routes_dir):
        rel_path = Path(root).relative_to(routes_dir)

        # Skip if this is a server-only endpoint
        if "+server.ts" in files or "+server.js" in files:
            if "+page.svelte" not in files:
                api_route = "/" + str(rel_path) if str(rel_path) != "." else "/"
                api_route = _strip_route_groups(api_route)
                if api_route:
                    route_metadata[api_route] = {
                        "type": "api",
                        "dynamic": _route_has_dynamic_segments(api_route),
                    }
                continue

        if "+page.svelte" in files:
            route = "/" + str(rel_path) if str(rel_path) != "." else "/"
            route = _strip_route_groups(route)
            if not route:
                route = "/"

            is_dynamic = _route_has_dynamic_segments(route)
            route_metadata[route] = {"type": "page", "dynamic": is_dynamic}
            routes.add(route)

    return routes


def _discover_nuxt_routes(
    project_path: Path, route_metadata: Dict[str, Dict[str, Any]]
) -> Set[str]:
    """Discover Nuxt routes from pages/ directory."""
    routes: Set[str] = set()
    pages_dir = project_path / "pages"
    if not pages_dir.exists():
        return routes

    for root, dirs, files in os.walk(pages_dir):
        for file in files:
            if not file.endswith(".vue"):
                continue

            rel_path = (Path(root) / file).relative_to(pages_dir)
            route = "/" + str(rel_path.with_suffix(""))
            if route.endswith("/index"):
                route = route[:-6]
            if not route:
                route = "/"

            is_dynamic = _route_has_dynamic_segments(route)
            route_metadata[route] = {"type": "page", "dynamic": is_dynamic}
            routes.add(route)

    return routes


def _discover_react_router_routes(
    project_path: Path, route_metadata: Dict[str, Dict[str, Any]]
) -> Set[str]:
    """Discover React Router routes by scanning source files for route definitions."""
    routes: Set[str] = set()

    src_dirs = [project_path / "src", project_path]
    extensions = (".tsx", ".jsx", ".ts", ".js")

    ignore = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        ".next",
    }

    for src_dir in src_dirs:
        if not src_dir.exists():
            continue
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in ignore]
            for file in files:
                if not file.endswith(extensions):
                    continue
                fpath = Path(root) / file
                try:
                    content = fpath.read_text(errors="ignore")
                except OSError:
                    continue

                # Only scan files that use react-router
                if (
                    "react-router" not in content
                    and "Route" not in content
                    and "createBrowserRouter" not in content
                ):
                    continue

                # Match <Route path="..." /> or <Route path='...' />
                jsx_routes = re.findall(
                    r'<Route\s+[^>]*path\s*=\s*["\']([^"\']+)["\']', content
                )
                routes.update(jsx_routes)

                # Match path: "..." in createBrowserRouter / route config objects
                config_routes = re.findall(r'path\s*:\s*["\']([^"\']+)["\']', content)
                routes.update(config_routes)

    # Normalize and classify
    normalized: Set[str] = set()
    for route in routes:
        if not route.startswith("/"):
            continue  # skip relative routes
        is_dynamic = ":" in route or _route_has_dynamic_segments(route)
        route_metadata[route] = {"type": "page", "dynamic": is_dynamic}
        normalized.add(route)

    return normalized


def _parse_nextjs_middleware(
    project_path: Path, route_metadata: Dict[str, Dict[str, Any]]
):
    """Parse middleware.ts/js for auth redirect patterns to classify routes as public/protected."""
    for name in (
        "middleware.ts",
        "middleware.js",
        "src/middleware.ts",
        "src/middleware.js",
    ):
        mw_path = project_path / name
        if mw_path.exists():
            try:
                content = mw_path.read_text(errors="ignore")
            except OSError:
                continue

            # Detect public route patterns: matcher config or explicit path checks
            # e.g., matcher: ['/dashboard/:path*', '/api/:path*']
            public_paths = set()
            protected_paths = set()

            # Match redirect to login/sign-in patterns
            auth_redirects = re.findall(
                r'redirect.*?["\'](/(?:login|sign-in|signin|auth)[^"\']*)["\']',
                content,
                re.IGNORECASE,
            )

            # Match matcher config
            matchers = re.findall(r"matcher\s*:\s*\[(.*?)\]", content, re.DOTALL)
            for matcher_block in matchers:
                paths = re.findall(r'["\']([^"\']+)["\']', matcher_block)
                protected_paths.update(paths)

            # Match isPublicRoute / publicRoutes patterns
            public_matches = re.findall(
                r'(?:isPublic|publicRoute|public)\s*.*?["\']([^"\']+)["\']',
                content,
                re.IGNORECASE,
            )
            public_paths.update(public_matches)

            # Mark auth redirect targets as public
            for path in auth_redirects:
                public_paths.add(path)

            # Apply classifications
            for route, meta in route_metadata.items():
                is_protected = False
                for pp in protected_paths:
                    # Strip :path* wildcards for comparison
                    clean = re.sub(r"/:path\*?", "", pp)
                    if route.startswith(clean):
                        is_protected = True
                        break

                is_public = False
                for pp in public_paths:
                    clean = re.sub(r"/:path\*?", "", pp)
                    if route.startswith(clean) or route == pp:
                        is_public = True
                        break

                if is_public:
                    meta["visibility"] = "public"
                elif is_protected:
                    meta["visibility"] = "protected"

            break  # Only process first middleware found


def _parse_nextjs_layouts(project_path: Path) -> List[str]:
    """Parse layout.tsx files for navigation Link hrefs."""
    nav_links: List[str] = []

    for layout_name in ("layout.tsx", "layout.jsx", "layout.js"):
        for layout_path in project_path.rglob(layout_name):
            try:
                content = layout_path.read_text(errors="ignore")
            except OSError:
                continue

            # Match <Link href="..."> patterns
            hrefs = re.findall(r'<Link\s+[^>]*href\s*=\s*["\']([^"\']+)["\']', content)
            nav_links.extend(h for h in hrefs if h.startswith("/"))

    return list(dict.fromkeys(nav_links))  # Deduplicate preserving order


def discovery_step(manifest: RunManifest):
    project_path = manifest.config.project_path
    console = Console()

    # 1. Framework Detection (Respect user choice from init)
    framework = manifest.config.framework
    if framework == Framework.UNKNOWN:
        console.print(
            "Framework unknown or [bold yellow]UNKNOWN[/bold yellow] selected, attempting auto-detection..."
        )
        detected = detect_frameworks(
            project_path,
            skip_ai=manifest.config.skip_ai,
            model=manifest.config.ai_model,
        )
        if detected != Framework.UNKNOWN:
            framework = detected
            manifest.config.framework = framework
            console.print(
                f"Auto-detected framework: [bold cyan]{framework.value}[/bold cyan]"
            )
        else:
            console.print(
                "[yellow]Could not detect framework automatically. Defaulting to generic crawler.[/yellow]"
            )
    else:
        console.print(
            f"Using user-specified framework: [bold cyan]{framework.value}[/bold cyan]"
        )

    # Warn for detection-only frameworks
    if framework in (Framework.REACT_NATIVE, Framework.CHROME_EXTENSION):
        console.print(
            f"[yellow]{framework.value} detected but not yet supported for route discovery. Falling back to crawler.[/yellow]"
        )

    # 2. Service / BaaS Detection
    services = detect_services(project_path)
    manifest.detected_services = services
    if services:
        console.print(
            f"Detected services: [bold cyan]{', '.join(services)}[/bold cyan]"
        )

    # 3. UI Component Inventory
    ui_components = detect_ui_components(project_path)
    manifest.ui_components = ui_components
    if ui_components:
        display = [c for c in ui_components if c != "__shadcn_marker__"]
        if display:
            console.print(
                f"Detected [bold cyan]{len(display)}[/bold cyan] UI components (shadcn/ui)"
            )
        elif "__shadcn_marker__" in ui_components:
            console.print(
                "Detected [bold cyan]shadcn/ui[/bold cyan] (components.json present)"
            )

    # 4. Deployment Platform Detection
    deployment = detect_deployment(project_path)
    manifest.deployment_platform = deployment
    if deployment:
        console.print(f"Deployment platform: [bold cyan]{deployment}[/bold cyan]")

    # 5. Route Discovery
    routes: Set[str] = set()
    route_metadata: Dict[str, Dict[str, Any]] = {}

    if framework == Framework.WORDPRESS:
        text_domain = _extract_text_domain(project_path)
        wp_routes = _discover_wordpress_routes(project_path)
        routes.update(wp_routes)
        if wp_routes:
            console.print(
                f"Found [bold cyan]{len(wp_routes)}[/bold cyan] WordPress admin pages via plugin header scan"
            )
        if text_domain:
            route_metadata["__wp_text_domain__"] = {"text_domain": text_domain}

    elif framework == Framework.NEXTJS:
        routes = _discover_nextjs_routes(project_path, route_metadata)
        _parse_nextjs_middleware(project_path, route_metadata)
        nav_links = _parse_nextjs_layouts(project_path)
        if nav_links:
            console.print(
                f"Found [bold cyan]{len(nav_links)}[/bold cyan] navigation links from layouts"
            )

    elif framework == Framework.SVELTEKIT:
        routes = _discover_sveltekit_routes(project_path, route_metadata)

    elif framework == Framework.NUXT:
        routes = _discover_nuxt_routes(project_path, route_metadata)

    elif framework == Framework.REACT:
        routes = _discover_react_router_routes(project_path, route_metadata)

    # Fallback/Default routes if none found
    if len(routes) <= 1:
        console.print(
            "[yellow]Static analysis found few routes. Launching crawler fallback...[/yellow]"
        )
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                app_url = manifest.config.app_url
                console.print(f"Crawling {app_url}...")
                page.goto(app_url, wait_until="networkidle")

                # Find all links
                links = page.query_selector_all("a")
                for link in links:
                    href = link.get_attribute("href")
                    if href:
                        if href.startswith("/"):
                            routes.add(href)
                        elif href.startswith(app_url):
                            route = href.replace(app_url, "")
                            if not route.startswith("/"):
                                route = "/" + route
                            routes.add(route)
                browser.close()
        except Exception as e:
            console.print(f"[red]Crawler fallback failed: {e}[/red]")

    if not routes:
        routes.add("/")

    manifest.discovered_routes = sorted(list(routes))
    manifest.route_metadata = route_metadata

    # Summary
    dynamic_count = sum(1 for m in route_metadata.values() if m.get("dynamic"))
    api_count = sum(1 for m in route_metadata.values() if m.get("type") == "api")
    page_count = len(manifest.discovered_routes)

    summary_parts = [f"{page_count} page routes"]
    if dynamic_count:
        summary_parts.append(f"{dynamic_count} dynamic")
    if api_count:
        summary_parts.append(f"{api_count} API endpoints filtered")

    console.print(
        f"Found [bold green]{', '.join(summary_parts)}[/bold green]: {', '.join(manifest.discovered_routes)}"
    )
