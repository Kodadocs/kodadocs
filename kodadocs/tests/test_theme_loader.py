import pytest
from kodadocs.themes.loader import load_theme, list_themes, ThemePreset


def test_load_default_theme():
    theme = load_theme("default")
    assert theme.name == "default"
    assert theme.colors["brand"]["light"] == "#3e8fb0"
    assert theme.font is not None


def test_load_professional_theme():
    theme = load_theme("professional")
    assert theme.name == "professional"
    assert theme.colors["brand"]["light"] != "#3e8fb0"


def test_load_unknown_theme_raises():
    with pytest.raises(ValueError, match="Unknown theme"):
        load_theme("nonexistent-theme")


def test_list_themes_returns_all():
    themes = list_themes()
    assert len(themes) >= 6
    names = [t.name for t in themes]
    assert "default" in names
    assert "professional" in names
    assert "minimal" in names
    assert "playful" in names
    assert "dark-modern" in names
    assert "docs-classic" in names


def test_theme_generates_css():
    theme = load_theme("default")
    css = theme.to_css()
    assert "--vp-c-brand-1" in css
    assert "--vp-c-brand-2" in css
    assert "--vp-c-brand-3" in css
    assert ":root" in css
    assert ".dark" in css


def test_theme_css_has_light_and_dark():
    theme = load_theme("professional")
    css = theme.to_css()
    assert ":root" in css
    assert ".dark" in css
    assert theme.colors["brand"]["light"] in css
    assert theme.colors["brand"]["dark"] in css


def test_theme_css_includes_font():
    theme = load_theme("professional")
    css = theme.to_css()
    assert "--vp-font-family-base" in css
