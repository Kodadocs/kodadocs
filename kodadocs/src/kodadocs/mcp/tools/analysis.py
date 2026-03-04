import json
import os
import re
from pathlib import Path
from typing import Optional, List, Dict

from kodadocs.pipeline.analysis import Chunker, _detect_data_models


# Match the ignore list from pipeline/analysis.py
IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "docs",
    ".kodadocs",
    ".next",
}

LANG_MAP = {
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".py": "python",
}

MAX_CHUNKS = 100

# Same regex used in pipeline/analysis.py
ERROR_REGEX = re.compile(
    r'(?:throw new Error|raise [A-Za-z]+Error|console\.error|logger\.error)\(["\'](.+?)["\']\)'
)


def analyze_codebase_tool(
    project_path: str,
    discovered_routes: Optional[List[str]] = None,
) -> str:
    """Analyze codebase structure using tree-sitter. Extracts code chunks,
    error patterns, and data models. No AI calls — deterministic only.
    Returns JSON with code_chunks, error_patterns, data_models, counts.
    """
    path = Path(project_path)
    if not path.exists():
        return json.dumps(
            {
                "status": "error",
                "message": f"Project path does not exist: {project_path}",
            }
        )

    all_chunks: List[Dict] = []
    error_patterns: List[str] = []
    files_analyzed = 0

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            fpath = Path(root) / file
            if fpath.suffix not in LANG_MAP:
                continue

            lang = LANG_MAP[fpath.suffix]
            chunker = Chunker(lang)

            try:
                code = fpath.read_bytes()
                files_analyzed += 1

                # Extract error patterns
                content_str = code.decode("utf-8", errors="ignore")
                matches = ERROR_REGEX.findall(content_str)
                if matches:
                    error_patterns.extend(matches)

                # Extract code chunks via tree-sitter
                if chunker.parser and len(all_chunks) < MAX_CHUNKS:
                    tree = chunker.parser.parse(code)
                    chunks = chunker.get_chunks(tree.root_node, code)
                    remaining = MAX_CHUNKS - len(all_chunks)
                    all_chunks.extend(chunks[:remaining])
            except Exception:
                continue

    # Detect data models (Prisma, Drizzle)
    data_models = _detect_data_models(path)

    return json.dumps(
        {
            "status": "ok",
            "code_chunks": all_chunks[:MAX_CHUNKS],
            "error_patterns": list(set(error_patterns)),
            "data_models": data_models,
            "chunk_count": len(all_chunks),
            "files_analyzed": files_analyzed,
        }
    )
