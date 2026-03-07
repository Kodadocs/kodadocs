import json
from pathlib import Path
from typing import Optional

from kodadocs.models import RunManifest, SessionConfig, AuthConfig, Framework
from kodadocs.pipeline.capture import capture_step, _check_app_reachable
from kodadocs.pipeline.targeted_capture import capture_targeted
from kodadocs.pipeline.gif_recorder import record_gif
from kodadocs.utils.license import is_pro
from kodadocs.utils.messaging import (
    page_limit_warning,
    auth_gate_warning,
    targeted_capture_gate_warning,
    gif_recording_gate_warning,
)

FREE_TIER_PAGE_LIMIT = 15


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

    # Pro Kit gating
    warnings: list[str] = []

    if not is_pro():
        if len(routes) > FREE_TIER_PAGE_LIMIT:
            warnings.append(page_limit_warning(len(routes), FREE_TIER_PAGE_LIMIT))
            routes = routes[:FREE_TIER_PAGE_LIMIT]
        if auth:
            warnings.append(auth_gate_warning())
            auth = None

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

    result = {
        "status": "ok",
        "screenshots": manifest.screenshots,
        "dom_elements": {k: v for k, v in manifest.dom_elements.items()},
        "pii_regions": manifest.pii_regions,
    }
    if warnings:
        result["warnings"] = warnings
    return json.dumps(result)


VALID_GIF_ACTIONS = {"navigate", "click", "type", "scroll", "wait", "hover"}


def capture_targeted_tool(
    targets: list[dict],
    app_url: str,
    auth: Optional[dict],
    output_dir: str,
    blur_pii: bool = True,
) -> str:
    """Capture targeted screenshots of specific CSS selectors or clipped regions.
    Returns JSON with status and targeted_screenshots dict.
    Hard Pro gate — requires the Pro Kit to be installed.
    """
    if not is_pro():
        return json.dumps({
            "status": "error",
            "message": targeted_capture_gate_warning(),
            "targeted_screenshots": {},
        })

    if not _check_app_reachable(app_url):
        return json.dumps({
            "status": "error",
            "message": f"Could not reach {app_url}. Start your app first.",
            "targeted_screenshots": {},
        })

    # Validate targets
    for i, t in enumerate(targets):
        if "route" not in t or "label" not in t:
            return json.dumps({
                "status": "error",
                "message": f"Target {i} missing required 'route' and/or 'label' fields.",
                "targeted_screenshots": {},
            })
        if "selector" not in t and "clip" not in t:
            return json.dumps({
                "status": "error",
                "message": f"Target {i} ('{t['label']}') must have either 'selector' or 'clip'.",
                "targeted_screenshots": {},
            })

    try:
        result = capture_targeted(
            targets=targets,
            app_url=app_url,
            auth_config=auth,
            output_dir=output_dir,
            blur_pii=blur_pii,
        )
        return json.dumps(result)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e),
            "targeted_screenshots": {},
        })


def record_gif_tool(
    steps: list[dict],
    app_url: str,
    auth: Optional[dict],
    output_dir: str,
    label: str = "recording",
    frame_duration_ms: int = 2500,
    width: int = 1280,
    height: int = 720,
    blur_pii: bool = True,
) -> str:
    """Record a multi-step browser interaction as an animated GIF.
    Returns JSON with status, gif_path, frame_count, duration_seconds, file_size_bytes.
    Hard Pro gate — requires the Pro Kit to be installed.
    """
    if not is_pro():
        return json.dumps({
            "status": "error",
            "message": gif_recording_gate_warning(),
            "gif_path": "",
            "frame_count": 0,
            "duration_seconds": 0,
            "file_size_bytes": 0,
        })

    if not _check_app_reachable(app_url):
        return json.dumps({
            "status": "error",
            "message": f"Could not reach {app_url}. Start your app first.",
            "gif_path": "",
            "frame_count": 0,
            "duration_seconds": 0,
            "file_size_bytes": 0,
        })

    # Validate steps
    for i, step in enumerate(steps):
        if "action" not in step:
            return json.dumps({
                "status": "error",
                "message": f"Step {i} missing required 'action' field.",
                "gif_path": "",
                "frame_count": 0,
                "duration_seconds": 0,
                "file_size_bytes": 0,
            })
        if step["action"] not in VALID_GIF_ACTIONS:
            return json.dumps({
                "status": "error",
                "message": f"Step {i} has invalid action '{step['action']}'. Valid: {', '.join(sorted(VALID_GIF_ACTIONS))}",
                "gif_path": "",
                "frame_count": 0,
                "duration_seconds": 0,
                "file_size_bytes": 0,
            })

    try:
        result = record_gif(
            steps=steps,
            app_url=app_url,
            auth_config=auth,
            output_dir=output_dir,
            label=label,
            frame_duration_ms=frame_duration_ms,
            width=width,
            height=height,
            blur_pii=blur_pii,
        )
        return json.dumps(result)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e),
            "gif_path": "",
            "frame_count": 0,
            "duration_seconds": 0,
            "file_size_bytes": 0,
        })
