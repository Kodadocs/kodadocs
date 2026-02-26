import json
from pathlib import Path
from typing import Optional

from kodadocs.models import RunManifest, SessionConfig, AuthConfig, Framework
from kodadocs.pipeline.capture import capture_step, _check_app_reachable


def capture_screenshots_tool(
    routes: list[str],
    app_url: str,
    auth: Optional[dict],
    output_dir: str,
    blur_pii: bool = True,
) -> str:
    """Capture screenshots for given routes using Playwright.
    Returns JSON with status, screenshots dict, and dom_elements dict.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    project_path = output_path.parent
    if project_path.name == ".kodadocs":
        project_path = project_path.parent

    if not _check_app_reachable(app_url):
        return json.dumps(
            {
                "status": "error",
                "message": f"Could not reach {app_url}. Start your app first.",
                "screenshots": {},
                "dom_elements": {},
            }
        )

    auth_config = None
    if auth:
        auth_config = AuthConfig(
            username=auth.get("username"),
            password=auth.get("password"),
            auth_url=auth.get("auth_url"),
            cookie_name=auth.get("cookie_name"),
            cookie_value=auth.get("cookie_value"),
        )

    config = SessionConfig(
        app_url=app_url,
        auth=auth_config,
        project_path=project_path,
        output_path=project_path / "docs",
        framework=Framework.UNKNOWN,
        skip_ai=True,
        blur_pii=blur_pii,
    )
    manifest = RunManifest(
        session_id="mcp_capture",
        config=config,
        discovered_routes=routes,
    )

    try:
        capture_step(manifest)
    except Exception as e:
        return json.dumps(
            {
                "status": "error",
                "message": str(e),
                "screenshots": manifest.screenshots,
                "dom_elements": manifest.dom_elements,
                "pii_regions": manifest.pii_regions,
            }
        )

    return json.dumps(
        {
            "status": "ok",
            "screenshots": manifest.screenshots,
            "dom_elements": {k: v for k, v in manifest.dom_elements.items()},
            "pii_regions": manifest.pii_regions,
        }
    )
