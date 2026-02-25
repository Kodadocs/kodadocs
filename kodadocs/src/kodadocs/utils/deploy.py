"""Core deploy engine for static site deployment to multiple providers."""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kodadocs.utils.badge import inject_badge


@dataclass
class DeployResult:
    success: bool
    url: Optional[str] = None
    provider: Optional[str] = None
    error: Optional[str] = None


SUPPORTED_PROVIDERS = {"cloudflare", "vercel", "netlify", "github-pages"}

_PROVIDER_CLI = {
    "cloudflare": "wrangler",
    "vercel": "vercel",
    "netlify": "netlify",
    "github-pages": "npx",
}

_PROVIDER_ENV = {
    "cloudflare": ["CLOUDFLARE_API_TOKEN"],
    "vercel": ["VERCEL_TOKEN"],
    "netlify": ["NETLIFY_AUTH_TOKEN", "NETLIFY_SITE_ID"],
    "github-pages": [],
}

_PROVIDER_INSTALL_HINT = {
    "cloudflare": "npm install -g wrangler",
    "vercel": "npm install -g vercel",
    "netlify": "npm install -g netlify-cli",
    "github-pages": "npm install -g gh-pages",
}

_PROVIDER_TIMEOUT = {
    "cloudflare": 120,
    "vercel": 120,
    "netlify": 120,
    "github-pages": 180,
}


def _normalize_provider(name: str) -> str:
    """Normalize provider name: underscores to hyphens, lowercase."""
    return name.lower().replace("_", "-")


def resolve_provider(
    explicit: Optional[str] = None,
    detected: Optional[str] = None,
) -> Optional[str]:
    """Resolve which provider to use. Explicit wins over detected.

    Returns normalized provider name or None if unresolvable.
    """
    raw = explicit or detected
    if raw is None:
        return None
    normalized = _normalize_provider(raw)
    if normalized not in SUPPORTED_PROVIDERS:
        return None
    return normalized


def _check_cli(provider: str) -> Optional[str]:
    """Check if the provider's CLI is installed. Returns error message or None."""
    cli = _PROVIDER_CLI[provider]
    if shutil.which(cli) is None:
        hint = _PROVIDER_INSTALL_HINT[provider]
        return f"CLI '{cli}' not found. Install it with: {hint}"
    return None


def _check_env(provider: str) -> Optional[str]:
    """Check if required env vars are set. Returns error message or None."""
    required = _PROVIDER_ENV[provider]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        return f"Missing environment variables for {provider}: {', '.join(missing)}"
    return None


def _build_command(provider: str, dist_dir: Path, project_name: str) -> list[str]:
    """Build the deploy command for a provider."""
    dist = str(dist_dir)
    if provider == "cloudflare":
        return ["wrangler", "pages", "deploy", dist, f"--project-name={project_name}"]
    elif provider == "vercel":
        token = os.environ.get("VERCEL_TOKEN", "")
        return ["vercel", "deploy", "--prod", "--token", token, dist]
    elif provider == "netlify":
        token = os.environ.get("NETLIFY_AUTH_TOKEN", "")
        site_id = os.environ.get("NETLIFY_SITE_ID", "")
        return ["netlify", "deploy", "--dir", dist, "--prod", "--auth", token, "--site", site_id]
    elif provider == "github-pages":
        return ["npx", "gh-pages", "-d", dist]
    else:
        raise ValueError(f"Unknown provider: {provider}")


def _extract_url(provider: str, project_name: str, stdout: str) -> Optional[str]:
    """Extract the deployed URL from CLI output."""
    if provider == "cloudflare":
        # wrangler prints the URL; fallback to convention
        for line in stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("https://"):
                return stripped
        return f"https://{project_name}.pages.dev"
    elif provider == "vercel":
        # vercel prints the production URL
        for line in stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("https://"):
                return stripped
        return None
    elif provider == "netlify":
        for line in stdout.splitlines():
            stripped = line.strip()
            if "https://" in stripped and ".netlify" in stripped:
                # Extract URL from lines like "Website URL: https://..."
                parts = stripped.split("https://")
                if len(parts) >= 2:
                    return "https://" + parts[-1].split()[0]
        return None
    elif provider == "github-pages":
        return f"https://{project_name}.github.io"
    return None


def deploy(
    dist_dir: Path,
    project_name: str,
    provider: str,
    *,
    license_key: Optional[str] = None,
    site_slug: Optional[str] = None,
) -> DeployResult:
    """Deploy a static site directory to the specified provider.

    Pre-flight checks run before any subprocess call.
    Badge injection happens before provider dispatch.
    """
    # Validate provider
    if provider not in SUPPORTED_PROVIDERS:
        return DeployResult(
            success=False,
            provider=provider,
            error=f"Unsupported provider: {provider}. Supported: {', '.join(sorted(SUPPORTED_PROVIDERS))}",
        )

    # Check dist dir exists
    if not dist_dir.is_dir():
        return DeployResult(
            success=False,
            provider=provider,
            error=f"Build directory not found: {dist_dir}. Run the build step first.",
        )

    # Inject badge into all HTML files
    inject_badge(dist_dir)

    # Pre-flight: CLI installed?
    cli_err = _check_cli(provider)
    if cli_err:
        return DeployResult(success=False, provider=provider, error=cli_err)

    # Pre-flight: env vars set?
    env_err = _check_env(provider)
    if env_err:
        return DeployResult(success=False, provider=provider, error=env_err)

    # Build and run command
    cmd = _build_command(provider, dist_dir, project_name)
    timeout = _PROVIDER_TIMEOUT[provider]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return DeployResult(
            success=False,
            provider=provider,
            error=f"Deploy timed out after {timeout}s",
        )

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        return DeployResult(
            success=False,
            provider=provider,
            error=f"Deploy failed (exit {result.returncode}): {stderr[:500]}",
        )

    url = _extract_url(provider, project_name, result.stdout)
    return DeployResult(success=True, url=url, provider=provider)
