import json
import subprocess
from unittest.mock import patch, MagicMock


from kodadocs.utils.deploy import (
    resolve_provider,
    deploy,
    _check_cli,
    _check_env,
)


# ── resolve_provider ────────────────────────────────────────────────────


class TestResolveProvider:
    def test_explicit_wins_over_detected(self):
        assert resolve_provider(explicit="netlify", detected="vercel") == "netlify"

    def test_auto_detects_from_detected(self):
        assert resolve_provider(detected="cloudflare") == "cloudflare"

    def test_unknown_provider_returns_none(self):
        assert resolve_provider(explicit="fly") is None

    def test_normalizes_underscores(self):
        assert resolve_provider(explicit="github_pages") == "github-pages"

    def test_unsupported_detected_returns_none(self):
        for platform in ("fly", "railway", "docker", "heroku"):
            assert resolve_provider(detected=platform) is None

    def test_none_inputs_returns_none(self):
        assert resolve_provider() is None

    def test_case_insensitive(self):
        assert resolve_provider(explicit="Vercel") == "vercel"
        assert resolve_provider(explicit="CLOUDFLARE") == "cloudflare"

    def test_kodadocs_provider_is_supported(self):
        assert resolve_provider(explicit="kodadocs") == "kodadocs"

    def test_all_supported_providers_resolve(self):
        for p in ("cloudflare", "vercel", "netlify", "github-pages", "kodadocs"):
            assert resolve_provider(explicit=p) == p, f"Provider '{p}' should resolve"


# ── Pre-flight validation ───────────────────────────────────────────────


class TestCheckCli:
    @patch("kodadocs.utils.deploy.shutil.which", return_value=None)
    def test_missing_cli_returns_error_with_hint(self, mock_which):
        err = _check_cli("cloudflare")
        assert err is not None
        assert "wrangler" in err
        assert "npm install" in err

    @patch("kodadocs.utils.deploy.shutil.which", return_value="/usr/bin/wrangler")
    def test_present_cli_returns_none(self, mock_which):
        assert _check_cli("cloudflare") is None


class TestCheckEnv:
    def test_missing_env_vars_returns_error(self, monkeypatch):
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
        err = _check_env("cloudflare")
        assert err is not None
        assert "CLOUDFLARE_API_TOKEN" in err

    def test_netlify_needs_both_vars(self, monkeypatch):
        monkeypatch.setenv("NETLIFY_AUTH_TOKEN", "tok")
        monkeypatch.delenv("NETLIFY_SITE_ID", raising=False)
        err = _check_env("netlify")
        assert err is not None
        assert "NETLIFY_SITE_ID" in err

    def test_github_pages_needs_no_env_vars(self, monkeypatch):
        assert _check_env("github-pages") is None

    def test_all_vars_present_returns_none(self, monkeypatch):
        monkeypatch.setenv("VERCEL_TOKEN", "tok")
        assert _check_env("vercel") is None


# ── deploy() integration tests (mocked subprocess) ─────────────────────


class TestDeploy:
    def test_cloudflare_success(self, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        dist.mkdir()
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://my-project.pages.dev\n"
        mock_result.stderr = ""

        with (
            patch(
                "kodadocs.utils.deploy.shutil.which", return_value="/usr/bin/wrangler"
            ),
            patch("kodadocs.utils.deploy.subprocess.run", return_value=mock_result),
        ):
            result = deploy(dist, "my-project", "cloudflare")

        assert result.success is True
        assert result.url == "https://my-project.pages.dev"
        assert result.provider == "cloudflare"

    def test_vercel_success_extracts_url(self, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        dist.mkdir()
        monkeypatch.setenv("VERCEL_TOKEN", "tok")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Deploying...\nhttps://my-app-abc123.vercel.app\nReady!\n"
        mock_result.stderr = ""

        with (
            patch("kodadocs.utils.deploy.shutil.which", return_value="/usr/bin/vercel"),
            patch("kodadocs.utils.deploy.subprocess.run", return_value=mock_result),
        ):
            result = deploy(dist, "my-app", "vercel")

        assert result.success is True
        assert result.url == "https://my-app-abc123.vercel.app"

    def test_unknown_provider_returns_error(self, tmp_path):
        dist = tmp_path / "dist"
        dist.mkdir()
        result = deploy(dist, "proj", "fly")
        assert result.success is False
        assert "Unsupported provider" in result.error

    def test_missing_dist_dir_returns_error(self, tmp_path):
        missing = tmp_path / "nonexistent"
        result = deploy(missing, "proj", "cloudflare")
        assert result.success is False
        assert "not found" in result.error

    def test_subprocess_failure_returns_error(self, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        dist.mkdir()
        monkeypatch.setenv("NETLIFY_AUTH_TOKEN", "tok")
        monkeypatch.setenv("NETLIFY_SITE_ID", "site123")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Authentication failed"

        with (
            patch(
                "kodadocs.utils.deploy.shutil.which", return_value="/usr/bin/netlify"
            ),
            patch("kodadocs.utils.deploy.subprocess.run", return_value=mock_result),
        ):
            result = deploy(dist, "proj", "netlify")

        assert result.success is False
        assert "Authentication failed" in result.error

    def test_timeout_returns_error(self, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        dist.mkdir()
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

        with (
            patch(
                "kodadocs.utils.deploy.shutil.which", return_value="/usr/bin/wrangler"
            ),
            patch(
                "kodadocs.utils.deploy.subprocess.run",
                side_effect=subprocess.TimeoutExpired("wrangler", 120),
            ),
        ):
            result = deploy(dist, "proj", "cloudflare")

        assert result.success is False
        assert "timed out" in result.error

    def test_missing_cli_returns_install_hint(self, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        dist.mkdir()
        monkeypatch.setenv("VERCEL_TOKEN", "tok")

        with patch("kodadocs.utils.deploy.shutil.which", return_value=None):
            result = deploy(dist, "proj", "vercel")

        assert result.success is False
        assert "npm install" in result.error

    def test_deploy_injects_badge(self, tmp_path, monkeypatch):
        """Badge is injected into HTML files before deploying (free tier)."""
        dist = tmp_path / "dist"
        dist.mkdir()
        html = dist / "index.html"
        html.write_text("<html><head></head><body></body></html>")

        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://proj.pages.dev\n"
        mock_result.stderr = ""

        with (
            patch("kodadocs.utils.deploy.is_pro", return_value=False),
            patch(
                "kodadocs.utils.deploy.shutil.which", return_value="/usr/bin/wrangler"
            ),
            patch("kodadocs.utils.deploy.subprocess.run", return_value=mock_result),
        ):
            deploy(dist, "proj", "cloudflare")

        content = html.read_text()
        assert "kodadocs-badge" in content
        assert "Powered by KodaDocs" in content


# ── MCP tool tests ─────────────────────────────────────────────────────


class TestMcpDeployTool:
    def test_success_returns_ok_and_url(self, tmp_path, monkeypatch):
        from kodadocs.mcp.tools.deploy import deploy_site_tool

        # Create a fake dist dir
        site_dir = tmp_path / "docs"
        vitepress_dist = site_dir / ".vitepress" / "dist"
        vitepress_dist.mkdir(parents=True)

        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://mysite.pages.dev\n"
        mock_result.stderr = ""

        with (
            patch(
                "kodadocs.utils.deploy.shutil.which", return_value="/usr/bin/wrangler"
            ),
            patch("kodadocs.utils.deploy.subprocess.run", return_value=mock_result),
        ):
            raw = deploy_site_tool(str(site_dir), "mysite", provider="cloudflare")

        data = json.loads(raw)
        assert data["status"] == "ok"
        assert data["url"] == "https://mysite.pages.dev"
        assert data["provider"] == "cloudflare"

    def test_no_provider_returns_error(self, tmp_path):
        from kodadocs.mcp.tools.deploy import deploy_site_tool

        site_dir = tmp_path / "docs"
        site_dir.mkdir()

        raw = deploy_site_tool(str(site_dir), "mysite")
        data = json.loads(raw)
        assert data["status"] == "error"
        assert "provider" in data["error"].lower()

    def test_accepts_license_key_and_site_slug(self, tmp_path, monkeypatch):
        """deploy_site_tool accepts license_key and site_slug without error."""
        from kodadocs.mcp.tools.deploy import deploy_site_tool

        site_dir = tmp_path / "docs"
        vitepress_dist = site_dir / ".vitepress" / "dist"
        vitepress_dist.mkdir(parents=True)
        (vitepress_dist / "index.html").write_text(
            "<html><head></head><body></body></html>"
        )

        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://mysite.pages.dev\n"
        mock_result.stderr = ""

        with (
            patch(
                "kodadocs.utils.deploy.shutil.which", return_value="/usr/bin/wrangler"
            ),
            patch("kodadocs.utils.deploy.subprocess.run", return_value=mock_result),
        ):
            raw = deploy_site_tool(
                str(site_dir),
                "mysite",
                provider="cloudflare",
                license_key="kd_pro_abc12345",
                site_slug="mysite",
            )

        data = json.loads(raw)
        assert data["status"] == "ok"
