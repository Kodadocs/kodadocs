"""Theme preset loader for KodaDocs.

Default theme loads from local JSON. Paid themes (Pro) are fetched from the
KodaDocs API with license key auth and cached locally for 24 hours.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PRESETS_DIR = Path(__file__).parent / "presets"
CACHE_DIR = Path.home() / ".cache" / "kodadocs" / "themes"
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours

KODADOCS_API_URL = os.environ.get("KODADOCS_API_URL", "https://api.kodadocs.com")


@dataclass
class ThemePreset:
    name: str
    display_name: str
    description: str
    colors: dict[str, dict[str, str]]
    font: str
    code_theme: str

    def to_css(self) -> str:
        """Generate VitePress CSS custom properties from this theme."""
        brand_light = self.colors["brand"]["light"]
        brand_dark = self.colors["brand"]["dark"]
        brand_hover_light = self.colors.get("brand_hover", {}).get("light", brand_light)
        brand_hover_dark = self.colors.get("brand_hover", {}).get("dark", brand_dark)
        brand_soft_light = self.colors.get("brand_soft", {}).get("light", f"{brand_light}22")
        brand_soft_dark = self.colors.get("brand_soft", {}).get("dark", f"{brand_dark}22")
        bg_light = self.colors.get("bg", {}).get("light", "#ffffff")
        bg_dark = self.colors.get("bg", {}).get("dark", "#1b1b1f")
        bg_alt_light = self.colors.get("bg_alt", {}).get("light", "#f6f6f7")
        bg_alt_dark = self.colors.get("bg_alt", {}).get("dark", "#161618")
        text_light = self.colors.get("text", {}).get("light", "#213547")
        text_dark = self.colors.get("text", {}).get("dark", "rgba(255,255,245,.86)")
        text_muted_light = self.colors.get("text_muted", {}).get("light", "#596673")
        text_muted_dark = self.colors.get("text_muted", {}).get("dark", "rgba(235,235,245,.6)")

        return f""":root {{
  --vp-c-brand-1: {brand_light};
  --vp-c-brand-2: {brand_hover_light};
  --vp-c-brand-3: {brand_light};
  --vp-c-brand-soft: {brand_soft_light};
  --vp-c-bg: {bg_light};
  --vp-c-bg-alt: {bg_alt_light};
  --vp-c-text-1: {text_light};
  --vp-c-text-2: {text_muted_light};
  --vp-font-family-base: {self.font};
}}

.dark {{
  --vp-c-brand-1: {brand_dark};
  --vp-c-brand-2: {brand_hover_dark};
  --vp-c-brand-3: {brand_dark};
  --vp-c-brand-soft: {brand_soft_dark};
  --vp-c-bg: {bg_dark};
  --vp-c-bg-alt: {bg_alt_dark};
  --vp-c-text-1: {text_dark};
  --vp-c-text-2: {text_muted_dark};
}}
"""


def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.json"


def _read_cache(name: str, allow_expired: bool = False) -> Optional[dict]:
    """Read theme from disk cache. Returns None if missing or expired."""
    path = _cache_path(name)
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > CACHE_TTL_SECONDS and not allow_expired:
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(name: str, data: dict) -> None:
    """Write theme data to disk cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(name).write_text(json.dumps(data))


def _fetch_theme(name: str, license_key: str) -> dict:
    """Fetch a theme preset from the API. Raises on failure."""
    url = f"{KODADOCS_API_URL}/themes/{name}"
    req = urllib.request.Request(
        url,
        headers={
            "X-License-Key": license_key,
            "User-Agent": "kodadocs-cli/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return data["theme"]


def load_theme(name: str, license_key: Optional[str] = None) -> ThemePreset:
    """Load a theme preset by name.

    - "default" always loads from the local bundled preset (no API, no key).
    - All other themes require a license_key and are fetched from the API,
      with a 24-hour disk cache at ~/.cache/kodadocs/themes/.

    Graceful degradation for paid themes:
    - No license key → ValueError (explicit error)
    - 401 from API → ValueError (invalid key, no silent fallback)
    - API down + valid cache (even expired) → use cached version
    - API down + no cache → fall back to default theme with warning
    """
    if name == "default":
        preset_file = PRESETS_DIR / "default.json"
        data = json.loads(preset_file.read_text())
        return ThemePreset(**data)

    # Paid theme — require license key
    if not license_key:
        from ..utils.messaging import show_theme_gate_message
        show_theme_gate_message(name)
        # Fall back to default theme
        preset_file = PRESETS_DIR / "default.json"
        data = json.loads(preset_file.read_text())
        return ThemePreset(**data)

    # Try fresh cache first
    cached = _read_cache(name)
    if cached:
        return ThemePreset(**cached)

    # Fetch from API
    try:
        theme_data = _fetch_theme(name, license_key)
        _write_cache(name, theme_data)
        return ThemePreset(**theme_data)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ValueError(
                f"Invalid or inactive license key. Cannot load Pro theme '{name}'."
            ) from None
        if e.code == 404:
            raise ValueError(f"Theme '{name}' not found.") from None
        # Other HTTP errors — try expired cache
        expired = _read_cache(name, allow_expired=True)
        if expired:
            return ThemePreset(**expired)
        # Fall back to default
        return load_theme("default")
    except urllib.error.URLError:
        # Network error — try expired cache
        expired = _read_cache(name, allow_expired=True)
        if expired:
            return ThemePreset(**expired)
        # Fall back to default
        return load_theme("default")


def list_themes() -> list[dict]:
    """List available theme presets from the API catalog.

    Returns a list of dicts with name, display_name, description, tier.
    Falls back to default-only list if the API is unreachable.
    """
    url = f"{KODADOCS_API_URL}/themes"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "kodadocs-cli/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data["themes"]
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return [
            {
                "name": "default",
                "display_name": "Default",
                "description": "The standard KodaDocs look with teal accents",
                "tier": "free",
            }
        ]
