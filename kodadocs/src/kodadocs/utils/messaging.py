"""Upgrade messaging for free tier users."""

from rich.console import Console
from rich.panel import Panel

console = Console()

PRO_KIT_URL = "https://kodadocs.com/pro"


def show_page_limit_message(route_count: int, limit: int = 15) -> None:
    """Show upgrade message when free user hits page limit."""
    console.print(
        Panel(
            f"[yellow]Free tier is limited to {limit} pages per run.[/yellow]\n"
            f"You have {route_count} routes — generating docs for the first {limit}.\n\n"
            f"[bold]Install the Pro Kit for unlimited pages:[/bold]\n"
            f"[link={PRO_KIT_URL}]{PRO_KIT_URL}[/link]",
            title="[bold yellow]Page Limit Reached[/bold yellow]",
            border_style="yellow",
        )
    )


def show_auth_gate_message() -> None:
    """Show upgrade message when free user tries to use auth."""
    console.print(
        Panel(
            "[yellow]Auth-gated app support requires the Pro Kit.[/yellow]\n"
            "Auth config will be skipped. Only public routes will be captured.\n\n"
            f"[bold]Install the Pro Kit:[/bold]\n"
            f"[link={PRO_KIT_URL}]{PRO_KIT_URL}[/link]",
            title="[bold yellow]Pro Kit Required[/bold yellow]",
            border_style="yellow",
        )
    )


def show_branding_gate_message() -> None:
    """Show upgrade message when free user tries custom branding."""
    console.print(
        Panel(
            "[yellow]Custom brand colors and logos require the Pro Kit.[/yellow]\n"
            "Using default KodaDocs theme.\n\n"
            f"[bold]Install the Pro Kit:[/bold]\n"
            f"[link={PRO_KIT_URL}]{PRO_KIT_URL}[/link]",
            title="[bold yellow]Pro Kit Required[/bold yellow]",
            border_style="yellow",
        )
    )


def show_theme_gate_message(theme_name: str) -> None:
    """Show upgrade message when free user tries premium theme."""
    console.print(
        Panel(
            f"[yellow]Theme '{theme_name}' requires the Pro Kit.[/yellow]\n"
            "Using default theme instead.\n\n"
            f"[bold]Install the Pro Kit:[/bold]\n"
            f"[link={PRO_KIT_URL}]{PRO_KIT_URL}[/link]",
            title="[bold yellow]Pro Kit Required[/bold yellow]",
            border_style="yellow",
        )
    )


# --- Plain-text variants for MCP JSON responses ---


def page_limit_warning(route_count: int, limit: int = 15) -> str:
    return (
        f"FREE TIER: Limited to {limit} pages per run. "
        f"You have {route_count} routes — only the first {limit} will be captured. "
        f"Install the Pro Kit for unlimited pages: {PRO_KIT_URL}"
    )


def auth_gate_warning() -> str:
    return (
        "FREE TIER: Auth-gated app support requires the Pro Kit. "
        f"Auth config was ignored — only public routes will be captured. "
        f"Install the Pro Kit: {PRO_KIT_URL}"
    )


def branding_gate_warning() -> str:
    return (
        "FREE TIER: Custom brand colors and logos require the Pro Kit. "
        f"Using default KodaDocs branding. "
        f"Install the Pro Kit: {PRO_KIT_URL}"
    )


def targeted_capture_gate_warning() -> str:
    return (
        "PRO REQUIRED: Targeted element screenshots require the Pro Kit. "
        f"Install the Pro Kit: {PRO_KIT_URL}"
    )


def gif_recording_gate_warning() -> str:
    return (
        "PRO REQUIRED: GIF workflow recordings require the Pro Kit. "
        f"Install the Pro Kit: {PRO_KIT_URL}"
    )
