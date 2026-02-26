# KodaDocs Claude Code Skill

Generate end-user help documentation for your web app directly from Claude Code.

## Prerequisites

- Claude Code with Pro or Max subscription
- Python 3.12+
- kodadocs installed: `pip install kodadocs` or `uvx install kodadocs`
- Your web app running locally (for screenshots)

## Installation

### 1. Configure the MCP server

Add to your project's `.claude/settings.json` (or global `~/.claude/settings.json`):

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

### 2. Install the skill

Copy `kodadocs.md` to your Claude Code skills directory, or reference it in your project's `.claude/settings.json`.

## Usage

In Claude Code, run:

```
/kodadocs
```

This generates a complete help center for your project:
- Getting Started guide
- Feature walkthroughs with annotated screenshots
- FAQ and Troubleshooting sections
- VitePress static site ready to deploy

## How It Works

- **AI work** (code analysis, doc writing) is done by Claude Code natively — covered by your Pro/Max subscription
- **Deterministic work** (screenshots, image annotation, site assembly) runs through the MCP server using the kodadocs Python package
- **Zero API tokens** needed — everything is included in your Claude Code subscription

## Commands

| Command | Description |
|---------|-------------|
| `/kodadocs` | Full pipeline — generate complete help center |
| `/kodadocs generate` | Same as above |
| `/kodadocs update` | Re-scan and regenerate changed pages only |
| `/kodadocs update --feature X` | Regenerate docs for a specific feature |
