"""Theme preset loader for KodaDocs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PRESETS_DIR = Path(__file__).parent / "presets"


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


def load_theme(name: str) -> ThemePreset:
    """Load a theme preset by name."""
    preset_file = PRESETS_DIR / f"{name}.json"
    if not preset_file.exists():
        available = [p.stem for p in PRESETS_DIR.glob("*.json")]
        raise ValueError(
            f"Unknown theme '{name}'. Available: {', '.join(sorted(available))}"
        )

    data = json.loads(preset_file.read_text())
    return ThemePreset(**data)


def list_themes() -> list[ThemePreset]:
    """List all available theme presets."""
    themes = []
    for preset_file in sorted(PRESETS_DIR.glob("*.json")):
        data = json.loads(preset_file.read_text())
        themes.append(ThemePreset(**data))
    return themes
