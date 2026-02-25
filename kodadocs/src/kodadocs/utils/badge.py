"""Inject 'Powered by KodaDocs' badge into built HTML files."""

from pathlib import Path


BADGE_CSS = """\
<style>
.kodadocs-badge {
  position: fixed;
  bottom: 12px;
  right: 12px;
  background: #1a1a2e;
  color: #ccc;
  font-size: 12px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  padding: 6px 12px;
  border-radius: 6px;
  text-decoration: none;
  opacity: 0.85;
  z-index: 9999;
  transition: opacity 0.2s, color 0.2s;
}
.kodadocs-badge:hover {
  opacity: 1;
  color: #fff;
}
</style>"""

BADGE_HTML = '<a class="kodadocs-badge" href="https://kodadocs.com">Powered by KodaDocs</a>'


def inject_badge(dist_dir: Path) -> int:
    """Inject the KodaDocs badge into all HTML files under *dist_dir*.

    Inserts CSS before ``</head>`` and the badge link before ``</body>``.
    Skips files that already contain the badge.
    Returns the number of files modified.
    """
    count = 0
    for html_file in dist_dir.rglob("*.html"):
        text = html_file.read_text(encoding="utf-8")

        # Skip files that already have the badge injected.
        if "kodadocs-badge" in text:
            continue

        modified = False

        if "</head>" in text:
            text = text.replace("</head>", f"{BADGE_CSS}\n</head>", 1)
            modified = True

        if "</body>" in text:
            text = text.replace("</body>", f"{BADGE_HTML}\n</body>", 1)
            modified = True

        if modified:
            html_file.write_text(text, encoding="utf-8")
            count += 1

    return count
