# KodaDocs

AI-generated help docs for your web app — in minutes, not weeks.

KodaDocs is an open-source Claude Code MCP tool. Install it, tell Claude "Generate docs for my app", and get a complete help center with annotated screenshots and AI-written articles. Free to self-host. $12/mo for hosted deploy to `yourapp.kodadocs.com`.

## Quick Start

```bash
pip install kodadocs
playwright install chromium
```

Add the MCP server to your Claude Code config (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "kodadocs": {
      "command": "uvx",
      "args": ["kodadocs", "mcp"]
    }
  }
}
```

Then tell Claude:

> "Generate help docs for my app"

Claude reads your code, captures screenshots, writes documentation, and assembles a VitePress help center — all through MCP tools.

## How It Works

```
1. pip install kodadocs
2. Add MCP server to Claude Code
3. Tell Claude: "Generate docs for my app"
4. Claude discovers routes, captures screenshots, writes articles
5. Get a complete VitePress help center in ./docs/
6. Self-host for free, or deploy to yourapp.kodadocs.com (Pro)
```

## What Claude Does (via MCP tools)

| Phase | What happens |
|-------|-------------|
| **Discovery** | Detects framework, discovers routes from code |
| **Capture** | Launches headless browser, authenticates, captures screenshots |
| **Annotation** | Draws numbered callouts on UI elements |
| **Doc Writing** | Claude writes all articles directly (Getting Started, Feature Guides, FAQ, Troubleshooting) |
| **Assembly** | Assembles VitePress site with branding, search, and mobile layout |
| **Deploy** | Deploys to Cloudflare, Vercel, Netlify, GitHub Pages, or kodadocs.com |

## MCP Tools

| Tool | Description |
|------|-------------|
| `detect_framework` | Auto-detect web framework from project files |
| `capture_screenshots` | Headless browser capture with auth and validation |
| `annotate_screenshots` | Pillow numbered callouts + PII blur |
| `assemble_vitepress` | Build complete VitePress site from articles + screenshots |
| `deploy_site` | Deploy to hosting provider |
| `save_manifest` | Persist pipeline state |
| `load_manifest` | Load pipeline state |

## Claude Code Skill

KodaDocs includes a skill file (`skill/kodadocs.md`) that teaches Claude how to orchestrate the full pipeline. Install the skill to get guided doc generation.

## Free vs Pro

| | Free | Pro ($12/mo) |
|---|---|---|
| Generation | Unlimited | Unlimited |
| Output | Local `./docs/` folder | Local + one-command deploy |
| Hosting | Self-host (Vercel/Netlify/etc.) | `yourapp.kodadocs.com` |
| Custom domain | No | `help.yourapp.com` via CNAME |
| Embeddable widget | No | `<script>` tag → help sidebar in your app |
| Branding | "Powered by KodaDocs" badge | Badge removable |
| Feedback + analytics | No | "Was this helpful?" + search analytics dashboard |
| Auto-regen on deploy | No | Webhook/GitHub Action updates docs on push |
| Password protection | No | Token gate for customer-only docs |

Users bring their own Anthropic API key — generation is never gated.

## CLI (Power Users)

KodaDocs also has CLI commands for direct usage without Claude Code:

```bash
kodadocs generate .                        # Run full pipeline
kodadocs generate . --url http://localhost:3000  # Override app URL
kodadocs deploy . --provider cloudflare    # Deploy to provider
kodadocs init .                            # Interactive setup wizard
kodadocs config .                          # View/update config
```

## License

MIT
