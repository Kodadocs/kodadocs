"""Tests for the KodaDocs hosted deploy path (provider='kodadocs')."""

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import httpx

from kodadocs.utils.deploy import deploy, deploy_to_kodadocs, KODADOCS_API_URL


# ── Helpers ────────────────────────────────────────────────────────────────

VALID_LICENSE_KEY = "kd_pro_" + "a" * 20  # Satisfies is_pro_key() prefix check


def _make_dist(tmp_path: Path, with_html: bool = False) -> Path:
    """Create a minimal dist directory for testing."""
    dist = tmp_path / "dist"
    dist.mkdir()
    if with_html:
        (dist / "index.html").write_text(
            "<html><head></head><body><h1>Hello</h1></body></html>"
        )
    return dist


def _mock_200_response(url: str = "https://myapp.kodadocs.com") -> MagicMock:
    """Return a mock httpx.Response with status 200 and a JSON body."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {"url": url}
    resp.headers = {"content-type": "application/json"}
    return resp


def _mock_error_response(status: int, error_msg: str) -> MagicMock:
    """Return a mock httpx.Response representing an API error."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = {"error": error_msg}
    resp.headers = {"content-type": "application/json"}
    return resp


# ── deploy_to_kodadocs() unit tests ───────────────────────────────────────


class TestDeployToKodadocs:
    def test_success_returns_url_from_api(self, tmp_path):
        dist = _make_dist(tmp_path, with_html=True)
        mock_resp = _mock_200_response("https://myapp.kodadocs.com")

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            result = deploy_to_kodadocs(dist, "myapp", VALID_LICENSE_KEY)

        assert result.success is True
        assert "myapp.kodadocs.com" in result.url
        assert result.provider == "kodadocs"

    def test_api_error_returns_error_message(self, tmp_path):
        dist = _make_dist(tmp_path)
        mock_resp = _mock_error_response(401, "Invalid key")

        with patch("httpx.post", return_value=mock_resp):
            result = deploy_to_kodadocs(dist, "myapp", VALID_LICENSE_KEY)

        assert result.success is False
        assert "Invalid key" in result.error
        assert result.provider == "kodadocs"

    def test_api_non_json_error_uses_status_code_message(self, tmp_path):
        dist = _make_dist(tmp_path)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 500
        resp.headers = {"content-type": "text/plain"}
        resp.json.return_value = {}

        with patch("httpx.post", return_value=resp):
            result = deploy_to_kodadocs(dist, "myapp", VALID_LICENSE_KEY)

        assert result.success is False
        assert "500" in result.error

    def test_timeout_returns_error(self, tmp_path):
        dist = _make_dist(tmp_path)

        with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
            result = deploy_to_kodadocs(dist, "myapp", VALID_LICENSE_KEY)

        assert result.success is False
        assert "timed out" in result.error
        assert result.provider == "kodadocs"

    def test_http_error_returns_error(self, tmp_path):
        dist = _make_dist(tmp_path)

        with patch("httpx.post", side_effect=httpx.ConnectError("connection refused")):
            result = deploy_to_kodadocs(dist, "myapp", VALID_LICENSE_KEY)

        assert result.success is False
        assert "Upload failed" in result.error
        assert result.provider == "kodadocs"

    def test_zip_cleaned_up_on_success(self, tmp_path):
        dist = _make_dist(tmp_path, with_html=True)
        zip_path = dist.parent / "myapp.zip"

        mock_resp = _mock_200_response()

        with patch("httpx.post", return_value=mock_resp):
            deploy_to_kodadocs(dist, "myapp", VALID_LICENSE_KEY)

        # ZIP should be deleted after successful upload
        assert not zip_path.exists(), "ZIP should be cleaned up after success"

    def test_zip_cleaned_up_on_failure(self, tmp_path):
        dist = _make_dist(tmp_path)
        zip_path = dist.parent / "myapp.zip"

        mock_resp = _mock_error_response(500, "Internal error")

        with patch("httpx.post", return_value=mock_resp):
            deploy_to_kodadocs(dist, "myapp", VALID_LICENSE_KEY)

        # ZIP should be deleted even after a failed upload
        assert not zip_path.exists(), "ZIP should be cleaned up after failure"

    def test_zip_cleaned_up_on_exception(self, tmp_path):
        dist = _make_dist(tmp_path)
        zip_path = dist.parent / "myapp.zip"

        with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
            deploy_to_kodadocs(dist, "myapp", VALID_LICENSE_KEY)

        assert not zip_path.exists(), "ZIP should be cleaned up after exception"

    def test_zip_exists_during_upload(self, tmp_path):
        """Verify ZIP is present while httpx.post is executing."""
        dist = _make_dist(tmp_path, with_html=True)
        zip_path = dist.parent / "myapp.zip"
        zip_existed_during_call = []

        def check_zip_exists(*args, **kwargs):
            # During the POST call, the ZIP file should exist
            zip_existed_during_call.append(zip_path.exists())
            return _mock_200_response()

        with patch("httpx.post", side_effect=check_zip_exists):
            deploy_to_kodadocs(dist, "myapp", VALID_LICENSE_KEY)

        assert zip_existed_during_call == [True], "ZIP must exist during httpx.post call"

    def test_sends_correct_headers_and_data(self, tmp_path):
        dist = _make_dist(tmp_path, with_html=True)
        mock_resp = _mock_200_response()
        captured_kwargs = {}

        def capture_call(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_resp

        with patch("httpx.post", side_effect=capture_call):
            deploy_to_kodadocs(dist, "myapp", VALID_LICENSE_KEY)

        assert captured_kwargs["headers"] == {"X-License-Key": VALID_LICENSE_KEY}
        assert captured_kwargs["data"] == {"slug": "myapp"}
        assert "site" in captured_kwargs["files"]

    def test_uses_configurable_api_url(self, tmp_path, monkeypatch):
        dist = _make_dist(tmp_path, with_html=True)
        mock_resp = _mock_200_response()
        monkeypatch.setattr("kodadocs.utils.deploy.KODADOCS_API_URL", "https://staging.kodadocs.com")
        captured_url = []

        def capture_url(url, **kwargs):
            captured_url.append(url)
            return mock_resp

        with patch("httpx.post", side_effect=capture_url):
            deploy_to_kodadocs(dist, "myapp", VALID_LICENSE_KEY)

        assert captured_url[0] == "https://staging.kodadocs.com/deploy"

    def test_fallback_url_when_api_omits_url(self, tmp_path):
        dist = _make_dist(tmp_path, with_html=True)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = {}  # No 'url' key in response
        resp.headers = {"content-type": "application/json"}

        with patch("httpx.post", return_value=resp):
            result = deploy_to_kodadocs(dist, "myapp", VALID_LICENSE_KEY)

        assert result.success is True
        # Fallback URL uses the slug
        assert "myapp.kodadocs.com" in result.url


# ── deploy() integration tests for kodadocs provider ─────────────────────


class TestDeployWithKodadocsProvider:
    def test_success_returns_url(self, tmp_path):
        dist = _make_dist(tmp_path, with_html=True)
        mock_resp = _mock_200_response("https://myapp.kodadocs.com")

        with patch("httpx.post", return_value=mock_resp):
            result = deploy(dist, "myapp", "kodadocs", license_key=VALID_LICENSE_KEY, site_slug="myapp")

        assert result.success is True
        assert "myapp.kodadocs.com" in result.url
        assert result.provider == "kodadocs"

    def test_no_license_key_returns_error(self, tmp_path):
        dist = _make_dist(tmp_path)
        result = deploy(dist, "myapp", "kodadocs", license_key=None, site_slug="myapp")

        assert result.success is False
        assert "Pro license key" in result.error

    def test_free_license_key_returns_error(self, tmp_path):
        dist = _make_dist(tmp_path)
        result = deploy(dist, "myapp", "kodadocs", license_key="notaprokey", site_slug="myapp")

        assert result.success is False
        assert "Pro license key" in result.error

    def test_no_site_slug_returns_error(self, tmp_path):
        dist = _make_dist(tmp_path)
        result = deploy(dist, "myapp", "kodadocs", license_key=VALID_LICENSE_KEY, site_slug=None)

        assert result.success is False
        assert "site slug" in result.error

    def test_empty_site_slug_returns_error(self, tmp_path):
        dist = _make_dist(tmp_path)
        result = deploy(dist, "myapp", "kodadocs", license_key=VALID_LICENSE_KEY, site_slug="")

        assert result.success is False
        assert "site slug" in result.error

    def test_api_error_propagates(self, tmp_path):
        dist = _make_dist(tmp_path)
        mock_resp = _mock_error_response(401, "Invalid key")

        with patch("httpx.post", return_value=mock_resp):
            result = deploy(dist, "myapp", "kodadocs", license_key=VALID_LICENSE_KEY, site_slug="myapp")

        assert result.success is False
        assert "Invalid key" in result.error

    def test_timeout_propagates(self, tmp_path):
        dist = _make_dist(tmp_path)

        with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
            result = deploy(dist, "myapp", "kodadocs", license_key=VALID_LICENSE_KEY, site_slug="myapp")

        assert result.success is False
        assert "timed out" in result.error

    def test_skips_badge_injection(self, tmp_path):
        """kodadocs provider must NOT inject the 'Powered by KodaDocs' badge."""
        dist = _make_dist(tmp_path, with_html=True)
        html_before = (dist / "index.html").read_text()
        mock_resp = _mock_200_response()

        with patch("httpx.post", return_value=mock_resp):
            result = deploy(dist, "myapp", "kodadocs", license_key=VALID_LICENSE_KEY, site_slug="myapp")

        html_after = (dist / "index.html").read_text()
        assert result.success is True
        assert "kodadocs-badge" not in html_after
        assert "Powered by KodaDocs" not in html_after

    def test_missing_dist_dir_returns_error(self, tmp_path):
        missing = tmp_path / "nonexistent"
        result = deploy(missing, "myapp", "kodadocs", license_key=VALID_LICENSE_KEY, site_slug="myapp")

        assert result.success is False
        assert "not found" in result.error

    def test_zip_cleaned_up_on_success(self, tmp_path):
        dist = _make_dist(tmp_path, with_html=True)
        zip_path = dist.parent / "myapp.zip"
        mock_resp = _mock_200_response()

        with patch("httpx.post", return_value=mock_resp):
            deploy(dist, "myapp", "kodadocs", license_key=VALID_LICENSE_KEY, site_slug="myapp")

        assert not zip_path.exists(), "ZIP must be cleaned up after successful deploy"

    def test_zip_cleaned_up_on_failure(self, tmp_path):
        dist = _make_dist(tmp_path)
        zip_path = dist.parent / "myapp.zip"
        mock_resp = _mock_error_response(500, "server error")

        with patch("httpx.post", return_value=mock_resp):
            deploy(dist, "myapp", "kodadocs", license_key=VALID_LICENSE_KEY, site_slug="myapp")

        assert not zip_path.exists(), "ZIP must be cleaned up after failed deploy"


# ── MCP tool tests for kodadocs provider ──────────────────────────────────


class TestMcpDeployToolKodadocs:
    def test_mcp_tool_passes_license_key_and_slug(self, tmp_path):
        from kodadocs.mcp.tools.deploy import deploy_site_tool

        site_dir = tmp_path / "docs"
        vitepress_dist = site_dir / ".vitepress" / "dist"
        vitepress_dist.mkdir(parents=True)

        mock_resp = _mock_200_response("https://mysite.kodadocs.com")

        with patch("httpx.post", return_value=mock_resp):
            raw = deploy_site_tool(
                str(site_dir),
                "mysite",
                provider="kodadocs",
                license_key=VALID_LICENSE_KEY,
                site_slug="mysite",
            )

        data = json.loads(raw)
        assert data["status"] == "ok"
        assert "mysite.kodadocs.com" in data["url"]
        assert data["provider"] == "kodadocs"

    def test_mcp_tool_no_provider_error_mentions_kodadocs(self, tmp_path):
        from kodadocs.mcp.tools.deploy import deploy_site_tool

        site_dir = tmp_path / "docs"
        site_dir.mkdir()

        raw = deploy_site_tool(str(site_dir), "mysite")
        data = json.loads(raw)

        assert data["status"] == "error"
        assert "kodadocs" in data["error"].lower()

    def test_mcp_tool_missing_license_key_returns_error(self, tmp_path):
        from kodadocs.mcp.tools.deploy import deploy_site_tool

        site_dir = tmp_path / "docs"
        vitepress_dist = site_dir / ".vitepress" / "dist"
        vitepress_dist.mkdir(parents=True)

        raw = deploy_site_tool(
            str(site_dir), "mysite",
            provider="kodadocs", license_key=None, site_slug="mysite",
        )
        data = json.loads(raw)

        assert data["status"] == "error"
        assert "Pro license key" in data["error"]
