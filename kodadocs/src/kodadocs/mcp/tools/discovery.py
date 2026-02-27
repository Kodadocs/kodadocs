import json
from pathlib import Path
from typing import Optional

from kodadocs.models import RunManifest, SessionConfig, Framework
from kodadocs.pipeline.discovery import discovery_step, _parse_nextjs_layouts


def discover_routes_tool(
    project_path: str,
    framework: Optional[str] = None,
    app_url: Optional[str] = None,
) -> str:
    """Discover routes, services, and metadata for a project.
    Returns JSON with discovered_routes, route_metadata, detected_services, etc.
    """
    path = Path(project_path)
    if not path.exists():
        return json.dumps(
            {
                "status": "error",
                "message": f"Project path does not exist: {project_path}",
            }
        )

    # Resolve framework: explicit override or auto-detect
    resolved_framework = Framework.UNKNOWN
    if framework:
        for f in Framework:
            if f.value == framework:
                resolved_framework = f
                break

    config = SessionConfig(
        app_url=app_url or "http://localhost:3000",
        project_path=path,
        output_path=path / "docs",
        framework=resolved_framework,
        skip_ai=True,
    )
    manifest = RunManifest(session_id="mcp_discovery", config=config)

    try:
        discovery_step(manifest)
    except Exception as e:
        return json.dumps(
            {
                "status": "error",
                "message": str(e),
                "discovered_routes": manifest.discovered_routes,
            }
        )

    # Extract nav links for Next.js projects
    nav_links = []
    detected_fw = manifest.config.framework
    if isinstance(detected_fw, str):
        is_nextjs = detected_fw == Framework.NEXTJS.value
    else:
        is_nextjs = detected_fw == Framework.NEXTJS
    if is_nextjs:
        nav_links = _parse_nextjs_layouts(path)

    framework_value = manifest.config.framework
    if isinstance(framework_value, Framework):
        framework_value = framework_value.value

    return json.dumps(
        {
            "status": "ok",
            "framework": framework_value,
            "discovered_routes": manifest.discovered_routes,
            "route_metadata": manifest.route_metadata,
            "detected_services": manifest.detected_services,
            "ui_components": manifest.ui_components,
            "deployment_platform": manifest.deployment_platform,
            "nav_links": nav_links,
        }
    )
