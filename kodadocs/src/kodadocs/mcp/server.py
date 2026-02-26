from fastmcp import FastMCP
from kodadocs.mcp.tools.framework import detect_framework_tool
from kodadocs.mcp.tools.capture import capture_screenshots_tool
from kodadocs.mcp.tools.annotation import annotate_screenshots_tool
from kodadocs.mcp.tools.output import assemble_vitepress_tool
from kodadocs.mcp.tools.manifest import save_manifest_tool, load_manifest_tool
from kodadocs.mcp.tools.deploy import deploy_site_tool

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
    Returns JSON with screenshots dict and dom_elements dict.
    """
    return capture_screenshots_tool(
        routes, app_url, auth, output_dir, blur_pii=blur_pii
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
    Pass license_key for KodaDocs Pro features (badge removal, hosted deploy — coming soon).
    """
    return deploy_site_tool(
        site_dir,
        project_name,
        provider=provider,
        detected_platform=detected_platform,
        license_key=license_key,
        site_slug=site_slug,
    )


def run_server():
    """Start the KodaDocs MCP server (stdio transport)."""
    mcp.run()
