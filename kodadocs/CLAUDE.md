# KodaDocs — Claude Code MCP Integration

## MCP Pipeline Contract

When generating documentation for a project, call the tools in this exact order.
Each step's output feeds into the next. All tools return JSON strings.

### Required Pipeline Order

```
1. detect_framework(project_path)
   → Returns framework name (e.g., "Next.js")

2. discover_routes(project_path, framework, app_url?)
   → Returns { discovered_routes, route_metadata, detected_services, ui_components, deployment_platform }

3. analyze_codebase(project_path, discovered_routes?)
   → Returns { code_chunks, error_patterns, data_models }

4. capture_screenshots(routes, app_url, auth?, output_dir)
   → Returns { screenshots: {route: path}, dom_elements: {route: elements}, pii_regions }

5. annotate_screenshots(screenshots_dir, dom_elements, brand_color?, pii_regions?)
   → Returns { annotated: {route: path} }

6. [YOU write the articles using the context from steps 1-5]
   → Create a list of article objects: { title, content (markdown), group? }

7. assemble_vitepress(articles, screenshots_dir, brand_color, logo_path?, output_dir, project_name, product_summary, discovered_routes, ...)
   → Returns { output_dir, articles_count }

8. deploy_site(site_dir, project_name, provider?, license_key?, site_slug?)
   → Returns { url, provider }
```

### Data Flow Between Tools

- **Step 2 → Step 4**: Pass `discovered_routes` from discover_routes as `routes` to capture_screenshots.
- **Step 4 → Step 5**: Pass the `screenshots` directory and `dom_elements` dict from capture_screenshots to annotate_screenshots.
- **Step 4 → Step 5**: Pass `pii_regions` from capture_screenshots to annotate_screenshots.
- **Steps 1-5 → Step 6**: Use all accumulated context (routes, screenshots, dom_elements, code_chunks, error_patterns, data_models, detected_services) to write high-quality documentation articles.
- **Step 6 → Step 7**: Pass your written articles to assemble_vitepress.

### State Persistence

Use `save_manifest` and `load_manifest` to persist pipeline state between sessions:
- Call `load_manifest(project_path)` at the start to check for previous runs
- Call `save_manifest(manifest, project_path)` after key steps to enable resumption

### Article Writing Guidelines

When writing articles (Step 6), you are acting as an expert technical documentation writer:

- Write task-oriented content: "How to [accomplish X]" not "The X page"
- Reference UI elements by their callout numbers from annotated screenshots: "Click **Save** [3]"
- Embed screenshots with: `![Description](path/to/screenshot.png)`
- Use consistent H1 for title, H2 for sections, H3 for subsections
- Include a brief overview paragraph after the H1
- For complex features, use numbered step-by-step instructions
- Mention detected services by name (e.g., "Authentication is powered by Clerk")
- If error patterns were found, include a Troubleshooting section
- Group related articles with the `group` field for organized sidebar navigation

### Pro Kit Features

The Pro Kit is a set of installable skill files that unlock advanced capabilities.
Pro Kit is detected by checking for skill directories in `~/.claude/skills/`.

**Free (base)**: 15 pages, default theme, basic capture, self-host with badge.
**Pro Kit (installed skills)**: Unlimited pages, all themes, auth capture, targeted screenshots, GIF recording, custom branding, no badge.

The `license_key` parameter is ONLY needed for `deploy_site` when deploying to kodadocs.com hosting.

## Project Structure

- `src/kodadocs/mcp/` — MCP tool definitions (thin wrappers)
- `src/kodadocs/pipeline/` — Core pipeline step implementations
- `src/kodadocs/utils/` — Shared utilities (framework detection, deploy, license, vitepress assembly)
- `src/kodadocs/themes/` — Theme presets and loader
- `src/kodadocs/models.py` — Pydantic models (SessionConfig, RunManifest)
- `src/kodadocs/orchestrator.py` — CLI pipeline orchestrator
- `src/kodadocs/main.py` — Typer CLI entry point
