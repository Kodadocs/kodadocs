from pathlib import Path
from kodadocs.utils.framework import detect_frameworks


def detect_framework_tool(project_path: str) -> str:
    """Detect the web framework of a project at the given path."""
    path = Path(project_path)
    if not path.exists():
        return f"Error: path {project_path} does not exist"
    framework = detect_frameworks(path, skip_ai=True)
    return framework.value
