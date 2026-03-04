"""Unit tests for the corrected deploy commands in _build_command."""

import os
from unittest.mock import patch

from kodadocs.utils.deploy import _build_command


def test_vercel_command_uses_cwd_not_positional(tmp_path):
    """Vercel CLI must use --cwd, not a positional dir argument (Gap 4)."""
    dist_dir = tmp_path / "docs" / ".vitepress" / "dist"
    dist_dir.mkdir(parents=True)

    with patch.dict(os.environ, {"VERCEL_TOKEN": "test-token"}):
        cmd = _build_command("vercel", dist_dir, "my-project")

    assert "--cwd" in cmd
    assert str(tmp_path / "docs") in cmd  # docs root, not dist dir
    assert "--yes" in cmd
    assert "--prod" in cmd
    assert "--token" in cmd
    assert "test-token" in cmd
    # Must NOT have "deploy" subcommand or positional dist path
    assert "deploy" not in cmd
    assert str(dist_dir) not in cmd


def test_netlify_command_includes_no_build(tmp_path):
    """Netlify CLI must include --no-build for pre-built sites."""
    dist_dir = tmp_path / "docs" / ".vitepress" / "dist"
    dist_dir.mkdir(parents=True)

    with patch.dict(
        os.environ, {"NETLIFY_AUTH_TOKEN": "tok", "NETLIFY_SITE_ID": "site123"}
    ):
        cmd = _build_command("netlify", dist_dir, "my-project")

    assert "--no-build" in cmd
    assert "--dir" in cmd
    assert "--prod" in cmd


def test_cloudflare_command_unchanged(tmp_path):
    """Cloudflare command should still use wrangler pages deploy with positional dir."""
    dist_dir = tmp_path / "docs" / ".vitepress" / "dist"
    dist_dir.mkdir(parents=True)

    cmd = _build_command("cloudflare", dist_dir, "my-project")

    assert cmd[0] == "wrangler"
    assert "pages" in cmd
    assert "deploy" in cmd
    assert str(dist_dir) in cmd


def test_github_pages_command_unchanged(tmp_path):
    """GitHub Pages command should still use npx gh-pages -d."""
    dist_dir = tmp_path / "docs" / ".vitepress" / "dist"
    dist_dir.mkdir(parents=True)

    cmd = _build_command("github-pages", dist_dir, "my-project")

    assert cmd[0] == "npx"
    assert "gh-pages" in cmd
    assert "-d" in cmd
