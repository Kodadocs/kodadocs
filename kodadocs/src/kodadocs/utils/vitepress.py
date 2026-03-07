"""Shared VitePress site assembly logic.

Single source of truth for generating VitePress config, theme CSS,
index page, article pages, and sidebar — used by both MCP tools and
the CLI pipeline.
"""

import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Optional

from kodadocs.themes.loader import load_theme
from kodadocs.utils.license import is_pro


def slugify(title: str) -> str:
    """Stable, human-readable slug from article title via NFKD normalization."""
    s = unicodedata.normalize("NFKD", title)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "article"


def unique_slug(title: str, seen: dict[str, int]) -> str:
    """Deduplicate slug by appending numeric suffix on collision."""
    base = slugify(title)
    count = seen.get(base, 0)
    seen[base] = count + 1
    return base if count == 0 else f"{base}-{count}"


def extract_tagline(summary: str) -> str:
    """Extract first sentence from product summary, capped at ~120 chars."""
    if not summary:
        return "Help Center"
    # Strip leading markdown headings
    text = re.sub(r"^(?:#{1,6}\s+.*\n*)+", "", summary).strip()
    # Strip bold/italic markers
    text = re.sub(r"[*_]{1,3}", "", text)
    # Strip bullet points
    text = re.sub(r"^[-*]\s+", "", text)
    # Strip JSON blocks that might have leaked through
    text = re.sub(r"```json\s*.*?```", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"\{[\s\S]*\"articles\"[\s\S]*\}", "", text).strip()
    if not text:
        return "Help Center"
    # Get first sentence
    match = re.match(r"([^.!?]+[.!?])", text)
    if match:
        sentence = match.group(1).strip()
    else:
        sentence = text.split("\n")[0].strip()
    if len(sentence) > 120:
        sentence = sentence[:117].rsplit(" ", 1)[0] + "..."
    # Escape double quotes for YAML frontmatter safety
    sentence = sentence.replace('"', '\\"')
    return sentence


def build_feature_cards(articles: list) -> str:
    """Build up to 3 VitePress feature cards from article titles + first sentences."""
    cards = []
    for article in articles[:3]:
        title = article.get("title", "")
        content = article.get("content", "") or article.get("body", "")
        text = re.sub(r"^#[^\n]*\n*", "", content).strip()
        match = re.match(r"([^.!?]+[.!?])", text)
        details = match.group(1).strip() if match else text[:100]
        # Escape quotes for YAML
        details = details.replace('"', '\\"')
        title_escaped = title.replace('"', '\\"')
        if title and details:
            cards.append(f'  - title: "{title_escaped}"\n    details: "{details}"')
    if not cards:
        return ""
    return "features:\n" + "\n".join(cards) + "\n"


DEFAULT_BRAND_COLOR = "#3e8fb0"


def assemble_site(
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
) -> dict:
    """Assemble a VitePress static site from articles and screenshots.

    This is the single source of truth for VitePress generation, used by
    both the MCP assemble_vitepress tool and the CLI pipeline output step.

    Returns dict with status, output_dir, articles_count, and optional warnings.
    """
    _is_pro = is_pro()
    warnings: list[str] = []

    # Pro Kit gate: custom branding
    if not _is_pro:
        if (brand_color and brand_color != DEFAULT_BRAND_COLOR) or logo_path:
            warnings.append(
                "FREE TIER: Custom brand colors and logos require the Pro Kit. "
                "Using default KodaDocs branding. "
                "Get the Pro Kit: https://kodadocs.com/pro"
            )
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
    path_mapping: dict[str, str] = {}
    if src_dir.exists():
        for img_file in src_dir.glob("*.png"):
            shutil.copy(img_file, assets_dir / img_file.name)
            path_mapping[img_file.name] = f"./assets/{img_file.name}"
        for img_file in src_dir.glob("*.gif"):
            shutil.copy(img_file, assets_dir / img_file.name)
            path_mapping[img_file.name] = f"./assets/{img_file.name}"
        annotated_dir = src_dir / "annotated"
        if annotated_dir.exists():
            for img_file in annotated_dir.glob("*.png"):
                dest_name = f"annotated-{img_file.name}"
                shutil.copy(img_file, assets_dir / dest_name)
                path_mapping[img_file.name] = f"./assets/{dest_name}"
            for img_file in annotated_dir.glob("*.gif"):
                dest_name = f"annotated-{img_file.name}"
                shutil.copy(img_file, assets_dir / dest_name)
                path_mapping[img_file.name] = f"./assets/{dest_name}"

    # Build sidebar (compute first for hero link)
    groups: dict[str, list] = {}
    ungrouped: list = []
    first_slug_link: str | None = None
    seen_slugs: dict[str, int] = {}

    for article in articles:
        title = article["title"]
        slug = unique_slug(title, seen_slugs)
        entry = {"text": title, "link": f"/{slug}"}
        if first_slug_link is None:
            first_slug_link = entry["link"]
        group = article.get("group")
        if group:
            groups.setdefault(group, []).append(entry)
        else:
            ungrouped.append(entry)

        # Write article page with path replacement
        body = article.get("content") or article.get("body", "")
        for filename, new_path in path_mapping.items():
            pattern = r"\((?:[^)]*/)?" + re.escape(filename) + r"\)"
            body = re.sub(pattern, f"({new_path})", body)
        (output_path / f"{slug}.md").write_text(body)

    # Sidebar: grouped for Pro, flat for free
    all_entries = []
    for items in groups.values():
        all_entries.extend(items)
    all_entries.extend(ungrouped)

    if _is_pro and groups:
        sidebar = []
        for i, (name, items) in enumerate(groups.items()):
            sidebar.append({
                "text": name,
                "collapsed": i > 0,
                "items": items,
            })
        if ungrouped:
            sidebar.append({"text": "Guide", "collapsed": True, "items": ungrouped})
    else:
        sidebar = [{"text": "Guide", "items": all_entries}]

    # Index page
    guide_link = first_slug_link or "/"
    tagline = hero_tagline or extract_tagline(product_summary)
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
        features_yaml = build_feature_cards(articles)

    summary_body = ""
    if show_product_summary and product_summary:
        summary_body = re.sub(r"^(?:#{1,6}\s+.*\n*)+", "", product_summary).strip()
        summary_body = re.sub(r"[*_]{1,3}", "", summary_body)

    # Escape project name for YAML
    safe_project_name = project_name.replace('"', '\\"')

    index_content = f"""---
layout: home
hero:
  name: "{safe_project_name}"
  text: "Documentation"
  tagline: "{tagline}"
  actions:
    - theme: brand
      text: {cta_text}
      link: {cta_link}
{features_yaml}---

{summary_body}
"""
    # Path replacement in index
    for filename, new_path in path_mapping.items():
        pattern = r"\((?:[^)]*/)?" + re.escape(filename) + r"\)"
        index_content = re.sub(pattern, f"({new_path})", index_content)

    (output_path / "index.md").write_text(index_content)

    # Copy logo
    logo_config = ""
    if logo_path:
        src_logo = Path(logo_path)
        if src_logo.exists():
            dest_name = re.sub(r"[^a-z0-9._-]", "-", src_logo.name.lower())
            shutil.copy(src_logo, assets_dir / dest_name)
            logo_config = f"    logo: '/assets/{dest_name}',\n"

    # Nav items
    if _is_pro and groups:
        nav_items = [{"text": "Home", "link": "/"}]
        for name, items in groups.items():
            if items:
                nav_items.append({"text": name, "link": items[0]["link"]})
    else:
        nav_items = [
            {"text": "Home", "link": "/"},
            {"text": "Guide", "link": guide_link},
        ]
    nav_json = json.dumps(nav_items, indent=6)

    # VitePress config
    config_content = f"""import {{ defineConfig }} from 'vitepress'

export default defineConfig({{
  title: "{safe_project_name} Docs",
  description: "Documentation for {safe_project_name}",
  cleanUrls: true,
  ignoreDeadLinks: true,
  themeConfig: {{
    search: {{ provider: 'local' }},
{logo_config}    nav: {nav_json},
    sidebar: {json.dumps(sidebar, indent=6)},
    socialLinks: []
  }}
}})
"""
    (vitepress_dir / "config.mts").write_text(config_content)

    # Theme CSS
    theme_dir = vitepress_dir / "theme"
    theme_dir.mkdir(exist_ok=True)
    (theme_dir / "index.ts").write_text(
        "import DefaultTheme from 'vitepress/theme'\n"
        "import './style.css'\n\n"
        "export default DefaultTheme\n"
    )

    if theme_name and theme_name != "default":
        try:
            theme = load_theme(theme_name)
            css_content = theme.to_css()
        except ValueError:
            css_content = (
                f":root {{\n"
                f"  --vp-c-brand-1: {brand_color};\n"
                f"  --vp-c-brand-2: {brand_color};\n"
                f"  --vp-c-brand-3: {brand_color};\n"
                f"}}\n"
            )
    else:
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
        pkg_name = project_name.lower().replace(" ", "-").replace('"', "")
        pkg = {
            "name": f"{pkg_name}-docs",
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
    return result
