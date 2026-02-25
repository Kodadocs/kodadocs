import typer
from rich.console import Console
from rich.prompt import Prompt, Confirm
from pathlib import Path
from typing import Optional, List
from .models import SessionConfig, AuthConfig, Framework
from .utils.framework import detect_frameworks
from .orchestrator import PipelineOrchestrator
from .pipeline.discovery import discovery_step
from .pipeline.analysis import analysis_step
from .pipeline.capture import capture_step
from .pipeline.output import output_step
from .pipeline.enrichment import enrichment_step
from .pipeline.annotation import annotation_step
import json
import os

app = typer.Typer(
    help="KodaDocs — Claude Code MCP tool for generating end-user help documentation. Primary usage: add the MCP server to Claude Code and tell Claude 'Generate docs for my app'.",
    invoke_without_command=True,
)
console = Console()

from kodadocs import __version__ as VERSION

def version_callback(value: bool):
    if value:
        console.print(f"KodaDocs [bold cyan]{VERSION}[/bold cyan]")
        raise typer.Exit()

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", callback=version_callback, is_eager=True, help="Show version and exit."
    ),
):
    if ctx.invoked_subcommand is None:
        console.print()
        console.print(f"  [bold cyan]KodaDocs {VERSION}[/bold cyan]")
        console.print(f"  Claude Code MCP tool for generating help documentation")
        console.print()
        console.print("[bold]Recommended: Use with Claude Code (MCP)[/bold]")
        console.print()
        console.print('  Add to [cyan]~/.claude/settings.json[/cyan]:')
        console.print()
        console.print('    [dim]{[/dim]')
        console.print('      [dim]"mcpServers": {[/dim]')
        console.print('        [dim]"kodadocs": {[/dim]')
        console.print('          [dim]"command": "uvx",[/dim]')
        console.print('          [dim]"args": ["kodadocs", "mcp"][/dim]')
        console.print('        [dim]}[/dim]')
        console.print('      [dim]}[/dim]')
        console.print('    [dim]}[/dim]')
        console.print()
        console.print('  Then tell Claude: [green]"Generate help docs for my app"[/green]')
        console.print()
        console.print("[bold]CLI commands (power users):[/bold]")
        console.print()
        console.print("  kodadocs generate .     Run full pipeline directly")
        console.print("  kodadocs deploy .       Deploy generated docs")
        console.print("  kodadocs init .         Interactive setup wizard")
        console.print("  kodadocs config .       View/update configuration")
        console.print("  kodadocs mcp            Start MCP server")
        console.print()

@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Project path to initialize KodaDocs"),
    output: Path = typer.Option(Path("./docs"), help="Path to save generated documentation"),
):
    """Advanced setup wizard. Optional — 'kodadocs generate' works without this."""
    console.print(f"[bold green]Initializing KodaDocs for {path.absolute()}[/bold green]")

    if not path.exists():
        console.print(f"[red]Error: Project path {path} does not exist.[/red]")
        raise typer.Exit(code=1)

    app_url = Prompt.ask("What is the URL of your app (for screenshots)?", default="http://localhost:3000")
    if not app_url.startswith("http"):
        console.print("[yellow]Warning: URL should start with http:// or https://[/yellow]")
        if Confirm.ask(f"Did you mean http://{app_url}?", default=True):
            app_url = f"http://{app_url}"

    auth_config = None
    if Confirm.ask("Does your app require authentication for screenshots?"):
        auth_url = Prompt.ask("Auth URL (login page)", default=f"{app_url}/login")
        username = Prompt.ask("Username")
        password = Prompt.ask("Password", password=True)
        auth_config = AuthConfig(auth_url=auth_url, username=username, password=password)

    include_patterns = Prompt.ask("Include patterns (comma separated)", default="**/*").split(",")
    exclude_patterns = Prompt.ask("Exclude patterns (comma separated)", default="node_modules/**, .git/**").split(",")

    brand_color = Prompt.ask("Primary brand color (hex)", default="#3e8fb0")
    logo_path = Prompt.ask("Path to your logo image", default="public/logo.png")

    skip_ai = not Confirm.ask("Use AI for discovery and analysis?", default=True)
    default_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    ai_model = default_model
    if not skip_ai:
        ai_model = Prompt.ask("Anthropic model to use", default=default_model)

    # Detect framework (after skip_ai is determined so AI fallback respects the flag)
    detected_framework = detect_frameworks(path, skip_ai=skip_ai, model=ai_model)
    console.print(f"Detected framework: [cyan]{detected_framework.value}[/cyan]")

    if not Confirm.ask(f"Is [cyan]{detected_framework.value}[/cyan] the correct framework?", default=True):
        framework_options = [f.value for f in Framework]
        framework_value = Prompt.ask("Select the correct framework", choices=framework_options, default=Framework.UNKNOWN.value)
        framework = Framework(framework_value)
    else:
        framework = detected_framework

    config = SessionConfig(
        app_url=app_url,
        auth=auth_config,
        include_patterns=[p.strip() for p in include_patterns],
        exclude_patterns=[p.strip() for p in exclude_patterns],
        framework=framework,
        project_path=path.absolute(),
        output_path=output.absolute(),
        brand_color=brand_color,
        logo_path=Path(logo_path) if logo_path else None,
        ai_model=ai_model,
        skip_ai=skip_ai
    )

    # Save config to file
    kodadocs_dir = path / ".kodadocs"
    kodadocs_dir.mkdir(exist_ok=True)
    config_file = kodadocs_dir / "session_config.json"
    with open(config_file, "w") as f:
        f.write(config.model_dump_json(indent=2))

    console.print(f"[bold green]Configuration saved to {config_file}[/bold green]")
    console.print("Run [bold cyan]kodadocs generate[/bold cyan] to start the pipeline.")

@app.command()
def config(
    show: bool = typer.Option(False, "--show", "-s", help="Pretty-print current configuration"),
    url: Optional[str] = typer.Option(None, "--url", help="Update app URL"),
    brand_color: Optional[str] = typer.Option(None, "--brand-color", help="Update brand color (hex)"),
    logo: Optional[str] = typer.Option(None, "--logo", help="Update logo path"),
    model: Optional[str] = typer.Option(None, "--model", help="Update AI model"),
    output: Optional[Path] = typer.Option(None, "--output", help="Update output path"),
    framework: Optional[str] = typer.Option(None, "--framework", help="Update framework"),
    path: Path = typer.Argument(Path("."), help="Project path"),
):
    """View or update saved KodaDocs configuration."""
    path = path.resolve()
    config_file = path / ".kodadocs" / "session_config.json"

    has_updates = any(v is not None for v in [url, brand_color, logo, model, output, framework])

    if not config_file.exists():
        console.print("[yellow]No config found. Run [bold]kodadocs init[/bold] or [bold]kodadocs generate[/bold] first.[/yellow]")
        raise typer.Exit(code=1)

    with open(config_file, "r") as f:
        cfg = SessionConfig.model_validate(json.load(f))

    if has_updates:
        if url is not None:
            cfg.app_url = url
        if brand_color is not None:
            cfg.brand_color = brand_color
        if logo is not None:
            cfg.logo_path = Path(logo)
        if model is not None:
            cfg.ai_model = model
        if output is not None:
            cfg.output_path = output.resolve()
        if framework is not None:
            valid = [f.value for f in Framework]
            if framework not in valid:
                console.print(f"[red]Invalid framework '[bold]{framework}[/bold]'. Choose from: {', '.join(valid)}[/red]")
                raise typer.Exit(code=1)
            cfg.framework = Framework(framework)

        with open(config_file, "w") as f:
            f.write(cfg.model_dump_json(indent=2))
        console.print("[green]Configuration updated.[/green]")

    # Show config (always after updates, or when --show / no flags)
    if not has_updates or show:
        console.print()
        console.print("[bold cyan]KodaDocs Configuration[/bold cyan]")
        console.print(f"  app_url:     {cfg.app_url}")
        console.print(f"  framework:   {cfg.framework.value if isinstance(cfg.framework, Framework) else cfg.framework}")
        console.print(f"  output_path: {cfg.output_path}")
        console.print(f"  brand_color: {cfg.brand_color}")
        console.print(f"  logo_path:   {cfg.logo_path or '(none)'}")
        console.print(f"  ai_model:    {cfg.ai_model}")
        console.print(f"  skip_ai:     {cfg.skip_ai}")
        console.print()

@app.command()
def generate(
    path: Path = typer.Argument(Path("."), help="Project path to run KodaDocs pipeline"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Override app URL for screenshots"),
    fresh: bool = typer.Option(False, "--fresh", help="Ignore cached config, re-run from scratch"),
    user: Optional[str] = typer.Option(None, "--user", help="WordPress admin username"),
    wp_pass: Optional[str] = typer.Option(None, "--pass", help="WordPress admin password"),
    do_deploy: bool = typer.Option(False, "--deploy", help="Deploy after generation"),
):
    """Run the full pipeline directly (CLI mode). For most users, the MCP + Claude Code path is recommended instead."""
    path = path.resolve()

    if not path.exists():
        console.print(f"[bold red]Error: Project path {path} does not exist.[/bold red]")
        raise typer.Exit(code=1)

    config_file = path / ".kodadocs" / "session_config.json"

    if config_file.exists() and not fresh:
        # Load existing config
        with open(config_file, "r") as f:
            config_data = json.load(f)
            config = SessionConfig.model_validate(config_data)
    else:
        # Auto-configure: no prompts, smart defaults
        framework = detect_frameworks(path, skip_ai=True)

        skip_ai = False
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            skip_ai = True
            console.print("[yellow]ANTHROPIC_API_KEY not set. Running without AI features.[/yellow]")

        config = SessionConfig(
            project_path=path,
            output_path=(path / "docs").resolve(),
            framework=framework,
            skip_ai=skip_ai,
        )

        # Save config for next run
        kodadocs_dir = path / ".kodadocs"
        kodadocs_dir.mkdir(exist_ok=True)
        config_file = kodadocs_dir / "session_config.json"
        with open(config_file, "w") as f:
            f.write(config.model_dump_json(indent=2))

    # Apply --url override
    if url:
        config.app_url = url

    # Auto-build auth config for WordPress when --user/--pass provided
    if user and wp_pass:
        config.auth = AuthConfig(
            auth_url=f"{config.app_url}/wp-login.php",
            username=user,
            password=wp_pass,
        )

    # Print summary banner
    framework_label = config.framework if isinstance(config.framework, str) else config.framework.value
    ai_label = f"Enabled ({config.ai_model})" if not config.skip_ai else "Disabled (no API key)"
    console.print()
    console.print(f"  [bold cyan]KodaDocs {VERSION}[/bold cyan]")
    console.print(f"  Project:   {config.project_path}")
    console.print(f"  Framework: {framework_label} (auto-detected)")
    console.print(f"  App URL:   {config.app_url}")
    console.print(f"  AI:        {ai_label}")
    console.print(f"  Output:    {config.output_path}")
    console.print()

    orchestrator = PipelineOrchestrator(path)

    # Register steps
    orchestrator.register_step("Discovery", discovery_step)
    orchestrator.register_step("Analysis", analysis_step)
    orchestrator.register_step("Capture", capture_step)
    orchestrator.register_step("Annotation", annotation_step)
    orchestrator.register_step("Enrichment", enrichment_step)
    orchestrator.register_step("Output", output_step, force_rerun=True)

    if do_deploy:
        from .pipeline.deploy import deploy_step
        orchestrator.register_step("Deploy", deploy_step, critical=False, force_rerun=True)

    orchestrator.run(config)
    console.print("[bold green]Generation complete![/bold green]")

@app.command(name="deploy")
def deploy_cmd(
    path: Path = typer.Argument(Path("."), help="Project path"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Deploy provider (cloudflare, vercel, netlify, github-pages)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Docs output directory override"),
    license_key: Optional[str] = typer.Option(None, "--license-key", help="KodaDocs Pro license key"),
    site_slug: Optional[str] = typer.Option(None, "--slug", help="Site subdomain for kodadocs.com hosting"),
):
    """Deploy the generated help center to a hosting provider."""
    from .utils.deploy import resolve_provider, deploy as run_deploy

    path = path.resolve()

    # Resolve license key: CLI flag > env var
    resolved_license = license_key or os.getenv("KODADOCS_LICENSE_KEY")

    # Load manifest to get detected platform and output path
    manifest_file = path / ".kodadocs" / "run_manifest.json"
    detected_platform = None
    output_path = output or (path / "docs")

    if manifest_file.exists():
        with open(manifest_file, "r") as f:
            manifest_data = json.load(f)
            detected_platform = manifest_data.get("deployment_platform")
            if not output:
                cfg = manifest_data.get("config", {})
                if cfg.get("output_path"):
                    output_path = Path(cfg["output_path"])

    resolved = resolve_provider(explicit=provider, detected=detected_platform)
    if resolved is None:
        console.print("[bold red]Error: No deploy provider specified.[/bold red]")
        console.print("Use [bold]--provider[/bold] to choose one: cloudflare, vercel, netlify, github-pages, kodadocs")
        if detected_platform:
            console.print(f"Detected platform '{detected_platform}' is not a supported deploy target.")
        raise typer.Exit(code=1)

    dist_dir = Path(output_path) / ".vitepress" / "dist"
    if not dist_dir.is_dir():
        console.print(f"[bold red]Error: Build directory not found at {dist_dir}[/bold red]")
        console.print("Run [bold]kodadocs generate[/bold] first to build the site.")
        raise typer.Exit(code=1)

    project_name = path.name
    console.print(f"Deploying to [bold cyan]{resolved}[/bold cyan]...")

    result = run_deploy(
        dist_dir, project_name, resolved,
        license_key=resolved_license, site_slug=site_slug,
    )

    if result.success:
        console.print(f"[bold green]Deployed successfully![/bold green]")
        if result.url:
            console.print(f"  URL: [bold cyan]{result.url}[/bold cyan]")

        # Persist to manifest
        if manifest_file.exists():
            with open(manifest_file, "r") as f:
                manifest_data = json.load(f)
            manifest_data["deploy_url"] = result.url
            manifest_data["deploy_status"] = "success"
            with open(manifest_file, "w") as f:
                json.dump(manifest_data, f, indent=2)
    else:
        console.print(f"[bold red]Deploy failed:[/bold red] {result.error}")
        raise typer.Exit(code=1)


@app.command()
def mcp():
    """Start KodaDocs MCP server for Claude Code integration."""
    from kodadocs.mcp.server import run_server
    run_server()

if __name__ == "__main__":
    app()
