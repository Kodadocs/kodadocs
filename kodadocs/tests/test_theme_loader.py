import json
import time
from http.client import HTTPResponse
from io import BytesIO
from unittest.mock import patch, MagicMock
import urllib.error

import pytest
from kodadocs.themes.loader import (
    load_theme,
    list_themes,
    ThemePreset,
    CACHE_TTL_SECONDS,
)


PROFESSIONAL_THEME_DATA = {
    "name": "professional",
    "display_name": "Professional",
    "description": "Clean corporate look with deep blue accents",
    "colors": {
        "brand": {"light": "#2563eb", "dark": "#60a5fa"},
        "brand_hover": {"light": "#1d4ed8", "dark": "#93bbfd"},
        "brand_soft": {
            "light": "rgba(37,99,235,0.14)",
            "dark": "rgba(96,165,250,0.16)",
        },
        "bg": {"light": "#ffffff", "dark": "#0f172a"},
        "bg_alt": {"light": "#f8fafc", "dark": "#1e293b"},
        "text": {"light": "#1e293b", "dark": "#e2e8f0"},
        "text_muted": {"light": "#64748b", "dark": "#94a3b8"},
    },
    "font": "Inter, system-ui, sans-serif",
    "code_theme": "github-dark",
}

CATALOG_DATA = [
    {"name": "default", "display_name": "Default", "description": "Default", "tier": "free"},
    {"name": "professional", "display_name": "Professional", "description": "Pro", "tier": "pro"},
]


def _mock_response(data: dict, status: int = 200) -> MagicMock:
    """Create a mock urllib response."""
    body = json.dumps(data).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Redirect CACHE_DIR to tmp_path for test isolation."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr("kodadocs.themes.loader.CACHE_DIR", cache_dir)
    return cache_dir


def test_load_default_always_local():
    """Default theme loads from local JSON, no API call, no key needed."""
    with patch("kodadocs.themes.loader.urllib.request.urlopen") as mock_urlopen:
        theme = load_theme("default")
        mock_urlopen.assert_not_called()

    assert theme.name == "default"
    assert theme.colors["brand"]["light"] == "#3e8fb0"
    assert theme.font is not None


def test_load_paid_requires_license_key():
    """Loading a paid theme without a license key raises ValueError."""
    with pytest.raises(ValueError, match="Pro theme"):
        load_theme("professional")


def test_load_paid_from_api():
    """Paid theme fetched from API with valid license key."""
    mock_resp = _mock_response({"theme": PROFESSIONAL_THEME_DATA})

    with patch("kodadocs.themes.loader.urllib.request.urlopen", return_value=mock_resp):
        theme = load_theme("professional", license_key="kd_pro_test123")

    assert isinstance(theme, ThemePreset)
    assert theme.name == "professional"
    assert theme.colors["brand"]["light"] == "#2563eb"


def test_load_paid_caches_to_disk(isolated_cache):
    """After fetching from API, theme data is written to cache."""
    mock_resp = _mock_response({"theme": PROFESSIONAL_THEME_DATA})

    with patch("kodadocs.themes.loader.urllib.request.urlopen", return_value=mock_resp):
        load_theme("professional", license_key="kd_pro_test123")

    cache_file = isolated_cache / "professional.json"
    assert cache_file.exists()
    cached = json.loads(cache_file.read_text())
    assert cached["name"] == "professional"


def test_load_paid_from_cache(isolated_cache):
    """When cache is fresh, no HTTP call is made."""
    cache_dir = isolated_cache
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "professional.json"
    cache_file.write_text(json.dumps(PROFESSIONAL_THEME_DATA))

    with patch("kodadocs.themes.loader.urllib.request.urlopen") as mock_urlopen:
        theme = load_theme("professional", license_key="kd_pro_test123")
        mock_urlopen.assert_not_called()

    assert theme.name == "professional"


def test_load_paid_api_down_uses_expired_cache(isolated_cache):
    """When API is down but expired cache exists, use cached version."""
    cache_dir = isolated_cache
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "professional.json"
    cache_file.write_text(json.dumps(PROFESSIONAL_THEME_DATA))

    # Make cache expired by setting mtime far in the past
    old_time = time.time() - CACHE_TTL_SECONDS - 3600
    import os
    os.utime(cache_file, (old_time, old_time))

    with patch(
        "kodadocs.themes.loader.urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        theme = load_theme("professional", license_key="kd_pro_test123")

    assert theme.name == "professional"
    assert theme.colors["brand"]["light"] == "#2563eb"


def test_load_paid_api_down_no_cache_falls_back(isolated_cache):
    """When API is down and no cache exists, fall back to default theme."""
    with patch(
        "kodadocs.themes.loader.urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        theme = load_theme("professional", license_key="kd_pro_test123")

    assert theme.name == "default"


def test_load_paid_401_raises():
    """Invalid license key (401) raises ValueError, no silent fallback."""
    error = urllib.error.HTTPError(
        url="https://api.kodadocs.com/themes/professional",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=BytesIO(b'{"error": "Invalid key"}'),
    )

    with patch(
        "kodadocs.themes.loader.urllib.request.urlopen",
        side_effect=error,
    ):
        with pytest.raises(ValueError, match="Invalid or inactive license key"):
            load_theme("professional", license_key="kd_pro_badkey")


def test_list_themes_from_api():
    """list_themes() fetches catalog from API."""
    mock_resp = _mock_response({"themes": CATALOG_DATA})

    with patch("kodadocs.themes.loader.urllib.request.urlopen", return_value=mock_resp):
        themes = list_themes()

    assert len(themes) == 2
    assert themes[0]["name"] == "default"
    assert themes[1]["tier"] == "pro"


def test_list_themes_api_down():
    """When API is unreachable, list_themes returns default only."""
    with patch(
        "kodadocs.themes.loader.urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        themes = list_themes()

    assert len(themes) == 1
    assert themes[0]["name"] == "default"
    assert themes[0]["tier"] == "free"


def test_theme_generates_css():
    """Default theme produces valid CSS with all expected properties."""
    theme = load_theme("default")
    css = theme.to_css()
    assert "--vp-c-brand-1" in css
    assert "--vp-c-brand-2" in css
    assert "--vp-c-brand-3" in css
    assert ":root" in css
    assert ".dark" in css


def test_theme_css_includes_font():
    """Theme CSS includes font-family property."""
    theme = load_theme("default")
    css = theme.to_css()
    assert "--vp-font-family-base" in css
