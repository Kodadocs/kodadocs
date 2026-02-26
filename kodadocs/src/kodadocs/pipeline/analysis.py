import os
import re
from typing import List, Dict
from pathlib import Path
from tree_sitter import Language, Parser, Node
import tree_sitter_python as tspy
import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
import anthropic
from ..models import RunManifest
from rich.console import Console

# Supported Languages
LANGUAGES = {
    "python": Language(tspy.language()),
    "javascript": Language(tsjs.language()),
    "typescript": Language(tsts.language_typescript()),
    "tsx": Language(tsts.language_tsx()),
}

# Reuse parsers per language instead of creating new ones per file
_PARSERS: Dict[str, Parser] = {}


def _get_parser(lang_name: str):
    if lang_name not in _PARSERS:
        language = LANGUAGES.get(lang_name)
        if language:
            _PARSERS[lang_name] = Parser(language)
    return _PARSERS.get(lang_name)


class Chunker:
    def __init__(self, lang_name: str):
        self.parser = _get_parser(lang_name)

    def get_chunks(self, node: Node, code: bytes) -> List[Dict]:
        chunks = []
        meaningful = {
            "function_definition",
            "class_definition",
            "method_definition",
            "function_declaration",
        }
        if node.type in meaningful:
            content = code[node.start_byte : node.end_byte].decode(
                "utf-8", errors="ignore"
            )
            if len(content) < 2000:
                chunks.append({"type": node.type, "content": content})
                return chunks
        for child in node.children:
            chunks.extend(self.get_chunks(child, code))
        if not chunks and node.parent is None:
            chunks.append(
                {"type": "module", "content": code.decode("utf-8", errors="ignore")}
            )
        return chunks


def _detect_data_models(project_path: Path) -> List[str]:
    """Detect data models from Prisma schemas and Drizzle ORM definitions."""
    models: List[str] = []

    # Prisma: scan for schema.prisma
    for schema_path in project_path.rglob("schema.prisma"):
        try:
            content = schema_path.read_text(errors="ignore")
            prisma_models = re.findall(r"model\s+(\w+)\s*\{", content)
            models.extend(prisma_models)
        except OSError:
            pass

    # Drizzle: scan for pgTable/sqliteTable/mysqlTable calls in schema files
    drizzle_patterns = [
        r'(?:pgTable|sqliteTable|mysqlTable)\s*\(\s*["\'](\w+)["\']',
    ]
    ignore = {".git", "node_modules", "dist", "build", ".next"}
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ignore]
        for file in files:
            if not file.endswith((".ts", ".js")):
                continue
            # Only check files likely to contain schema definitions
            if (
                "schema" not in file.lower()
                and "drizzle" not in file.lower()
                and "db" not in file.lower()
            ):
                continue
            fpath = Path(root) / file
            try:
                content = fpath.read_text(errors="ignore")
                if "drizzle-orm" not in content and "Table" not in content:
                    continue
                for pattern in drizzle_patterns:
                    matches = re.findall(pattern, content)
                    models.extend(matches)
            except OSError:
                pass

    return list(dict.fromkeys(models))  # Deduplicate preserving order


def analysis_step(manifest: RunManifest):
    console = Console()
    project_path = manifest.config.project_path
    all_chunks = []
    error_patterns = []

    # Detect data models (Prisma, Drizzle)
    data_models = _detect_data_models(project_path)
    manifest.data_models = data_models
    if data_models:
        console.print(
            f"Detected data models: [bold cyan]{', '.join(data_models)}[/bold cyan]"
        )

    lang_map = {
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".py": "python",
    }

    ignore = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        "docs",
        ".kodadocs",
    }

    # Regex for error extraction
    error_regex = re.compile(
        r'(?:throw new Error|raise [A-Za-z]+Error|console\.error|logger\.error)\(["\'](.+?)["\']\)'
    )

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ignore]
        for file in files:
            fpath = Path(root) / file
            if fpath.suffix in lang_map:
                lang = lang_map[fpath.suffix]
                chunker = Chunker(lang)

                try:
                    with open(fpath, "rb") as f:
                        code = f.read()

                        content_str = code.decode("utf-8", errors="ignore")
                        matches = error_regex.findall(content_str)
                        if matches:
                            error_patterns.extend(matches)

                        if chunker.parser:
                            tree = chunker.parser.parse(code)
                            all_chunks.extend(chunker.get_chunks(tree.root_node, code))
                except Exception as e:
                    console.print(f"[yellow]Error processing {fpath}: {e}[/yellow]")

    manifest.error_patterns = list(set(error_patterns))
    console.print(
        f"Extracted [bold]{len(all_chunks)}[/bold] code chunks and [bold]{len(manifest.error_patterns)}[/bold] error patterns."
    )

    # AI Understanding with Claude
    if manifest.config.skip_ai:
        return

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return

    client = anthropic.Anthropic(api_key=api_key)
    model = manifest.config.ai_model

    # Prepare context from chunks (limit to stay within tokens)
    context = ""
    for i, chunk in enumerate(all_chunks[:50]):
        context += f"\n---\nChunk {i} ({chunk['type']}):\n{chunk['content'][:500]}\n"

    if manifest.error_patterns:
        context += (
            "\n\nDetected Error Messages (for Troubleshooting section):\n"
            + "\n".join(manifest.error_patterns[:20])
        )

    console.print(f"Requesting product summary from Claude ([cyan]{model}[/cyan])...")
    try:
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": f"Based on the following code chunks, provide a high-level product summary and a suggested help center documentation outline (as a JSON-like structure). Focus on user-facing features, NOT technical implementation.\n\nCODE CONTEXT:\n{context}",
                }
            ],
        )
        raw_summary = response.content[0].text
        # Strip trailing JSON code blocks, raw JSON blobs, and outline headings
        # so the summary is clean prose for tagline extraction and display.
        cleaned = re.sub(r"```json\s*.*?```", "", raw_summary, flags=re.DOTALL)
        cleaned = re.sub(
            r"\{[\s\S]*\"articles\"[\s\S]*\}", "", cleaned, flags=re.DOTALL
        )
        cleaned = re.sub(
            r"##?\s*(?:Suggested|Outline|Documentation).*",
            "",
            cleaned,
            flags=re.DOTALL,
        )
        manifest.product_summary = cleaned.strip()

        # Cost tracking
        if "Analysis" in manifest.steps:
            in_cost = response.usage.input_tokens * (3.0 / 1_000_000)
            out_cost = response.usage.output_tokens * (15.0 / 1_000_000)
            manifest.steps["Analysis"].cost_estimate += in_cost + out_cost

        console.print("Product summary generated.")
    except Exception as e:
        console.print(f"[red]AI analysis failed: {e}[/red]")
        manifest.product_summary = "AI analysis failed (API error). Please check your credentials or usage limits."
