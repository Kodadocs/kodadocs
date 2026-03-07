"""Unit tests for license/Pro Kit detection and badge suppression."""

from pathlib import Path

import pytest

from kodadocs.utils.license import is_pro, is_valid_license_key, has_local_pro_kit, LICENSE_KEY_PATTERN
from kodadocs.models import SessionConfig


# -- is_valid_license_key() (deploy-only validation) -------------------------


class TestIsValidLicenseKey:
    def test_valid_pro_key_returns_true(self):
        assert is_valid_license_key("kd_pro_" + "a" * 20) is True

    def test_none_returns_false(self):
        assert is_valid_license_key(None) is False

    def test_empty_string_returns_false(self):
        assert is_valid_license_key("") is False

    def test_wrong_prefix_returns_false(self):
        assert is_valid_license_key("kd_free_abc") is False

    def test_short_key_still_valid_prefix(self):
        """Prefix check only — short keys pass."""
        assert is_valid_license_key("kd_pro_short") is True

    def test_random_string_returns_false(self):
        assert is_valid_license_key("totally_random") is False

    def test_key_with_hyphens_returns_true(self):
        assert is_valid_license_key("kd_pro_" + "a-b_c" * 5) is True


# -- is_pro() (Pro Kit detection) --------------------------------------------


class TestIsPro:
    def test_returns_false_without_skill_dirs(self, monkeypatch):
        """Without skill directories, is_pro() returns False."""
        monkeypatch.setattr(
            "kodadocs.utils.license.has_local_pro_kit", lambda: False
        )
        assert is_pro() is False

    def test_returns_true_with_skill_dirs(self, monkeypatch):
        """With Pro Kit skill directories, is_pro() returns True."""
        monkeypatch.setattr(
            "kodadocs.utils.license.has_local_pro_kit", lambda: True
        )
        assert is_pro() is True


# -- LICENSE_KEY_PATTERN ------------------------------------------------------


class TestLicenseKeyPattern:
    def test_license_key_pattern_is_string(self):
        import re

        assert isinstance(LICENSE_KEY_PATTERN, str)
        assert len(LICENSE_KEY_PATTERN) > 0
        compiled = re.compile(LICENSE_KEY_PATTERN)
        assert compiled.match("kd_pro_" + "a" * 20) is not None
        assert compiled.match("bad_key") is None


# -- SessionConfig license_key ------------------------------------------------


class TestSessionConfigLicenseKey:
    def test_session_config_accepts_valid_key(self, tmp_path):
        cfg = SessionConfig(project_path=tmp_path, license_key="kd_pro_" + "a" * 20)
        assert cfg.license_key == "kd_pro_" + "a" * 20

    def test_session_config_allows_none_key(self, tmp_path):
        cfg = SessionConfig(project_path=tmp_path)
        assert cfg.license_key is None

    def test_session_config_accepts_any_string_key(self, tmp_path):
        """License key field no longer has pattern validation (deploy-only)."""
        cfg = SessionConfig(project_path=tmp_path, license_key="any_string")
        assert cfg.license_key == "any_string"


# -- Badge suppression (via deploy()) ----------------------------------------


class TestBadgeSuppression:
    def _make_dist(self, tmp_path: Path) -> Path:
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text(
            "<html><head></head><body></body></html>",
            encoding="utf-8",
        )
        return dist

    def test_deploy_injects_badge_without_pro_kit(self, tmp_path, monkeypatch):
        """Free tier (no Pro Kit) gets the badge injected."""
        from unittest.mock import MagicMock, patch
        from kodadocs.utils.deploy import deploy

        dist = self._make_dist(tmp_path)
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

        content = (dist / "index.html").read_text()
        assert "kodadocs-badge" in content

    def test_deploy_skips_badge_with_pro_kit(self, tmp_path, monkeypatch):
        """Pro Kit installed — badge NOT injected."""
        from unittest.mock import MagicMock, patch
        from kodadocs.utils.deploy import deploy

        dist = self._make_dist(tmp_path)
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://proj.pages.dev\n"
        mock_result.stderr = ""

        with (
            patch("kodadocs.utils.deploy.is_pro", return_value=True),
            patch(
                "kodadocs.utils.deploy.shutil.which", return_value="/usr/bin/wrangler"
            ),
            patch("kodadocs.utils.deploy.subprocess.run", return_value=mock_result),
        ):
            deploy(dist, "proj", "cloudflare")

        content = (dist / "index.html").read_text()
        assert "kodadocs-badge" not in content
