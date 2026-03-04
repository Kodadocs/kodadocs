#!/bin/bash

# KodaDocs — Local Development Setup
echo "Setting up KodaDocs..."

# 1. Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# 2. Install dependencies
echo "Installing dependencies..."
.venv/bin/python3 -m pip install -e ".[dev]"

# 3. Install Playwright browser
echo "Installing Playwright Chromium..."
.venv/bin/python3 -m playwright install chromium

# 4. Success message
echo ""
echo "KodaDocs is ready!"
echo "------------------------------------------------"
echo "To use with Claude Code (recommended):"
echo "  Add MCP server to ~/.claude/settings.json:"
echo '  {"mcpServers": {"kodadocs": {"command": "uvx", "args": ["kodadocs", "mcp"]}}}'
echo ""
echo "To use the CLI directly:"
echo "  source .venv/bin/activate"
echo "  kodadocs --help"
echo "------------------------------------------------"
