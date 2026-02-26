# KodaDocs

[![PyPI version](https://img.shields.io/pypi/v/kodadocs)](https://pypi.org/project/kodadocs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/Kodadocs/kodadocs/actions/workflows/ci.yml/badge.svg)](https://github.com/Kodadocs/kodadocs/actions/workflows/ci.yml)

AI-generated help docs for your web app — in minutes, not weeks.

KodaDocs is an open-source Claude Code MCP tool. Install it, tell Claude "Generate docs for my app", and get a complete help center with annotated screenshots and AI-written articles. Free to self-host. $12/mo for hosted deploy to `yourapp.kodadocs.com`.

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

Claude reads your code, captures screenshots, writes documentation, and assembles a VitePress help center — all through MCP tools.

## How It Works

```
Your web app ──► KodaDocs ──► Complete help center
                   │
                   ├── Detects framework (Next.js, Django, Flask, WordPress, ...)
                   ├── Discovers routes from source code
                   ├── Launches headless browser & authenticates
                   ├── Captures screenshots with PII blurring
                   ├── Draws numbered callouts on UI elements
                   ├── Claude writes all articles
                   └── Assembles VitePress site & deploys
```

| Phase | What happens |
|-------|-------------|
| **Discovery** | Detects framework, discovers routes from code |
| **Capture** | Launches headless browser, authenticates, captures screenshots |
| **Annotation** | Draws numbered callouts on UI elements |
| **Doc Writing** | Claude writes all articles (Getting Started, Feature Guides, FAQ, Troubleshooting) |
| **Assembly** | Assembles VitePress site with branding, search, and mobile layout |
| **Deploy** | Deploys to Cloudflare, Vercel, Netlify, GitHub Pages, or kodadocs.com |

## Supported Frameworks

Next.js, Nuxt, React, Vue, Angular, SvelteKit, Remix, Astro, Django, Flask, FastAPI, Rails, Laravel, Express, Hono, WordPress, Chrome Extensions, and more.

## MCP Tools

| Tool | Description |
|------|-------------|
| `detect_framework` | Auto-detect web framework from project files |
| `capture_screenshots` | Headless browser capture with auth and validation |
| `annotate_screenshots` | Pillow numbered callouts + PII blur |
| `assemble_vitepress` | Build complete VitePress site from articles + screenshots |
| `deploy_site` | Deploy to hosting provider |
| `save_manifest` / `load_manifest` | Persist and load pipeline state |

## Claude Code Skill

KodaDocs includes a [skill file](kodadocs/skill/kodadocs.md) that teaches Claude how to orchestrate the full pipeline. To install it:

```bash
mkdir -p .claude/skills
cp kodadocs/skill/kodadocs.md .claude/skills/kodadocs.md
```

## CLI

KodaDocs also works as a standalone CLI without Claude Code:

```bash
kodadocs generate .                              # Run full pipeline
kodadocs generate . --url http://localhost:3000   # Override app URL
kodadocs generate . --user admin --pass secret    # Auth-gated apps
kodadocs deploy . --provider cloudflare           # Deploy to provider
kodadocs init .                                   # Interactive setup wizard
kodadocs config .                                 # View/update config
kodadocs mcp                                      # Start MCP server
```

## Auth-Gated Apps

KodaDocs handles apps behind login walls automatically:

1. Provide credentials via `kodadocs init` or `--user` / `--pass` flags
2. KodaDocs logs in via headless browser, saves the session
3. Post-auth crawl discovers routes invisible to unauthenticated visitors
4. All screenshots are captured in the authenticated session

## API Key

KodaDocs requires an [Anthropic API key](https://console.anthropic.com/) to generate documentation.

**With Claude Code (MCP):** The API key is provided automatically — no setup needed.

**With the CLI:** Set the key in your environment:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Free vs Pro

| | Free | Pro ($12/mo) |
|---|---|---|
| Generation | Unlimited | Unlimited |
| Output | Local `./docs/` folder | Local + one-command deploy |
| Hosting | Self-host (Vercel/Netlify/etc.) | `yourapp.kodadocs.com` |
| Custom domain | No | `help.yourapp.com` via CNAME |
| Branding | "Powered by KodaDocs" badge | Badge removable |

Users bring their own Anthropic API key — generation is never gated.

## Contributing

See [CONTRIBUTING.md](kodadocs/CONTRIBUTING.md) for development setup and guidelines.

## License

MIT
