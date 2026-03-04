from unittest.mock import patch, MagicMock
from kodadocs.models import SessionConfig, RunManifest, Framework


def _make_manifest(
    tmp_path, framework=Framework.NEXTJS, app_url="http://localhost:3000"
):
    config = SessionConfig(
        app_url=app_url,
        project_path=tmp_path,
        framework=framework,
        skip_ai=True,
    )
    return RunManifest(session_id="test", config=config)


def test_nextjs_app_router_discovery(tmp_path):
    from kodadocs.pipeline.discovery import discovery_step

    # Create Next.js App Router structure
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

    manifest = _make_manifest(tmp_path)

    # Patch playwright at the source (it's a lazy import inside discovery_step)
    with patch("playwright.sync_api.sync_playwright"):
        discovery_step(manifest)

    assert "/" in manifest.discovered_routes
    assert "/about" in manifest.discovered_routes
    assert "/dashboard" in manifest.discovered_routes


def test_nextjs_pages_router_discovery(tmp_path):
    from kodadocs.pipeline.discovery import discovery_step

    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "index.tsx").write_text("export default function Home() {}")
    (tmp_path / "pages" / "about.tsx").write_text("export default function About() {}")

    manifest = _make_manifest(tmp_path)
    with patch("playwright.sync_api.sync_playwright"):
        discovery_step(manifest)

    assert "/" in manifest.discovered_routes
    assert "/about" in manifest.discovered_routes


def test_nextjs_route_groups_stripped(tmp_path):
    from kodadocs.pipeline.discovery import discovery_step

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "(marketing)").mkdir()
    (tmp_path / "app" / "(marketing)" / "page.tsx").write_text(
        "export default function Home() {}"
    )

    manifest = _make_manifest(tmp_path)
    with patch("playwright.sync_api.sync_playwright"):
        discovery_step(manifest)

    assert "/" in manifest.discovered_routes
    # Route group "(marketing)" should be stripped
    assert "(marketing)" not in str(manifest.discovered_routes)


def test_wordpress_admin_page_discovery(tmp_path):
    from kodadocs.pipeline.discovery import discovery_step

    # Create a mock WordPress plugin file with standard header and menu registrations
    plugin_php = tmp_path / "formrank-lead-scoring.php"
    plugin_php.write_text("""<?php
/**
 * Plugin Name: FormRank Lead Scoring
 * Description: AI-powered lead scoring for form submissions
 * Version: 1.0.0
 * Text Domain: formrank-lead-scoring
 */

function formrank_admin_menu() {
    add_menu_page(
        'FormRank Lead Scoring',
        'FormRank',
        'manage_options',
        'formrank-lead-scoring',
        'formrank_dashboard_page'
    );
    add_submenu_page(
        'formrank-lead-scoring',
        'Dashboard',
        'Dashboard',
        'manage_options',
        'formrank-lead-scoring-dashboard',
        'formrank_dashboard_page'
    );
    add_submenu_page(
        'formrank-lead-scoring',
        'Settings',
        'Settings',
        'manage_options',
        'formrank-lead-scoring-settings',
        'formrank_settings_page'
    );
}
add_action('admin_menu', 'formrank_admin_menu');
""")

    manifest = _make_manifest(
        tmp_path, framework=Framework.WORDPRESS, app_url="http://localhost:8080"
    )
    discovery_step(manifest)

    assert len(manifest.discovered_routes) == 3
    assert (
        "/wp-admin/admin.php?page=formrank-lead-scoring" in manifest.discovered_routes
    )
    assert (
        "/wp-admin/admin.php?page=formrank-lead-scoring-dashboard"
        in manifest.discovered_routes
    )
    assert (
        "/wp-admin/admin.php?page=formrank-lead-scoring-settings"
        in manifest.discovered_routes
    )


def test_empty_project_gets_root_route(tmp_path):
    from kodadocs.pipeline.discovery import discovery_step

    manifest = _make_manifest(tmp_path, framework=Framework.UNKNOWN)

    # Patch playwright at the source — the import is lazy inside the function
    mock_pw = MagicMock()
    mock_browser = (
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value
    )
    mock_page = mock_browser.new_page.return_value
    mock_page.query_selector_all.return_value = []

    with patch("playwright.sync_api.sync_playwright", return_value=mock_pw):
        discovery_step(manifest)

    assert "/" in manifest.discovered_routes


# ---------------------------------------------------------------------------
# A4: Next.js Improvements — dynamic routes, route.ts filtering, internals
# ---------------------------------------------------------------------------


class TestNextjsDynamicRoutes:
    """Dynamic route segments [slug] should be marked dynamic=True in route_metadata."""

    def test_app_router_dynamic_segment_marked(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
        (tmp_path / "app" / "blog").mkdir()
        (tmp_path / "app" / "blog" / "[slug]").mkdir()
        (tmp_path / "app" / "blog" / "[slug]" / "page.tsx").write_text(
            "export default function BlogPost() {}"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/blog/[slug]" in manifest.discovered_routes
        assert manifest.route_metadata["/blog/[slug]"]["dynamic"] is True

    def test_static_route_not_marked_dynamic(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "about").mkdir()
        (tmp_path / "app" / "about" / "page.tsx").write_text(
            "export default function About() {}"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/about" in manifest.discovered_routes
        assert manifest.route_metadata["/about"]["dynamic"] is False

    def test_nested_dynamic_segment(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "users").mkdir()
        (tmp_path / "app" / "users" / "[userId]").mkdir()
        (tmp_path / "app" / "users" / "[userId]" / "posts").mkdir()
        (tmp_path / "app" / "users" / "[userId]" / "posts" / "[postId]").mkdir()
        (
            tmp_path / "app" / "users" / "[userId]" / "posts" / "[postId]" / "page.tsx"
        ).write_text("export default function Post() {}")

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        route = "/users/[userId]/posts/[postId]"
        assert route in manifest.discovered_routes
        assert manifest.route_metadata[route]["dynamic"] is True

    def test_catch_all_dynamic_segment(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "docs").mkdir()
        (tmp_path / "app" / "docs" / "[...slug]").mkdir()
        (tmp_path / "app" / "docs" / "[...slug]" / "page.tsx").write_text(
            "export default function Docs() {}"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/docs/[...slug]" in manifest.discovered_routes
        assert manifest.route_metadata["/docs/[...slug]"]["dynamic"] is True


class TestNextjsRouteFiltering:
    """route.ts directories should be filtered out from page routes and classified as API."""

    def test_route_ts_excluded_from_page_routes(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
        (tmp_path / "app" / "api").mkdir()
        (tmp_path / "app" / "api" / "users").mkdir()
        (tmp_path / "app" / "api" / "users" / "route.ts").write_text(
            "export async function GET() { return Response.json({}) }"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        # The API route directory should NOT appear in discovered_routes
        assert "/api/users" not in manifest.discovered_routes
        assert "/" in manifest.discovered_routes

    def test_route_ts_gets_api_type_in_metadata(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
        (tmp_path / "app" / "api").mkdir()
        (tmp_path / "app" / "api" / "users").mkdir()
        (tmp_path / "app" / "api" / "users" / "route.ts").write_text(
            "export async function GET() {}"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/api/users" in manifest.route_metadata
        assert manifest.route_metadata["/api/users"]["type"] == "api"

    def test_route_js_also_filtered(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
        (tmp_path / "app" / "webhooks").mkdir()
        (tmp_path / "app" / "webhooks" / "route.js").write_text(
            "export async function POST() {}"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/webhooks" not in manifest.discovered_routes
        assert manifest.route_metadata["/webhooks"]["type"] == "api"

    def test_dynamic_api_route_marked_dynamic(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
        (tmp_path / "app" / "api").mkdir()
        (tmp_path / "app" / "api" / "users").mkdir()
        (tmp_path / "app" / "api" / "users" / "[id]").mkdir()
        (tmp_path / "app" / "api" / "users" / "[id]" / "route.ts").write_text(
            "export async function GET() {}"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/api/users/[id]" in manifest.route_metadata
        assert manifest.route_metadata["/api/users/[id]"]["type"] == "api"
        assert manifest.route_metadata["/api/users/[id]"]["dynamic"] is True


class TestNextjsInternalFilesExcluded:
    """loading.tsx, error.tsx, not-found.tsx should NOT be included as page routes."""

    def test_loading_tsx_not_included(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
        (tmp_path / "app" / "dashboard").mkdir()
        (tmp_path / "app" / "dashboard" / "page.tsx").write_text(
            "export default function Dashboard() {}"
        )
        # loading.tsx should not create a route — it lives in a dir that has page.tsx
        # or in a dir that has NO page.tsx (and thus no route is generated)
        (tmp_path / "app" / "dashboard" / "loading.tsx").write_text(
            "export default function Loading() { return <div>Loading...</div> }"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        # Only / and /dashboard, no loading route
        assert "/" in manifest.discovered_routes
        assert "/dashboard" in manifest.discovered_routes
        # The discovery is based on page.tsx presence, so loading.tsx alone
        # does not create a route. Verify the total count.
        assert len(manifest.discovered_routes) == 2

    def test_error_tsx_directory_without_page_not_included(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
        # A directory with only error.tsx and no page.tsx should not appear
        (tmp_path / "app" / "settings").mkdir()
        (tmp_path / "app" / "settings" / "error.tsx").write_text(
            "export default function Error() {}"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/settings" not in manifest.discovered_routes
        assert "/" in manifest.discovered_routes

    def test_not_found_tsx_directory_without_page_not_included(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
        # not-found.tsx alone should not create a route
        (tmp_path / "app" / "missing").mkdir()
        (tmp_path / "app" / "missing" / "not-found.tsx").write_text(
            "export default function NotFound() {}"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/missing" not in manifest.discovered_routes

    def test_layout_only_directory_not_included(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
        # A directory with only layout.tsx should not appear as a route
        (tmp_path / "app" / "admin").mkdir()
        (tmp_path / "app" / "admin" / "layout.tsx").write_text(
            "export default function AdminLayout({ children }) { return children }"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/admin" not in manifest.discovered_routes


class TestNextjsPagesRouterDynamic:
    """Pages Router should now include files with [ in the name (dynamic routes)."""

    def test_pages_router_dynamic_route_included(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "index.tsx").write_text(
            "export default function Home() {}"
        )
        (tmp_path / "pages" / "blog").mkdir()
        (tmp_path / "pages" / "blog" / "[slug].tsx").write_text(
            "export default function BlogPost() {}"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/" in manifest.discovered_routes
        assert "/blog/[slug]" in manifest.discovered_routes
        assert manifest.route_metadata["/blog/[slug]"]["dynamic"] is True

    def test_pages_router_catch_all_route(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "index.tsx").write_text(
            "export default function Home() {}"
        )
        (tmp_path / "pages" / "docs").mkdir()
        (tmp_path / "pages" / "docs" / "[...slug].tsx").write_text(
            "export default function Docs() {}"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/docs/[...slug]" in manifest.discovered_routes
        assert manifest.route_metadata["/docs/[...slug]"]["dynamic"] is True

    def test_pages_router_static_not_marked_dynamic(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "about.tsx").write_text(
            "export default function About() {}"
        )

        manifest = _make_manifest(tmp_path)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/about" in manifest.discovered_routes
        assert manifest.route_metadata["/about"]["dynamic"] is False


# ---------------------------------------------------------------------------
# B1: SvelteKit Route Discovery
# ---------------------------------------------------------------------------


class TestSvelteKitRouteDiscovery:
    """SvelteKit routes discovered from src/routes/ via +page.svelte files."""

    def test_basic_root_route(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "src" / "routes").mkdir(parents=True)
        (tmp_path / "src" / "routes" / "+page.svelte").write_text("<h1>Home</h1>")

        manifest = _make_manifest(tmp_path, framework=Framework.SVELTEKIT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/" in manifest.discovered_routes

    def test_nested_route(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "src" / "routes").mkdir(parents=True)
        (tmp_path / "src" / "routes" / "+page.svelte").write_text("<h1>Home</h1>")
        (tmp_path / "src" / "routes" / "about").mkdir()
        (tmp_path / "src" / "routes" / "about" / "+page.svelte").write_text(
            "<h1>About</h1>"
        )

        manifest = _make_manifest(tmp_path, framework=Framework.SVELTEKIT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/" in manifest.discovered_routes
        assert "/about" in manifest.discovered_routes

    def test_dynamic_route_marked(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "src" / "routes").mkdir(parents=True)
        (tmp_path / "src" / "routes" / "+page.svelte").write_text("<h1>Home</h1>")
        (tmp_path / "src" / "routes" / "blog").mkdir()
        (tmp_path / "src" / "routes" / "blog" / "[slug]").mkdir()
        (tmp_path / "src" / "routes" / "blog" / "[slug]" / "+page.svelte").write_text(
            "<h1>Blog Post</h1>"
        )

        manifest = _make_manifest(tmp_path, framework=Framework.SVELTEKIT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/blog/[slug]" in manifest.discovered_routes
        assert manifest.route_metadata["/blog/[slug]"]["dynamic"] is True

    def test_server_endpoint_without_page_excluded(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "src" / "routes").mkdir(parents=True)
        (tmp_path / "src" / "routes" / "+page.svelte").write_text("<h1>Home</h1>")
        (tmp_path / "src" / "routes" / "api").mkdir()
        (tmp_path / "src" / "routes" / "api" / "data").mkdir()
        # Server-only endpoint — no +page.svelte
        (tmp_path / "src" / "routes" / "api" / "data" / "+server.ts").write_text(
            "export function GET() { return new Response('ok') }"
        )

        manifest = _make_manifest(tmp_path, framework=Framework.SVELTEKIT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/api/data" not in manifest.discovered_routes
        # But it should be recorded as an API in metadata
        assert "/api/data" in manifest.route_metadata
        assert manifest.route_metadata["/api/data"]["type"] == "api"

    def test_route_groups_stripped(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "src" / "routes").mkdir(parents=True)
        (tmp_path / "src" / "routes" / "(app)").mkdir()
        (tmp_path / "src" / "routes" / "(app)" / "dashboard").mkdir()
        (
            tmp_path / "src" / "routes" / "(app)" / "dashboard" / "+page.svelte"
        ).write_text("<h1>Dashboard</h1>")

        manifest = _make_manifest(tmp_path, framework=Framework.SVELTEKIT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/dashboard" in manifest.discovered_routes
        # Route group "(app)" stripped from the path
        assert "(app)" not in str(manifest.discovered_routes)

    def test_deeply_nested_sveltekit_routes(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "src" / "routes").mkdir(parents=True)
        (tmp_path / "src" / "routes" / "+page.svelte").write_text("<h1>Home</h1>")
        (tmp_path / "src" / "routes" / "settings").mkdir()
        (tmp_path / "src" / "routes" / "settings" / "profile").mkdir()
        (
            tmp_path / "src" / "routes" / "settings" / "profile" / "+page.svelte"
        ).write_text("<h1>Profile Settings</h1>")

        manifest = _make_manifest(tmp_path, framework=Framework.SVELTEKIT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/settings/profile" in manifest.discovered_routes

    def test_server_js_variant_excluded(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "src" / "routes").mkdir(parents=True)
        (tmp_path / "src" / "routes" / "+page.svelte").write_text("<h1>Home</h1>")
        (tmp_path / "src" / "routes" / "api").mkdir()
        (tmp_path / "src" / "routes" / "api" / "health").mkdir()
        (tmp_path / "src" / "routes" / "api" / "health" / "+server.js").write_text(
            "export function GET() { return new Response('ok') }"
        )

        manifest = _make_manifest(tmp_path, framework=Framework.SVELTEKIT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/api/health" not in manifest.discovered_routes
        assert manifest.route_metadata["/api/health"]["type"] == "api"


# ---------------------------------------------------------------------------
# B4: Nuxt Route Discovery
# ---------------------------------------------------------------------------


class TestNuxtRouteDiscovery:
    """Nuxt routes discovered from pages/ directory with .vue files."""

    def test_basic_index_route(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "index.vue").write_text(
            "<template><h1>Home</h1></template>"
        )

        manifest = _make_manifest(tmp_path, framework=Framework.NUXT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/" in manifest.discovered_routes

    def test_nested_about_route(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "index.vue").write_text(
            "<template><h1>Home</h1></template>"
        )
        (tmp_path / "pages" / "about.vue").write_text(
            "<template><h1>About</h1></template>"
        )

        manifest = _make_manifest(tmp_path, framework=Framework.NUXT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/" in manifest.discovered_routes
        assert "/about" in manifest.discovered_routes

    def test_dynamic_route_marked(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "index.vue").write_text(
            "<template><h1>Home</h1></template>"
        )
        (tmp_path / "pages" / "blog").mkdir()
        (tmp_path / "pages" / "blog" / "[slug].vue").write_text(
            "<template><h1>Blog Post</h1></template>"
        )

        manifest = _make_manifest(tmp_path, framework=Framework.NUXT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/blog/[slug]" in manifest.discovered_routes
        assert manifest.route_metadata["/blog/[slug]"]["dynamic"] is True

    def test_static_route_not_dynamic(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "contact.vue").write_text(
            "<template><h1>Contact</h1></template>"
        )

        manifest = _make_manifest(tmp_path, framework=Framework.NUXT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/contact" in manifest.discovered_routes
        assert manifest.route_metadata["/contact"]["dynamic"] is False

    def test_nested_directory_route(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "index.vue").write_text(
            "<template><h1>Home</h1></template>"
        )
        (tmp_path / "pages" / "settings").mkdir()
        (tmp_path / "pages" / "settings" / "index.vue").write_text(
            "<template><h1>Settings</h1></template>"
        )
        (tmp_path / "pages" / "settings" / "profile.vue").write_text(
            "<template><h1>Profile</h1></template>"
        )

        manifest = _make_manifest(tmp_path, framework=Framework.NUXT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/" in manifest.discovered_routes
        assert "/settings" in manifest.discovered_routes
        assert "/settings/profile" in manifest.discovered_routes

    def test_deeply_nested_dynamic_route(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "users").mkdir()
        (tmp_path / "pages" / "users" / "[id]").mkdir()
        (tmp_path / "pages" / "users" / "[id]" / "posts.vue").write_text(
            "<template><h1>User Posts</h1></template>"
        )

        manifest = _make_manifest(tmp_path, framework=Framework.NUXT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/users/[id]/posts" in manifest.discovered_routes
        assert manifest.route_metadata["/users/[id]/posts"]["dynamic"] is True

    def test_non_vue_files_ignored(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "index.vue").write_text(
            "<template><h1>Home</h1></template>"
        )
        # Non-.vue files should be ignored
        (tmp_path / "pages" / "README.md").write_text("# Pages dir")
        (tmp_path / "pages" / "utils.ts").write_text("export const foo = 1")

        manifest = _make_manifest(tmp_path, framework=Framework.NUXT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert len(manifest.discovered_routes) == 1
        assert "/" in manifest.discovered_routes


# ---------------------------------------------------------------------------
# B2: React Router Route Discovery
# ---------------------------------------------------------------------------


class TestReactRouterDiscovery:
    """React Router routes discovered by scanning source files for route definitions."""

    def test_jsx_route_pattern(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "App.tsx").write_text("""
import { BrowserRouter, Route, Routes } from 'react-router-dom';

export default function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/profile" element={<Profile />} />
            </Routes>
        </BrowserRouter>
    );
}
""")

        manifest = _make_manifest(tmp_path, framework=Framework.REACT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/dashboard" in manifest.discovered_routes
        assert "/profile" in manifest.discovered_routes

    def test_config_pattern(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "router.ts").write_text("""
import { createBrowserRouter } from 'react-router-dom';

export const router = createBrowserRouter([
    {
        path: "/",
        element: <Root />,
    },
    {
        path: "/settings",
        element: <Settings />,
    },
    {
        path: "/users",
        element: <Users />,
    },
]);
""")

        manifest = _make_manifest(tmp_path, framework=Framework.REACT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/" in manifest.discovered_routes
        assert "/settings" in manifest.discovered_routes
        assert "/users" in manifest.discovered_routes

    def test_only_scans_files_with_react_router_refs(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "src").mkdir()
        # This file has no react-router imports — should be ignored
        (tmp_path / "src" / "utils.ts").write_text("""
const path = "/ignored-path";
export function getPath() { return path; }
""")
        # This file has react-router reference — should be scanned
        (tmp_path / "src" / "App.tsx").write_text("""
import { Route } from 'react-router-dom';

export default function App() {
    return <Route path="/found" element={<Found />} />;
}
""")

        manifest = _make_manifest(tmp_path, framework=Framework.REACT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/found" in manifest.discovered_routes
        # /ignored-path should not be discovered (no react-router context)
        assert "/ignored-path" not in manifest.discovered_routes

    def test_relative_routes_excluded(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "App.tsx").write_text("""
import { Route } from 'react-router-dom';

export default function App() {
    return (
        <>
            <Route path="/absolute" element={<Absolute />} />
            <Route path="relative" element={<Relative />} />
        </>
    );
}
""")

        manifest = _make_manifest(tmp_path, framework=Framework.REACT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/absolute" in manifest.discovered_routes
        # Relative paths (not starting with /) should be excluded
        assert "relative" not in manifest.discovered_routes

    def test_dynamic_route_with_colon_param(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "App.tsx").write_text("""
import { Route } from 'react-router-dom';

export default function App() {
    return (
        <>
            <Route path="/users/:id" element={<User />} />
            <Route path="/posts/:postId/comments" element={<Comments />} />
        </>
    );
}
""")

        manifest = _make_manifest(tmp_path, framework=Framework.REACT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/users/:id" in manifest.discovered_routes
        assert manifest.route_metadata["/users/:id"]["dynamic"] is True
        assert "/posts/:postId/comments" in manifest.discovered_routes
        assert manifest.route_metadata["/posts/:postId/comments"]["dynamic"] is True

    def test_mixed_jsx_and_config_patterns(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "App.tsx").write_text("""
import { Route } from 'react-router-dom';
export default function App() {
    return <Route path="/from-jsx" element={<Page />} />;
}
""")
        (tmp_path / "src" / "config.ts").write_text("""
import { createBrowserRouter } from 'react-router-dom';
export const router = createBrowserRouter([
    { path: "/from-config" },
]);
""")

        manifest = _make_manifest(tmp_path, framework=Framework.REACT)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "/from-jsx" in manifest.discovered_routes
        assert "/from-config" in manifest.discovered_routes


# ---------------------------------------------------------------------------
# Integration: Service, Component, and Deployment Detection in discovery_step
# ---------------------------------------------------------------------------


class TestDiscoveryStepIntegration:
    """Verify that discovery_step populates detected_services, ui_components, deployment_platform."""

    def test_detected_services_populated(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        # Create package.json with known service dependencies
        (tmp_path / "package.json").write_text("""{
  "name": "test-app",
  "dependencies": {
    "next": "14.0.0",
    "@supabase/supabase-js": "^2.0.0",
    "stripe": "^14.0.0",
    "@clerk/nextjs": "^4.0.0"
  }
}""")
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")

        manifest = _make_manifest(tmp_path, framework=Framework.NEXTJS)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "supabase" in manifest.detected_services
        assert "stripe" in manifest.detected_services
        assert "clerk" in manifest.detected_services

    def test_ui_components_populated(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        # Create shadcn/ui component structure
        (tmp_path / "components.json").write_text('{"style": "default"}')
        (tmp_path / "src" / "components" / "ui").mkdir(parents=True)
        (tmp_path / "src" / "components" / "ui" / "button.tsx").write_text(
            "export function Button() {}"
        )
        (tmp_path / "src" / "components" / "ui" / "card.tsx").write_text(
            "export function Card() {}"
        )
        (tmp_path / "src" / "components" / "ui" / "input.tsx").write_text(
            "export function Input() {}"
        )

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")

        manifest = _make_manifest(tmp_path, framework=Framework.NEXTJS)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "button" in manifest.ui_components
        assert "card" in manifest.ui_components
        assert "input" in manifest.ui_components

    def test_deployment_platform_populated(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "vercel.json").write_text('{"framework": "nextjs"}')
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")

        manifest = _make_manifest(tmp_path, framework=Framework.NEXTJS)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert manifest.deployment_platform == "vercel"

    def test_deployment_platform_netlify(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "netlify.toml").write_text('[build]\ncommand = "npm run build"')
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")

        manifest = _make_manifest(tmp_path, framework=Framework.NEXTJS)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert manifest.deployment_platform == "netlify"

    def test_deployment_platform_docker(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "Dockerfile").write_text("FROM node:20-alpine")
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")

        manifest = _make_manifest(tmp_path, framework=Framework.NEXTJS)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert manifest.deployment_platform == "docker"

    def test_no_services_when_no_package_json(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")

        manifest = _make_manifest(tmp_path, framework=Framework.NEXTJS)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert manifest.detected_services == []

    def test_no_deployment_when_no_config(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")

        manifest = _make_manifest(tmp_path, framework=Framework.NEXTJS)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert manifest.deployment_platform is None

    def test_shadcn_marker_when_components_json_only(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        (tmp_path / "components.json").write_text('{"style": "default"}')
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")

        manifest = _make_manifest(tmp_path, framework=Framework.NEXTJS)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        assert "__shadcn_marker__" in manifest.ui_components

    def test_all_detections_run_together(self, tmp_path):
        """Ensure services, components, deployment, and routes are all discovered in one call."""
        from kodadocs.pipeline.discovery import discovery_step

        # Set up a realistic project structure
        (tmp_path / "package.json").write_text("""{
  "name": "full-app",
  "dependencies": {
    "next": "14.0.0",
    "@prisma/client": "^5.0.0",
    "resend": "^3.0.0"
  }
}""")
        (tmp_path / "vercel.json").write_text("{}")
        (tmp_path / "components.json").write_text('{"style": "default"}')
        (tmp_path / "src" / "components" / "ui").mkdir(parents=True)
        (tmp_path / "src" / "components" / "ui" / "dialog.tsx").write_text(
            "export function Dialog() {}"
        )
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "page.tsx").write_text("export default function Home() {}")
        (tmp_path / "app" / "dashboard").mkdir()
        (tmp_path / "app" / "dashboard" / "page.tsx").write_text(
            "export default function Dashboard() {}"
        )

        manifest = _make_manifest(tmp_path, framework=Framework.NEXTJS)
        with patch("playwright.sync_api.sync_playwright"):
            discovery_step(manifest)

        # Routes
        assert "/" in manifest.discovered_routes
        assert "/dashboard" in manifest.discovered_routes

        # Services
        assert "prisma" in manifest.detected_services
        assert "resend" in manifest.detected_services

        # UI components
        assert "dialog" in manifest.ui_components

        # Deployment
        assert manifest.deployment_platform == "vercel"


# ---------------------------------------------------------------------------
# WordPress Runtime Sidebar Discovery
# ---------------------------------------------------------------------------


class TestExtractTextDomain:
    """_extract_text_domain should return the text domain from PHP headers."""

    def test_returns_text_domain_from_php_header(self, tmp_path):
        from kodadocs.pipeline.discovery import _extract_text_domain

        plugin_php = tmp_path / "my-plugin.php"
        plugin_php.write_text("""<?php
/**
 * Plugin Name: My Plugin
 * Text Domain: my-plugin
 */
""")
        assert _extract_text_domain(tmp_path) == "my-plugin"

    def test_returns_none_when_no_header(self, tmp_path):
        from kodadocs.pipeline.discovery import _extract_text_domain

        plugin_php = tmp_path / "my-plugin.php"
        plugin_php.write_text("<?php echo 'hello';")

        assert _extract_text_domain(tmp_path) is None

    def test_returns_none_for_empty_directory(self, tmp_path):
        from kodadocs.pipeline.discovery import _extract_text_domain

        assert _extract_text_domain(tmp_path) is None


class TestDiscoverWpSidebarRoutes:
    """_discover_wp_sidebar_routes should extract sidebar links matching the text domain."""

    def test_returns_filtered_routes(self):
        from kodadocs.pipeline.discovery import _discover_wp_sidebar_routes

        mock_page = MagicMock()
        mock_page.evaluate.return_value = [
            "admin.php?page=formrank-lead-scoring",
            "admin.php?page=formrank-lead-scoring-dashboard",
            "admin.php?page=formrank-lead-scoring-account",
            "admin.php?page=other-plugin-settings",
            "edit.php",
        ]

        routes = _discover_wp_sidebar_routes(
            mock_page, "http://localhost:8080", "formrank-lead-scoring"
        )

        assert len(routes) == 3
        assert "/wp-admin/admin.php?page=formrank-lead-scoring" in routes
        assert "/wp-admin/admin.php?page=formrank-lead-scoring-dashboard" in routes
        assert "/wp-admin/admin.php?page=formrank-lead-scoring-account" in routes
        # other-plugin-settings should be excluded
        assert "/wp-admin/admin.php?page=other-plugin-settings" not in routes

    def test_returns_empty_on_no_matching_links(self):
        from kodadocs.pipeline.discovery import _discover_wp_sidebar_routes

        mock_page = MagicMock()
        mock_page.evaluate.return_value = [
            "admin.php?page=other-plugin",
            "edit.php",
        ]

        routes = _discover_wp_sidebar_routes(
            mock_page, "http://localhost:8080", "my-plugin"
        )
        assert routes == []

    def test_returns_empty_on_navigation_failure(self):
        from kodadocs.pipeline.discovery import _discover_wp_sidebar_routes

        mock_page = MagicMock()
        mock_page.goto.side_effect = Exception("Navigation failed")

        routes = _discover_wp_sidebar_routes(
            mock_page, "http://localhost:8080", "my-plugin"
        )
        assert routes == []

    def test_deduplicates_routes(self):
        from kodadocs.pipeline.discovery import _discover_wp_sidebar_routes

        mock_page = MagicMock()
        mock_page.evaluate.return_value = [
            "admin.php?page=my-plugin",
            "admin.php?page=my-plugin",  # duplicate
            "admin.php?page=my-plugin-settings",
        ]

        routes = _discover_wp_sidebar_routes(
            mock_page, "http://localhost:8080", "my-plugin"
        )
        assert len(routes) == 2


class TestWordPressDiscoveryStoresTextDomain:
    """discovery_step should stash __wp_text_domain__ in route_metadata for WP plugins."""

    def test_text_domain_stored_in_route_metadata(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        plugin_php = tmp_path / "formrank.php"
        plugin_php.write_text("""<?php
/**
 * Plugin Name: FormRank
 * Text Domain: formrank-lead-scoring
 */

add_menu_page('FormRank', 'FormRank', 'manage_options', 'formrank-lead-scoring', 'fr_page');
""")

        manifest = _make_manifest(
            tmp_path, framework=Framework.WORDPRESS, app_url="http://localhost:8080"
        )
        discovery_step(manifest)

        assert "__wp_text_domain__" in manifest.route_metadata
        assert (
            manifest.route_metadata["__wp_text_domain__"]["text_domain"]
            == "formrank-lead-scoring"
        )

    def test_no_text_domain_when_missing(self, tmp_path):
        from kodadocs.pipeline.discovery import discovery_step

        plugin_php = tmp_path / "my-plugin.php"
        plugin_php.write_text("<?php echo 'hello';")

        manifest = _make_manifest(
            tmp_path, framework=Framework.WORDPRESS, app_url="http://localhost:8080"
        )
        discovery_step(manifest)

        assert "__wp_text_domain__" not in manifest.route_metadata
