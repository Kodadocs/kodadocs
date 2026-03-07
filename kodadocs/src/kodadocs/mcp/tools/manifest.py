import json
from pathlib import Path


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Lists and scalars are replaced."""
    merged = base.copy()
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def save_manifest_tool(manifest: dict, project_path: str) -> str:
    """Save a RunManifest dict to .kodadocs/run_manifest.json.
    Accepts a partial manifest dict — deep merges with existing if present.
    """
    path = Path(project_path)
    kodadocs_dir = path / ".kodadocs"
    kodadocs_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = kodadocs_dir / "run_manifest.json"

    existing = {}
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())

    merged = _deep_merge(existing, manifest)
    manifest_path.write_text(json.dumps(merged, indent=2, default=str))

    return json.dumps({"status": "ok", "path": str(manifest_path)})


def load_manifest_tool(project_path: str) -> str:
    """Load the RunManifest from .kodadocs/run_manifest.json."""
    manifest_path = Path(project_path) / ".kodadocs" / "run_manifest.json"

    if not manifest_path.exists():
        return json.dumps({"status": "error", "message": "No manifest found"})

    data = json.loads(manifest_path.read_text())
    return json.dumps({"status": "ok", "manifest": data})
