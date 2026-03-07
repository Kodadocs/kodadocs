from fastmcp import FastMCP
from kodadocs.mcp.tools.framework import detect_framework_tool
from kodadocs.mcp.tools.capture import (
    capture_screenshots_tool,
    capture_targeted_tool,
    record_gif_tool,
)
from kodadocs.mcp.tools.annotation import annotate_screenshots_tool
from kodadocs.mcp.tools.output import assemble_vitepress_tool
from kodadocs.mcp.tools.manifest import save_manifest_tool, load_manifest_tool
from kodadocs.mcp.tools.deploy import deploy_site_tool
from kodadocs.mcp.tools.discovery import discover_routes_tool
from kodadocs.mcp.tools.analysis import analyze_codebase_tool

mcp = FastMCP(name="kodadocs")


@mcp.tool
def detect_framework(project_path: str) -> str:
    """Detect the web framework of a project at the given path.
    Returns the framework name (e.g., 'Next.js', 'Django', 'React').
    Uses heuristic detection from package.json, requirements.txt, etc.
    """
    return detect_framework_tool(project_path)


@mcp.tool
def capture_screenshots(
    routes: list[str],
    app_url: str,
    auth: dict | None,
    output_dir: str,
    blur_pii: bool = True,
) -> str:
    """Capture screenshots for discovered routes using Playwright.
    Launches headless Chromium, authenticates if auth is provided,
    navigates to each route, captures screenshots, and extracts DOM elements.
    Returns JSON with screenshots dict, dom_elements dict, and pii_regions.
    Free tier: limited to 15 pages, no auth support. Pro Kit (installed skills) unlocks unlimited pages and auth.
    """
    return capture_screenshots_tool(
        routes, app_url, auth, output_dir, blur_pii=blur_pii
    )


@mcp.tool
def capture_targeted(
    targets: list[dict],
    app_url: str,
    auth: dict | None,
    output_dir: str,
    blur_pii: bool = True,
) -> str:
    """Capture targeted screenshots of specific CSS selectors or clipped regions.
    Each target needs: route, label, and either selector (CSS) or clip ({x,y,width,height}).
    Optional padding (int) adds white border around the capture.
    Pro Kit required — install Pro Kit skill files to use this tool.
    Returns JSON with status and targeted_screenshots dict (label -> path).
    """
    return capture_targeted_tool(
        targets, app_url, auth, output_dir, blur_pii=blur_pii
    )


@mcp.tool
def record_gif(
    steps: list[dict],
    app_url: str,
    auth: dict | None,
    output_dir: str,
    label: str = "recording",
    frame_duration_ms: int = 2500,
    width: int = 1280,
    height: int = 720,
    blur_pii: bool = True,
) -> str:
    """Record a multi-step browser interaction as an animated GIF.
    Each step needs: action (navigate|click|type|scroll|wait|hover), target (CSS selector or path), value (optional).
    frame_duration_ms controls how long each frame is shown (default 2500ms = 2.5 seconds).
    Pro Kit required — install Pro Kit skill files to use this tool.
    Returns JSON with status, gif_path, frame_count, duration_seconds, file_size_bytes.
    """
    return record_gif_tool(
        steps, app_url, auth, output_dir,
        label=label, frame_duration_ms=frame_duration_ms, width=width, height=height,
        blur_pii=blur_pii,
    )


@mcp.tool
def annotate_screenshots(
    screenshots_dir: str,
    dom_elements: dict,
    brand_color: str = "#3e8fb0",
    pii_regions: dict | None = None,
) -> str:
    """Annotate screenshots with numbered callouts using Pillow.
    Takes screenshot directory and dom_elements dict (route -> element list).
    Each element needs: role, name, bounds {x, y, width, height}.
    Creates annotated copies in screenshots_dir/annotated/.
    Returns JSON with route -> annotated image path.
    """
    return annotate_screenshots_tool(
        screenshots_dir, dom_elements, brand_color, pii_regions=pii_regions
    )


@mcp.tool
def assemble_vitepress(
    articles: list[dict],
    screenshots_dir: str,
    brand_color: str,
    logo_path: str | None,
    output_dir: str,
    project_name: str,
    product_summary: str,
    discovered_routes: list[str],
    hero_tagline: str | None = None,
    hero_cta_text: str | None = None,
    hero_cta_link: str | None = None,
    feature_highlights: list[dict] | None = None,
    show_product_summary: bool = True,
    theme_name: str | None = None,
) -> str:
    """Assemble a VitePress static site from generated articles and screenshots.
    Creates index page, article markdown files, VitePress config, theme with brand color, and package.json.
    Pass theme_name to use a built-in theme preset (default, professional, minimal, playful, dark-modern, docs-classic).
    Pro themes and custom branding require the Pro Kit (installed locally).
    """
    return assemble_vitepress_tool(
        articles,
        screenshots_dir,
        brand_color,
        logo_path,
        output_dir,
        project_name,
        product_summary,
        discovered_routes,
        hero_tagline=hero_tagline,
        hero_cta_text=hero_cta_text,
        hero_cta_link=hero_cta_link,
        feature_highlights=feature_highlights,
        show_product_summary=show_product_summary,
        theme_name=theme_name,
    )


@mcp.tool
def save_manifest(manifest: dict, project_path: str) -> str:
    """Save pipeline state to .kodadocs/run_manifest.json."""
    return save_manifest_tool(manifest, project_path)


@mcp.tool
def load_manifest(project_path: str) -> str:
    """Load existing pipeline state from .kodadocs/run_manifest.json."""
    return load_manifest_tool(project_path)


@mcp.tool
def deploy_site(
    site_dir: str,
    project_name: str,
    provider: str | None = None,
    detected_platform: str | None = None,
    license_key: str | None = None,
    site_slug: str | None = None,
) -> str:
    """Deploy the generated VitePress site to a hosting provider.
    Supported providers: cloudflare, vercel, netlify, github-pages.
    Pro Kit removes the badge on self-hosted deploys. Pass license_key for hosted deploy at yourapp.kodadocs.com.
    """
    return deploy_site_tool(
        site_dir,
        project_name,
        provider=provider,
        detected_platform=detected_platform,
        license_key=license_key,
        site_slug=site_slug,
    )


@mcp.tool
def discover_routes(
    project_path: str,
    framework: str | None = None,
    app_url: str | None = None,
) -> str:
    """Discover application routes, services, and metadata via static analysis.
    Returns JSON with discovered_routes, route_metadata, detected_services,
    ui_components, and deployment_platform. Supports Next.js, SvelteKit,
    Nuxt, React Router, and WordPress. Pass app_url to enable Playwright
    crawler fallback when static analysis finds few routes.
    """
    return discover_routes_tool(project_path, framework=framework, app_url=app_url)


@mcp.tool
def analyze_codebase(
    project_path: str,
    discovered_routes: list[str] | None = None,
) -> str:
    """Analyze codebase structure using tree-sitter parsing.
    Extracts code chunks (functions, classes), error patterns, and data models
    (Prisma, Drizzle). No AI calls — fully deterministic. Returns JSON with
    code_chunks, error_patterns, data_models, and file counts.
    """
    return analyze_codebase_tool(project_path, discovered_routes=discovered_routes)


def run_server():
    """Start the KodaDocs MCP server (stdio transport)."""
    mcp.run()
