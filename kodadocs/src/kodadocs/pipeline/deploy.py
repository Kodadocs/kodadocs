"""Optional pipeline step for deploying the generated site."""

from kodadocs.models import RunManifest
from kodadocs.utils.deploy import resolve_provider, deploy
from pathlib import Path
from rich.console import Console

console = Console()


def deploy_step(manifest: RunManifest) -> None:
    """Deploy the built VitePress site. Skips silently if no provider or no dist dir."""
    provider = resolve_provider(detected=manifest.deployment_platform)
    if provider is None:
        console.print(
            "[yellow]No deployment provider detected. Skipping deploy.[/yellow]"
        )
        manifest.deploy_status = "skipped"
        return

    dist_dir = Path(manifest.config.output_path) / ".vitepress" / "dist"
    if not dist_dir.is_dir():
        console.print("[yellow]No build output found. Skipping deploy.[/yellow]")
        manifest.deploy_status = "skipped"
        return

    project_name = Path(manifest.config.project_path).name
    result = deploy(dist_dir, project_name, provider)

    if result.success:
        manifest.deploy_url = result.url
        manifest.deploy_status = "success"
        console.print(f"[bold green]Deployed to {provider}:[/bold green] {result.url}")
    else:
        manifest.deploy_status = "failed"
        console.print(f"[bold red]Deploy failed:[/bold red] {result.error}")
