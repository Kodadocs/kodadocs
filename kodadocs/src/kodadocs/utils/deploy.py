"""Core deploy engine for static site deployment to multiple providers."""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kodadocs.utils.badge import inject_badge
from kodadocs.utils.license import is_pro, is_valid_license_key

KODADOCS_API_URL = os.environ.get("KODADOCS_API_URL", "https://api.kodadocs.com")


@dataclass
class DeployResult:
    success: bool
    url: Optional[str] = None
    provider: Optional[str] = None
    error: Optional[str] = None


SUPPORTED_PROVIDERS = {"cloudflare", "vercel", "netlify", "github-pages", "kodadocs"}

_PROVIDER_CLI = {
    "cloudflare": "wrangler",
    "vercel": "vercel",
    "netlify": "netlify",
    "github-pages": "npx",
    "kodadocs": None,  # Not a CLI-based provider; uses API (Plan 06-03)
}

_PROVIDER_ENV = {
    "cloudflare": ["CLOUDFLARE_API_TOKEN"],
    "vercel": ["VERCEL_TOKEN"],
    "netlify": ["NETLIFY_AUTH_TOKEN", "NETLIFY_SITE_ID"],
    "github-pages": [],
    "kodadocs": ["KODADOCS_LICENSE_KEY"],
}

_PROVIDER_INSTALL_HINT = {
    "cloudflare": "npm install -g wrangler",
    "vercel": "npm install -g vercel",
    "netlify": "npm install -g netlify-cli",
    "github-pages": "npm install -g gh-pages",
    "kodadocs": "Get a Pro license at https://kodadocs.com",
}

_PROVIDER_TIMEOUT = {
    "cloudflare": 120,
    "vercel": 120,
    "netlify": 120,
    "github-pages": 180,
    "kodadocs": 120,
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
    """Check if the provider's CLI is installed. Returns error message or None.

    Returns None (no error) when the provider has no CLI (e.g., 'kodadocs'
    uses a direct API call instead of a subprocess).
    """
    cli = _PROVIDER_CLI[provider]
    if cli is None:
        # No CLI required for this provider (API-based deploy)
        return None
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
        # --cwd points to the docs root (dist_dir is <docs>/.vitepress/dist, so parent.parent = docs root)
        # --yes skips interactive project setup prompts
        # Do NOT pass dist as positional arg — Vercel CLI interprets it as project name
        docs_root = str(dist_dir.parent.parent)
        return ["vercel", "--cwd", docs_root, "--prod", "--yes", "--token", token]
    elif provider == "netlify":
        token = os.environ.get("NETLIFY_AUTH_TOKEN", "")
        site_id = os.environ.get("NETLIFY_SITE_ID", "")
        # --no-build prevents netlify-cli v21+ from running a build before deploying pre-built output
        return [
            "netlify",
            "deploy",
            "--no-build",
            "--dir",
            dist,
            "--prod",
            "--auth",
            token,
            "--site",
            site_id,
        ]
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


def deploy_to_kodadocs(
    dist_dir: Path, site_slug: str, license_key: str
) -> DeployResult:
    """ZIP dist dir and upload to KodaDocs deploy API."""
    import json as _json
    import urllib.request
    import urllib.error
    import uuid

    # Create ZIP archive in parent directory
    zip_path = dist_dir.parent / f"{site_slug}.zip"
    try:
        shutil.make_archive(str(zip_path.with_suffix("")), "zip", dist_dir)

        # Build multipart/form-data request using stdlib
        boundary = uuid.uuid4().hex
        body_parts = []

        # slug field
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(b'Content-Disposition: form-data; name="slug"\r\n\r\n')
        body_parts.append(f"{site_slug}\r\n".encode())

        # site file
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(
            f'Content-Disposition: form-data; name="site"; filename="{site_slug}.zip"\r\n'.encode()
        )
        body_parts.append(b"Content-Type: application/zip\r\n\r\n")
        body_parts.append(zip_path.read_bytes())
        body_parts.append(b"\r\n")

        body_parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(body_parts)

        req = urllib.request.Request(
            f"{KODADOCS_API_URL}/deploy",
            data=body,
            headers={
                "X-License-Key": license_key,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "kodadocs-cli/1.0",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            data = _json.loads(resp.read())
            return DeployResult(
                success=True,
                url=data.get("url", f"https://{site_slug}.kodadocs.com"),
                provider="kodadocs",
            )

    except urllib.error.HTTPError as e:
        try:
            error_body = _json.loads(e.read())
            error_msg = error_body.get("error", f"API returned {e.code}")
        except Exception:
            error_msg = f"API returned {e.code}"
        return DeployResult(success=False, provider="kodadocs", error=error_msg)
    except urllib.error.URLError as e:
        return DeployResult(
            success=False, provider="kodadocs", error=f"Upload failed: {e.reason}"
        )
    except TimeoutError:
        return DeployResult(
            success=False, provider="kodadocs", error="Upload timed out after 120s"
        )
    except OSError as e:
        return DeployResult(
            success=False, provider="kodadocs", error=f"Upload failed: {e}"
        )
    finally:
        # Always clean up ZIP
        if zip_path.exists():
            zip_path.unlink(missing_ok=True)


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

    For the ``kodadocs`` provider, ``license_key`` and ``site_slug`` are
    required — both are validated before the upload attempt. Badge injection
    is skipped for the ``kodadocs`` provider (Pro-only feature).
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

    # kodadocs provider: validate, skip badge, call API directly
    if provider == "kodadocs":
        if not is_valid_license_key(license_key):
            return DeployResult(
                success=False,
                provider=provider,
                error=(
                    "KodaDocs hosting requires a Pro license key. "
                    "Get one at https://kodadocs.com"
                ),
            )
        if not site_slug:
            return DeployResult(
                success=False,
                provider=provider,
                error="KodaDocs hosting requires a site slug. Use --slug mysite",
            )
        # Badge injection is skipped for Pro/kodadocs provider
        return deploy_to_kodadocs(dist_dir, site_slug, license_key)

    # Inject badge only for free tier (no Pro Kit installed)
    if not is_pro():
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
