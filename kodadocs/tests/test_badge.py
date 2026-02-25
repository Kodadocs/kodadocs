from pathlib import Path

import pytest

from kodadocs.utils.badge import inject_badge, BADGE_HTML, BADGE_CSS


@pytest.fixture
def html_file(tmp_path):
    """Create a minimal HTML file in tmp_path."""
    html = tmp_path / "index.html"
    html.write_text(
        "<!DOCTYPE html><html><head><title>Test</title></head>"
        "<body><h1>Hello</h1></body></html>"
    )
    return html


class TestInjectBadge:
    def test_injects_css_before_head_close(self, tmp_path, html_file):
        inject_badge(tmp_path)
        content = html_file.read_text()
        assert "kodadocs-badge" in content
        # CSS appears before </head>
        css_pos = content.find(".kodadocs-badge")
        head_close_pos = content.find("</head>")
        assert css_pos < head_close_pos

    def test_injects_html_before_body_close(self, tmp_path, html_file):
        inject_badge(tmp_path)
        content = html_file.read_text()
        badge_pos = content.find("Powered by KodaDocs")
        body_close_pos = content.find("</body>")
        assert badge_pos < body_close_pos

    def test_returns_count_of_modified_files(self, tmp_path, html_file):
        # Add a second HTML file
        sub = tmp_path / "about"
        sub.mkdir()
        (sub / "index.html").write_text(
            "<html><head></head><body></body></html>"
        )
        count = inject_badge(tmp_path)
        assert count == 2

    def test_skips_non_html_files(self, tmp_path, html_file):
        (tmp_path / "style.css").write_text("body { color: red; }")
        count = inject_badge(tmp_path)
        assert count == 1  # only the .html file

    def test_handles_empty_directory(self, tmp_path):
        count = inject_badge(tmp_path)
        assert count == 0

    def test_does_not_double_inject(self, tmp_path, html_file):
        inject_badge(tmp_path)
        first_content = html_file.read_text()
        first_count = first_content.count("kodadocs-badge")

        inject_badge(tmp_path)
        second_content = html_file.read_text()
        # Second inject must be a no-op; badge count stays the same.
        assert second_content.count("kodadocs-badge") == first_count

    def test_badge_links_to_kodadocs(self, tmp_path, html_file):
        inject_badge(tmp_path)
        content = html_file.read_text()
        assert 'href="https://kodadocs.com"' in content
