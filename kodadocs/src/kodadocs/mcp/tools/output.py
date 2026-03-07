import json
from typing import Optional

from kodadocs.utils.vitepress import assemble_site


def assemble_vitepress_tool(
    articles: list[dict],
    screenshots_dir: str,
    brand_color: str,
    logo_path: Optional[str],
    output_dir: str,
    project_name: str,
    product_summary: str,
    discovered_routes: list[str],
    hero_tagline: Optional[str] = None,
    hero_cta_text: Optional[str] = None,
    hero_cta_link: Optional[str] = None,
    feature_highlights: Optional[list[dict]] = None,
    show_product_summary: bool = True,
    theme_name: Optional[str] = None,
) -> str:
    """Assemble a VitePress static site from articles and screenshots.
    Delegates to shared utils.vitepress.assemble_site for consistent output.
    Returns JSON with status and output path.
    """
    result = assemble_site(
        articles=articles,
        screenshots_dir=screenshots_dir,
        brand_color=brand_color,
        logo_path=logo_path,
        output_dir=output_dir,
        project_name=project_name,
        product_summary=product_summary,
        discovered_routes=discovered_routes,
        hero_tagline=hero_tagline,
        hero_cta_text=hero_cta_text,
        hero_cta_link=hero_cta_link,
        feature_highlights=feature_highlights,
        show_product_summary=show_product_summary,
        theme_name=theme_name,
    )
    return json.dumps(result)
