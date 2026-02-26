"""Unit tests for license key validation and badge suppression (Pro tier)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from kodadocs.utils.license import is_pro_key, LICENSE_KEY_PATTERN
from kodadocs.models import SessionConfig


# ── is_pro_key() ────────────────────────────────────────────────────────


class TestIsProKey:
    def test_valid_pro_key_returns_true(self):
        """A key with the kd_pro_ prefix and 20+ chars is accepted."""
        assert is_pro_key("kd_pro_" + "a" * 20) is True

    def test_none_returns_false(self):
        """None is treated as no key — free tier."""
        assert is_pro_key(None) is False

    def test_empty_string_returns_false(self):
        """Empty string is treated as no key — free tier."""
        assert is_pro_key("") is False

    def test_wrong_prefix_returns_false(self):
        """Keys without the kd_pro_ prefix are rejected."""
        assert is_pro_key("kd_free_abc") is False

    def test_short_key_still_valid_prefix(self):
        """Runtime check is prefix-only; short keys pass is_pro_key.

        Pydantic enforces the 20-char minimum at the model level.
        """
        assert is_pro_key("kd_pro_short") is True

    def test_random_string_returns_false(self):
        assert is_pro_key("totally_random") is False

    def test_key_with_hyphens_returns_true(self):
        """Hyphens and underscores in the suffix are valid."""
        assert is_pro_key("kd_pro_" + "a-b_c" * 5) is True

    def test_license_key_pattern_is_string(self):
        """LICENSE_KEY_PATTERN must be a non-empty string (used in Pydantic Field)."""
        import re

        assert isinstance(LICENSE_KEY_PATTERN, str)
        assert len(LICENSE_KEY_PATTERN) > 0
        # Must compile without error
        compiled = re.compile(LICENSE_KEY_PATTERN)
        assert compiled.match("kd_pro_" + "a" * 20) is not None
        assert compiled.match("bad_key") is None


# ── SessionConfig Pydantic validation ───────────────────────────────────


class TestSessionConfigLicenseKey:
    def test_session_config_accepts_valid_key(self, tmp_path):
        """A well-formed Pro key passes Pydantic validation."""
        cfg = SessionConfig(project_path=tmp_path, license_key="kd_pro_" + "a" * 20)
        assert cfg.license_key == "kd_pro_" + "a" * 20

    def test_session_config_rejects_malformed_key(self, tmp_path):
        """A malformed key raises ValidationError."""
        with pytest.raises(ValidationError):
            SessionConfig(project_path=tmp_path, license_key="bad")

    def test_session_config_allows_none_key(self, tmp_path):
        """No license key (free tier) is always valid."""
        cfg = SessionConfig(project_path=tmp_path)
        assert cfg.license_key is None

    def test_session_config_rejects_short_pro_key(self, tmp_path):
        """A key matching the prefix but shorter than 20 suffix chars is rejected."""
        with pytest.raises(ValidationError):
            SessionConfig(project_path=tmp_path, license_key="kd_pro_short")

    def test_session_config_accepts_key_with_hyphens(self, tmp_path):
        """Hyphens and underscores in the suffix are allowed by the pattern."""
        key = "kd_pro_" + "ab-cd_ef" * 3  # 24 suffix chars
        cfg = SessionConfig(project_path=tmp_path, license_key=key)
        assert cfg.license_key == key


# ── Badge suppression (via deploy()) ────────────────────────────────────


class TestBadgeSuppression:
    """Integration tests verifying badge injection is gated on Pro license key.

    These tests exercise the deploy() function with a mocked subprocess so
    we stay focused on badge behaviour rather than actual deployments.
    """

    def _make_dist(self, tmp_path: Path) -> Path:
        """Create a minimal dist directory with one HTML file."""
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text(
            "<html><head></head><body></body></html>",
            encoding="utf-8",
        )
        return dist

    def test_deploy_injects_badge_without_key(self, tmp_path, monkeypatch):
        """Free tier (no license key) gets the badge injected."""
        from unittest.mock import MagicMock, patch
        from kodadocs.utils.deploy import deploy

        dist = self._make_dist(tmp_path)
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://proj.pages.dev\n"
        mock_result.stderr = ""

        with (
            patch(
                "kodadocs.utils.deploy.shutil.which", return_value="/usr/bin/wrangler"
            ),
            patch("kodadocs.utils.deploy.subprocess.run", return_value=mock_result),
        ):
            deploy(dist, "proj", "cloudflare", license_key=None)

        content = (dist / "index.html").read_text()
        assert "kodadocs-badge" in content

    def test_deploy_skips_badge_with_pro_key(self, tmp_path, monkeypatch):
        """Pro tier (valid license key) does NOT get badge injected."""
        from unittest.mock import MagicMock, patch
        from kodadocs.utils.deploy import deploy

        dist = self._make_dist(tmp_path)
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://proj.pages.dev\n"
        mock_result.stderr = ""

        with (
            patch(
                "kodadocs.utils.deploy.shutil.which", return_value="/usr/bin/wrangler"
            ),
            patch("kodadocs.utils.deploy.subprocess.run", return_value=mock_result),
        ):
            deploy(dist, "proj", "cloudflare", license_key="kd_pro_" + "a" * 20)

        content = (dist / "index.html").read_text()
        assert "kodadocs-badge" not in content

    def test_deploy_injects_badge_with_invalid_key(self, tmp_path, monkeypatch):
        """An invalid (non-Pro) license key is treated as free tier — badge injected."""
        from unittest.mock import MagicMock, patch
        from kodadocs.utils.deploy import deploy

        dist = self._make_dist(tmp_path)
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://proj.pages.dev\n"
        mock_result.stderr = ""

        with (
            patch(
                "kodadocs.utils.deploy.shutil.which", return_value="/usr/bin/wrangler"
            ),
            patch("kodadocs.utils.deploy.subprocess.run", return_value=mock_result),
        ):
            deploy(dist, "proj", "cloudflare", license_key="not_a_real_key")

        content = (dist / "index.html").read_text()
        assert "kodadocs-badge" in content
