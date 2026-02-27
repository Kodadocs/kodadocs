# KodaDocs

[![PyPI version](https://img.shields.io/pypi/v/kodadocs)](https://pypi.org/project/kodadocs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

**End-user ready help docs for your web app — generated in minutes, not written over weeks.**

Most doc tools produce developer-facing references. KodaDocs produces the kind of help center your customers actually use: annotated screenshots, step-by-step guides, Getting Started walkthroughs, FAQ, and troubleshooting — all written in plain language, styled with your branding, and ready to ship the moment it's generated.

Install the MCP tool, tell Claude "Generate docs for my app", and get a complete, polished help center. No editing pass required. Free to self-host. $12/mo for hosted deploy to `yourapp.kodadocs.com`.

## Quick Start

```bash
pip install kodadocs
playwright install chromium
```

Or run without installing:

```bash
uvx kodadocs --help
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

Claude reads your code, captures screenshots, writes user-facing documentation, and assembles a ready-to-ship help center — all through MCP tools. The output is end-user ready: your customers can start using it immediately.

## What You Get

The output isn't a rough draft — it's a production help center your users can navigate on day one:

- **Getting Started guide** that walks new users through setup and first actions
- **Feature guides** with numbered, annotated screenshots showing exactly where to click
- **FAQ and Troubleshooting** pages covering common questions and error states
- **Full-text search**, responsive layout, and your brand colors baked in
- **Deployable immediately** — no review cycle, no copy-editing, no formatting cleanup

## How It Works (via MCP tools)

| Phase | What happens |
|-------|-------------|
| **Discovery** | Detects framework, discovers routes from code |
| **Capture** | Launches headless browser, authenticates, captures screenshots |
| **Annotation** | Draws numbered callouts on UI elements |
| **Doc Writing** | Claude writes end-user articles — plain language, task-oriented, with screenshot references |
| **Assembly** | Assembles VitePress site with branding, search, and mobile layout |
| **Deploy** | Deploys to Cloudflare, Vercel, Netlify, GitHub Pages, or kodadocs.com |

## MCP Tools

| Tool | Description |
|------|-------------|
| `detect_framework` | Auto-detect web framework from project files |
| `discover_routes` | Static analysis of routes, services, and metadata |
| `analyze_codebase` | Tree-sitter parsing for code chunks, error patterns, data models |
| `capture_screenshots` | Headless browser capture with auth and PII blur |
| `annotate_screenshots` | Numbered callouts on UI elements via Pillow |
| `assemble_vitepress` | Build complete VitePress site from articles + screenshots |
| `deploy_site` | Deploy to hosting provider |
| `save_manifest` | Persist pipeline state |
| `load_manifest` | Load pipeline state |

## Claude Code Skill

KodaDocs includes a [skill file](skill/kodadocs.md) that teaches Claude how to orchestrate the full pipeline. To install it, copy `skill/kodadocs.md` into your project's `.claude/skills/` directory:

```bash
mkdir -p .claude/skills
cp skill/kodadocs.md .claude/skills/kodadocs.md
```

## Free vs Pro

| | Free | Pro ($12/mo) |
|---|---|---|
| Generation | Unlimited | Unlimited |
| Output | Local `./docs/` folder | Local + one-command deploy |
| Hosting | Self-host (Vercel/Netlify/etc.) | `yourapp.kodadocs.com` |
| Custom domain | No | `help.yourapp.com` via CNAME |
| Themes | Default theme | 6 premium themes + custom brand colors, fonts, dark mode |
| Analytics | No | Search queries, article feedback, page views |
| Branding | "Powered by KodaDocs" badge | Badge removable |

Users bring their own Anthropic API key — generation is never gated.

## API Key

KodaDocs requires an [Anthropic API key](https://console.anthropic.com/) to generate documentation.

**With Claude Code (MCP):** The API key is provided automatically — no setup needed.

**With the CLI:** Set the key in your environment or in a `.env` file in your project root:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Or create a `.env` file in your project directory:

```
ANTHROPIC_API_KEY=sk-ant-...
```

KodaDocs loads `.env` automatically — no extra dependencies required.

## CLI

KodaDocs also has CLI commands for direct usage without Claude Code:

```bash
kodadocs generate .                              # Run full pipeline
kodadocs generate . --url http://localhost:3000   # Override app URL
kodadocs deploy . --provider cloudflare           # Deploy to provider
kodadocs init .                                   # Interactive setup wizard
kodadocs config .                                 # View/update config
kodadocs mcp                                      # Start MCP server
```

## License

MIT
