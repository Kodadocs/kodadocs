import json
from pathlib import Path
from typing import Optional

from kodadocs.utils.deploy import resolve_provider, deploy


def deploy_site_tool(
    site_dir: str,
    project_name: str,
    provider: Optional[str] = None,
    detected_platform: Optional[str] = None,
    license_key: Optional[str] = None,
    site_slug: Optional[str] = None,
) -> str:
    """Deploy a VitePress site to a supported hosting provider.

    Resolves the dist directory from site_dir/.vitepress/dist/,
    picks the provider (explicit or auto-detected), and deploys.
    """
    resolved = resolve_provider(explicit=provider, detected=detected_platform)
    if resolved is None:
        return json.dumps({
            "status": "error",
            "error": "No provider specified. Pass provider='cloudflare', 'vercel', 'netlify', or 'github-pages'.",
        })

    dist_dir = Path(site_dir) / ".vitepress" / "dist"
    result = deploy(
        dist_dir, project_name, resolved,
        license_key=license_key, site_slug=site_slug,
    )

    if result.success:
        return json.dumps({
            "status": "ok",
            "url": result.url,
            "provider": result.provider,
        })
    else:
        return json.dumps({
            "status": "error",
            "provider": result.provider,
            "error": result.error,
        })
