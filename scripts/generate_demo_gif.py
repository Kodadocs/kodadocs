#!/usr/bin/env python3
"""Generate a demo GIF showing KodaDocs CLI in action."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

# ── Dimensions ──────────────────────────────────────────────────────────
WIDTH, HEIGHT = 840, 520
PADDING_X = 20
TITLE_BAR_H = 38
CONTENT_Y0 = TITLE_BAR_H + 12
LINE_HEIGHT = 24
MAX_VISIBLE_LINES = 17
CORNER_R = 12

# ── Catppuccin Mocha palette ───────────────────────────────────────────
C = {
    "bg":      (30, 30, 46),
    "title":   (45, 45, 65),
    "white":   (205, 214, 244),
    "green":   (166, 227, 161),
    "cyan":    (137, 220, 235),
    "blue":    (137, 180, 250),
    "yellow":  (249, 226, 175),
    "dim":     (108, 112, 134),
    "red_dot": (243, 139, 168),
    "ylw_dot": (249, 226, 175),
    "grn_dot": (166, 227, 161),
    "bar_bg":  (49, 50, 68),
    "bar_fg":  (137, 180, 250),
}

# ── Fonts ───────────────────────────────────────────────────────────────
MONO = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 18)
MONO_BOLD = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 18, index=1)
TITLE_FONT = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 13)

FPS = 20  # frames per second


# ── Helpers ─────────────────────────────────────────────────────────────
def rounded_rect(draw: ImageDraw.Draw, xy, fill, r):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=r, fill=fill)


def draw_chrome(img: Image.Image):
    """Draw the terminal window chrome (title bar + traffic lights)."""
    draw = ImageDraw.Draw(img)
    # Background
    rounded_rect(draw, (0, 0, WIDTH - 1, HEIGHT - 1), C["bg"], CORNER_R)
    # Title bar
    rounded_rect(draw, (0, 0, WIDTH - 1, TITLE_BAR_H), C["title"], CORNER_R)
    # Fill the bottom corners of title bar so it's flat at the join
    draw.rectangle((0, TITLE_BAR_H - CORNER_R, WIDTH - 1, TITLE_BAR_H), fill=C["title"])
    # Traffic lights
    for i, color in enumerate([C["red_dot"], C["ylw_dot"], C["grn_dot"]]):
        cx = 20 + i * 22
        cy = TITLE_BAR_H // 2
        draw.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=color)
    # Title text
    title = "kodadocs generate ."
    bbox = TITLE_FONT.getbbox(title)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, (TITLE_BAR_H - 14) // 2), title, fill=C["dim"], font=TITLE_FONT)
    return img


def make_base():
    img = Image.new("RGB", (WIDTH, HEIGHT), C["bg"])
    draw_chrome(img)
    return img


# ── Inline color parser ────────────────────────────────────────────────
# Format: "{color:text}" e.g. "{green:done}" or plain text
def parse_segments(text: str):
    """Parse text with {color:content} markup into (text, color_key) segments."""
    segments = []
    i = 0
    while i < len(text):
        if text[i] == '{':
            end = text.find('}', i)
            if end == -1:
                segments.append((text[i:], "white"))
                break
            inner = text[i + 1:end]
            if ':' in inner:
                color_key, content = inner.split(':', 1)
                segments.append((content, color_key.strip()))
            else:
                segments.append((inner, "white"))
            i = end + 1
        else:
            next_brace = text.find('{', i)
            if next_brace == -1:
                segments.append((text[i:], "white"))
                break
            segments.append((text[i:next_brace], "white"))
            i = next_brace
    return segments


def draw_text_line(draw: ImageDraw.Draw, x: int, y: int, text: str, bold=False):
    """Draw a single line with inline color markup."""
    font = MONO_BOLD if bold else MONO
    segments = parse_segments(text)
    cx = x
    for content, color_key in segments:
        color = C.get(color_key, C["white"])
        draw.text((cx, y), content, fill=color, font=font)
        bbox = font.getbbox(content)
        cx += bbox[2] - bbox[0]


def draw_progress_bar(draw: ImageDraw.Draw, x: int, y: int, width: int, progress: float):
    """Draw a graphical progress bar."""
    bar_h = 14
    by = y + (LINE_HEIGHT - bar_h) // 2
    # Background
    draw.rounded_rectangle((x, by, x + width, by + bar_h), radius=4, fill=C["bar_bg"])
    # Filled portion
    fill_w = max(4, int(width * progress))
    if fill_w > 0:
        draw.rounded_rectangle((x, by, x + fill_w, by + bar_h), radius=4, fill=C["bar_fg"])


# ── Frame builder ───────────────────────────────────────────────────────
class TerminalAnimator:
    def __init__(self):
        self.lines: list[str] = []  # stored with markup
        self.bold_lines: set[int] = set()
        self.frames: list[tuple[Image.Image, int]] = []  # (frame, duration_ms)

    def _visible_lines(self):
        """Return the slice of lines that are visible."""
        if len(self.lines) <= MAX_VISIBLE_LINES:
            return self.lines, 0
        start = len(self.lines) - MAX_VISIBLE_LINES
        return self.lines[start:], start

    def _render(self, extra_draw_fn=None):
        """Render current state to a frame."""
        img = make_base()
        draw = ImageDraw.Draw(img)
        visible, offset = self._visible_lines()
        for i, line in enumerate(visible):
            y = CONTENT_Y0 + i * LINE_HEIGHT
            bold = (i + offset) in self.bold_lines
            draw_text_line(draw, PADDING_X, y, line, bold=bold)
        if extra_draw_fn:
            extra_draw_fn(draw)
        return img

    def add_frame(self, duration_ms: int, extra_draw_fn=None):
        self.frames.append((self._render(extra_draw_fn), duration_ms))

    def type_line(self, text: str, char_delay_ms=60):
        """Type out a line character by character with cursor."""
        # Strip markup for typing — we type the raw visible chars
        plain = text.replace('{', '').replace('}', '')
        # Remove color markup for plain display
        import re
        plain = re.sub(r'(\w+):', '', plain, count=plain.count('{'))
        # Actually, let's just type the display text directly (no markup during typing)
        display = ""
        for segment_text, _ in parse_segments(text):
            display += segment_text

        typed = ""
        for ch in display:
            typed += ch
            # Show typed text + cursor
            self.lines.append(typed + "\u2588")  # block cursor
            self.add_frame(char_delay_ms)
            self.lines.pop()
        # Final: show full marked-up line without cursor
        self.lines.append(text)
        self.add_frame(50)

    def add_line(self, text: str, duration_ms: int = 0, bold=False):
        """Add a line instantly."""
        if bold:
            self.bold_lines.add(len(self.lines))
        self.lines.append(text)
        if duration_ms > 0:
            self.add_frame(duration_ms)

    def hold(self, duration_ms: int):
        self.add_frame(duration_ms)

    def progress_sequence(self, label: str, total: int, steps: int, total_ms: int):
        """Animate a progress bar from 0 to total."""
        bar_x = PADDING_X
        bar_w = 340
        step_dur = total_ms // steps

        for s in range(steps + 1):
            current = int(total * s / steps)
            progress = s / steps
            line_text = f"   {label} "
            count_text = f"{current}/{total}"

            def make_draw_fn(lt, ct, prog, lcount):
                def fn(draw: ImageDraw.Draw):
                    vis, off = self._visible_lines()
                    line_idx = lcount - 1 - off
                    if line_idx < 0:
                        line_idx = len(vis) - 1
                    y = CONTENT_Y0 + line_idx * LINE_HEIGHT
                    # Clear the line area
                    draw.rectangle((PADDING_X, y, WIDTH - PADDING_X, y + LINE_HEIGHT), fill=C["bg"])
                    # Draw label
                    draw.text((PADDING_X, y), lt, fill=C["white"], font=MONO)
                    label_w = MONO.getbbox(lt)[2]
                    # Draw bar
                    bx = PADDING_X + label_w + 5
                    draw_progress_bar(draw, bx, y, bar_w, prog)
                    # Draw count after bar
                    cx = bx + bar_w + 10
                    draw.text((cx, y), ct, fill=C["yellow"], font=MONO)
                return fn

            if s == 0:
                self.lines.append("")  # placeholder line
            self.frames.append((
                self._render(make_draw_fn(line_text, count_text, progress, len(self.lines))),
                step_dur
            ))

        # Replace placeholder with final text
        self.lines[-1] = f"   {label} {'{yellow:' + str(total) + '/' + str(total) + '}'} {'{green:done}'}"


def build_animation():
    anim = TerminalAnimator()

    # ── 1. Type command (1.3s) ──
    anim.type_line("{dim:$} kodadocs generate {cyan:.}", char_delay_ms=55)
    anim.hold(200)

    # ── 2. Banner (1.5s hold) ──
    anim.add_line("")
    anim.add_line("{blue:KodaDocs} {dim:v2.0.0}")
    anim.add_line("")
    anim.add_line("  Project     {cyan:acme_webapp}")
    anim.add_line("  Framework   {cyan:Next.js 14}")
    anim.add_line("  App URL     {cyan:http://localhost:3000}")
    anim.add_line("  AI Model    {cyan:Claude Sonnet 4}")
    anim.add_line("  Output      {cyan:./kodadocs_output}")
    anim.add_line("")
    anim.hold(1500)

    # ── 3. Discovery (1.4s) ──
    anim.add_line("{blue:Discovering routes...}", 400, bold=True)
    anim.add_line("   Found {yellow:12} routes", 300)
    anim.add_line("   Services: {cyan:Prisma} {cyan:NextAuth} {cyan:Stripe}", 400)
    anim.hold(300)

    # ── 4. Analysis (1.3s) ──
    anim.add_line("{blue:Analyzing codebase...}", 400, bold=True)
    anim.add_line("   {yellow:127} functions, {yellow:8} Prisma models", 400)
    anim.hold(500)

    # ── 5. Capture (1.4s) ──
    anim.add_line("{blue:Capturing screenshots...}", 200, bold=True)
    anim.progress_sequence("Capturing", 12, 12, 1200)

    # ── 6. Annotation (1.2s) ──
    anim.add_line("{blue:Annotating screenshots...}", 200, bold=True)
    anim.progress_sequence("Annotating", 12, 10, 1000)

    # ── 7. Enrichment (2.3s) ──
    anim.add_line("{blue:Writing articles...}", 200, bold=True)
    articles = [
        "Getting Started",
        "Dashboard Overview",
        "User Management",
        "Billing & Payments",
        "Settings Page",
        "API Reference",
    ]
    for art in articles:
        anim.add_line(f"   {art}... {{green:done}}", 300)
    anim.hold(250)

    # ── 8. Assembly (0.9s) ──
    anim.add_line("{blue:Assembling site...}", 400, bold=True)
    anim.add_line("   Generated {yellow:6} articles with screenshots", 500)

    # ── 9. Final message (3.5s) ──
    anim.add_line("")
    anim.add_line("{green:Docs generated!} Open ./kodadocs_output to view.", 0, bold=True)
    anim.hold(3500)

    return anim.frames


# ── GIF export ──────────────────────────────────────────────────────────
def save_gif(frames: list[tuple[Image.Image, int]], path: str):
    """Save frames as an optimized animated GIF with delta encoding."""
    if not frames:
        return

    # Deduplicate consecutive identical frames by merging durations
    deduped: list[tuple[Image.Image, int]] = [frames[0]]
    for img, dur in frames[1:]:
        prev_img, prev_dur = deduped[-1]
        if img.tobytes() == prev_img.tobytes():
            deduped[-1] = (prev_img, prev_dur + dur)
        else:
            deduped.append((img, dur))
    frames = deduped

    # Build shared palette from a composite of key frames
    palette_img = frames[0][0].quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=0)
    shared_palette = palette_img.getpalette()

    quantized = []
    for img, dur in frames:
        q = img.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=0)
        quantized.append((q, dur))

    imgs = [q for q, _ in quantized]
    durations = [d for _, d in quantized]

    imgs[0].save(
        path,
        save_all=True,
        append_images=imgs[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )

    # Try gifsicle optimization if available
    import subprocess, shutil
    if shutil.which("gifsicle"):
        tmp = path + ".opt"
        subprocess.run(
            ["gifsicle", "-O3", "--colors", "64", "--lossy=30", "-o", tmp, path],
            capture_output=True,
        )
        import os
        if os.path.exists(tmp) and os.path.getsize(tmp) < os.path.getsize(path):
            os.replace(tmp, path)
        elif os.path.exists(tmp):
            os.remove(tmp)

    import os
    size_kb = os.path.getsize(path) / 1024
    total_ms = sum(durations)
    print(f"Saved {path}")
    print(f"  Frames: {len(imgs)}")
    print(f"  Duration: {total_ms / 1000:.1f}s")
    print(f"  Size: {size_kb:.0f} KB")


def main():
    print("Generating KodaDocs demo GIF...")
    frames = build_animation()
    out_path = "/Users/claudioagent/Documents/Kodadocs/demo.gif"
    save_gif(frames, out_path)
    print("Done!")


if __name__ == "__main__":
    main()
