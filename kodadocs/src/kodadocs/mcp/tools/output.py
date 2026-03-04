import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Optional

from kodadocs.themes.loader import load_theme
from kodadocs.utils.license import is_pro_key
from kodadocs.utils.messaging import branding_gate_warning


def _slugify(title: str) -> str:
    """Stable, human-readable slug from article title via NFKD normalization."""
    s = unicodedata.normalize("NFKD", title)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "article"


def _unique_slug(title: str, seen: dict[str, int]) -> str:
    """Deduplicate slug by appending numeric suffix on collision."""
    base = _slugify(title)
    count = seen.get(base, 0)
    seen[base] = count + 1
    return base if count == 0 else f"{base}-{count}"


def _extract_tagline(summary: str) -> str:
    """Extract first sentence from product summary, capped at ~120 chars."""
    if not summary:
        return "Help Center"
    text = re.sub(r"^#\s+.*\n*", "", summary).strip()
    match = re.match(r"([^.!?]+[.!?])", text)
    sentence = match.group(1).strip() if match else text
    if len(sentence) > 120:
        sentence = sentence[:117].rsplit(" ", 1)[0] + "..."
    return sentence


def _build_feature_cards(articles: list) -> str:
    """Build up to 3 VitePress feature cards from article titles + first sentences."""
    cards = []
    for article in articles[:3]:
        title = article.get("title", "")
        content = article.get("content", "") or article.get("body", "")
        text = re.sub(r"^#[^\n]*\n*", "", content).strip()
        match = re.match(r"([^.!?]+[.!?])", text)
        details = match.group(1).strip() if match else text[:100]
        if title and details:
            cards.append(f'  - title: "{title}"\n    details: "{details}"')
    if not cards:
        return ""
    return "features:\n" + "\n".join(cards) + "\n"


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
    license_key: Optional[str] = None,
) -> str:
    """Assemble a VitePress static site from articles and screenshots.
    Returns JSON with status and output path.
    """
    DEFAULT_BRAND_COLOR = "#3e8fb0"
    warnings: list[str] = []
    _is_pro = is_pro_key(license_key)

    # MCP-layer soft gating for branding
    if not _is_pro:
        if (brand_color and brand_color != DEFAULT_BRAND_COLOR) or logo_path:
            warnings.append(branding_gate_warning())
        brand_color = DEFAULT_BRAND_COLOR
        logo_path = None

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    assets_dir = output_path / "assets"
    assets_dir.mkdir(exist_ok=True)
    vitepress_dir = output_path / ".vitepress"
    vitepress_dir.mkdir(exist_ok=True)

    # Copy screenshots and GIFs to assets
    src_dir = Path(screenshots_dir)
    if src_dir.exists():
        for img_file in src_dir.glob("*.png"):
            shutil.copy(img_file, assets_dir / img_file.name)
        for img_file in src_dir.glob("*.gif"):
            shutil.copy(img_file, assets_dir / img_file.name)
        annotated_dir = src_dir / "annotated"
        if annotated_dir.exists():
            for img_file in annotated_dir.glob("*.png"):
                shutil.copy(img_file, assets_dir / f"annotated-{img_file.name}")
            for img_file in annotated_dir.glob("*.gif"):
                shutil.copy(img_file, assets_dir / f"annotated-{img_file.name}")

    # Generate article pages and sidebar (compute sidebar FIRST for hero link)
    # Group articles by "group" field if present
    groups: dict[str, list] = {}
    ungrouped: list = []
    first_slug_link: str | None = None
    seen_slugs: dict[str, int] = {}
    for article in articles:
        title = article["title"]
        slug = _unique_slug(title, seen_slugs)
        entry = {"text": title, "link": f"/{slug}"}
        if first_slug_link is None:
            first_slug_link = entry["link"]
        group = article.get("group")
        if group:
            groups.setdefault(group, []).append(entry)
        else:
            ungrouped.append(entry)
        body = article.get("content") or article.get("body", "")
        (output_path / f"{slug}.md").write_text(body)

    # Build sidebar: grouped sections (Pro only), flat "Guide" for free
    all_entries = []
    for items in groups.values():
        all_entries.extend(items)
    all_entries.extend(ungrouped)

    if _is_pro and groups:
        sidebar = [{"text": name, "items": items} for name, items in groups.items()]
        if ungrouped:
            sidebar.append({"text": "Guide", "items": ungrouped})
    else:
        sidebar = [{"text": "Guide", "items": all_entries}]

    # Generate index page (after sidebar so we can use first article for hero link)
    guide_link = first_slug_link or "/"
    tagline = hero_tagline or _extract_tagline(product_summary)
    cta_text = hero_cta_text or "Get Started"
    cta_link = hero_cta_link or guide_link

    if feature_highlights:
        features_yaml = (
            "features:\n"
            + "\n".join(
                f'  - title: "{f["title"]}"\n    details: "{f["details"]}"'
                for f in feature_highlights[:3]
            )
            + "\n"
        )
    else:
        features_yaml = _build_feature_cards(articles)

    summary_body = ""
    if show_product_summary and product_summary:
        summary_body = re.sub(r"^#\s+.*\n*", "", product_summary).strip()

    index_content = f"""---
layout: home
hero:
  name: "{project_name}"
  text: "Documentation"
  tagline: "{tagline}"
  actions:
    - theme: brand
      text: {cta_text}
      link: {cta_link}
{features_yaml}---

{summary_body}
"""
    (output_path / "index.md").write_text(index_content)

    # Copy logo to assets if provided
    logo_config = ""
    if logo_path:
        src_logo = Path(logo_path)
        if src_logo.exists():
            dest_name = re.sub(r"[^a-z0-9._-]", "-", src_logo.name.lower())
            shutil.copy(src_logo, assets_dir / dest_name)
            logo_config = f"    logo: '/assets/{dest_name}',\n"

    # VitePress config
    config_content = f"""import {{ defineConfig }} from 'vitepress'

export default defineConfig({{
  title: "{project_name} Docs",
  description: "Documentation for {project_name}",
  cleanUrls: true,
  ignoreDeadLinks: true,
  themeConfig: {{
    search: {{ provider: 'local' }},
{logo_config}    nav: [
      {{ text: 'Home', link: '/' }},
      {{ text: 'Guide', link: '{guide_link}' }}
    ],
    sidebar: {json.dumps(sidebar, indent=6)},
    socialLinks: []
  }}
}})
"""
    (vitepress_dir / "config.mts").write_text(config_content)

    # Theme with brand color
    theme_dir = vitepress_dir / "theme"
    theme_dir.mkdir(exist_ok=True)
    (theme_dir / "index.ts").write_text(
        "import DefaultTheme from 'vitepress/theme'\n"
        "import './style.css'\n\n"
        "export default DefaultTheme\n"
    )
    # Generate theme CSS
    if theme_name and theme_name != "default":
        try:
            theme = load_theme(theme_name, license_key=license_key)
            css_content = theme.to_css()
        except ValueError:
            # Fall back to brand_color if theme not found
            css_content = (
                f":root {{\n"
                f"  --vp-c-brand-1: {brand_color};\n"
                f"  --vp-c-brand-2: {brand_color};\n"
                f"  --vp-c-brand-3: {brand_color};\n"
                f"}}\n"
            )
    else:
        # Use brand_color directly (backward compatible)
        css_content = (
            f":root {{\n"
            f"  --vp-c-brand-1: {brand_color};\n"
            f"  --vp-c-brand-2: {brand_color};\n"
            f"  --vp-c-brand-3: {brand_color};\n"
            f"}}\n"
        )

    (theme_dir / "style.css").write_text(css_content)

    # package.json
    if not (output_path / "package.json").exists():
        pkg = {
            "name": f"{project_name.lower().replace(' ', '-')}-docs",
            "version": "1.0.0",
            "scripts": {
                "docs:dev": "vitepress dev",
                "docs:build": "vitepress build",
                "docs:preview": "vitepress preview",
            },
            "devDependencies": {"vitepress": "~1.6.0"},
        }
        (output_path / "package.json").write_text(json.dumps(pkg, indent=2))

    result = {
        "status": "ok",
        "output_dir": str(output_path),
        "articles_count": len(articles),
    }
    if warnings:
        result["warnings"] = warnings
    return json.dumps(result)
