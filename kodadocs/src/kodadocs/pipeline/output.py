import re
import shutil
import json
import subprocess
import unicodedata
from pathlib import Path
from rich.console import Console
from ..models import RunManifest


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
    # Strip leading markdown headings (any level ##, ###, etc.) and blank lines
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
        # Fall back to first line only, not entire text
        sentence = text.split("\n")[0].strip()
    if len(sentence) > 120:
        sentence = sentence[:117].rsplit(" ", 1)[0] + "..."
    # Escape double quotes for YAML frontmatter safety
    sentence = sentence.replace('"', '\\"')
    return sentence


def _build_feature_cards(articles: list) -> str:
    """Build up to 3 VitePress feature cards from article titles + first sentences."""
    cards = []
    for article in articles[:3]:
        title = article.get("title", "")
        content = article.get("content", "")
        # Strip markdown heading and get first sentence
        text = re.sub(r"^#[^\n]*\n*", "", content).strip()
        match = re.match(r"([^.!?]+[.!?])", text)
        details = match.group(1).strip() if match else text[:100]
        if title and details:
            cards.append(f'  - title: "{title}"\n    details: "{details}"')
    if not cards:
        return ""
    return "features:\n" + "\n".join(cards) + "\n"


def output_step(manifest: RunManifest):
    output_path = manifest.config.output_path
    project_path = manifest.config.project_path
    console = Console()

    console.print(f"Generating VitePress documentation at {output_path}...")

    # 1. Create output directory structure
    output_path.mkdir(exist_ok=True, parents=True)
    assets_dir = output_path / "assets"
    assets_dir.mkdir(exist_ok=True)
    vitepress_dir = output_path / ".vitepress"
    vitepress_dir.mkdir(exist_ok=True)

    # 2. Copy screenshots to assets
    path_mapping = {}

    # We look for screenshots in the standard location first
    screenshots_src_dir = project_path / ".kodadocs" / "screenshots"

    for route, rel_path in manifest.screenshots.items():
        # Try to find the source file
        # rel_path might be the original (.kodadocs/screenshots/...) or already updated (./assets/...)
        src_path = project_path / rel_path

        # If it doesn't exist at rel_path, try the default screenshots dir
        if not src_path.exists():
            # Extract just the filename
            filename = Path(rel_path).name
            src_path = screenshots_src_dir / filename

        if src_path.exists():
            dest_name = src_path.name
            shutil.copy(src_path, assets_dir / dest_name)

            # Store mapping for replacement
            # We want to replace anything that looks like a path ending in this filename
            # e.g., .kodadocs/screenshots/login.png or .//.kodadocs/screenshots/login.png
            new_path = f"./assets/{dest_name}"
            path_mapping[dest_name] = new_path

            # Update manifest to point to new asset location for docs
            manifest.screenshots[route] = new_path

    # 3. Generate Article pages and Sidebar Config (compute sidebar FIRST for hero link)
    sidebar = []
    seen_slugs: dict[str, int] = {}

    for article in manifest.articles:
        title = article.get("title", "Untitled")
        content = article.get("content", "")
        if not content:
            continue
        slug = _unique_slug(title, seen_slugs)
        sidebar.append({"text": title, "link": f"/{slug}"})

        # Replace old screenshot paths with new asset paths
        for filename, new_path in path_mapping.items():
            # Replace markdown image links: ![alt](path/to/filename.png) -> ![alt](./assets/filename.png)
            # We look for the filename preceded by common path characters
            pattern = r"\((?:[^)]*/)?" + re.escape(filename) + r"\)"
            content = re.sub(pattern, f"({new_path})", content)

        with open(output_path / f"{slug}.md", "w") as f:
            f.write(content)

    # 4. Generate Index page (after sidebar so we can use sidebar[0] for hero link)
    guide_link = sidebar[0]["link"] if sidebar else "/"
    tagline = _extract_tagline(manifest.product_summary or "")
    features_yaml = _build_feature_cards(manifest.articles)
    summary_body = manifest.product_summary or ""
    # Strip leading markdown heading if present
    summary_body = re.sub(r"^#\s+.*\n*", "", summary_body).strip()

    index_content = f"""---
layout: home
hero:
  name: "{project_path.name}"
  text: "Documentation"
  tagline: "{tagline}"
  actions:
    - theme: brand
      text: Get Started
      link: {guide_link}
{features_yaml}---

{summary_body}
"""
    # Robust replacement for screenshot paths in index
    for filename, new_path in path_mapping.items():
        pattern = r"\(.*?" + re.escape(filename) + r"\)"
        index_content = re.sub(pattern, f"({new_path})", index_content)

    with open(output_path / "index.md", "w") as f:
        f.write(index_content)

    # 5. Generate VitePress Config

    config_content = f"""import {{ defineConfig }} from 'vitepress'

export default defineConfig({{
  title: "{project_path.name} Docs",
  description: "Documentation for {project_path.name}",
  cleanUrls: true,
  ignoreDeadLinks: true,
  themeConfig: {{
    search: {{ provider: 'local' }},
    nav: [
      {{ text: 'Home', link: '/' }},
      {{ text: 'Guide', link: '{guide_link}' }}
    ],
    sidebar: [
      {{
        text: 'Guide',
        items: {json.dumps(sidebar, indent=2)}
      }}
    ],
    socialLinks: []
  }}
}})
"""
    with open(vitepress_dir / "config.mts", "w") as f:
        f.write(config_content)

    # 5.1 Generate Theme with Brand Color
    theme_dir = vitepress_dir / "theme"
    theme_dir.mkdir(exist_ok=True)

    with open(theme_dir / "index.ts", "w") as f:
        f.write("""import DefaultTheme from 'vitepress/theme'
import './style.css'

export default DefaultTheme
""")

    brand_color = manifest.config.brand_color or "#3e8fb0"
    with open(theme_dir / "style.css", "w") as f:
        f.write(f"""/**
 * Customizing the brand color
 */
:root {{
  --vp-c-brand-1: {brand_color};
  --vp-c-brand-2: {brand_color}; /* Darker/Lighter variant ideally */
  --vp-c-brand-3: {brand_color};
}}
""")

    # 6. Generate package.json if needed
    if not (output_path / "package.json").exists():
        pkg_json = {
            "name": f"{project_path.name.lower().replace(' ', '-')}-docs",
            "version": "1.0.0",
            "scripts": {
                "docs:dev": "vitepress dev",
                "docs:build": "vitepress build",
                "docs:preview": "vitepress preview",
            },
            "devDependencies": {"vitepress": "~1.6.0"},
        }
        with open(output_path / "package.json", "w") as f:
            f.write(json.dumps(pkg_json, indent=2))

    # 7. Generate Instructions
    with open(output_path / "README.md", "w") as f:
        f.write(f"""# {project_path.name} Documentation

Generated by KodaDocs.

## Running Locally

1. Install dependencies:
   ```bash
   npm install
   ```

2. Start the dev server:
   ```bash
   npm run docs:dev
   ```

3. Build for production:
   ```bash
   npm run docs:build
   ```
""")

    console.print(
        f"[bold green]Documentation generated successfully in {output_path}[/bold green]"
    )

    # 8. Automated Build Step
    def run_command(cmd, cwd):
        try:
            console.print(f"Running '{' '.join(cmd)}' in {cwd}...")
            subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Command failed: {e.stderr.decode()}[/red]")
            return False
        except FileNotFoundError:
            console.print(f"[red]Command not found: {cmd[0]}[/red]")
            return False

    if (output_path / "package.json").exists():
        console.print("Starting automated VitePress build...")
        if run_command(["npm", "install"], output_path):
            if run_command(["npm", "run", "docs:build"], output_path):
                console.print(
                    "[bold green]VitePress site built successfully![/bold green]"
                )
                console.print(
                    f"Static files are ready in: {output_path / '.vitepress' / 'dist'}"
                )
            else:
                console.print(
                    "[yellow]Build failed. You may need to run 'npm run docs:build' manually.[/yellow]"
                )
        else:
            console.print(
                "[yellow]Install failed. Please ensure Node.js and npm are installed.[/yellow]"
            )

    console.print(
        "Run 'npm run docs:dev' in the docs folder to start a local preview server."
    )
