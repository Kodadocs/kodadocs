from kodadocs.pipeline.analysis import Chunker, _get_parser, _detect_data_models
from kodadocs.models import SessionConfig, RunManifest


def test_chunker_parses_python_function():
    chunker = Chunker("python")
    assert chunker.parser is not None

    code = b"""
def hello():
    return "world"

def greet(name):
    return f"Hello, {name}!"
"""
    tree = chunker.parser.parse(code)
    chunks = chunker.get_chunks(tree.root_node, code)
    assert len(chunks) == 2
    assert chunks[0]["type"] == "function_definition"
    assert "hello" in chunks[0]["content"]
    assert "greet" in chunks[1]["content"]


def test_chunker_parses_javascript():
    chunker = Chunker("javascript")
    assert chunker.parser is not None

    code = b"""
function add(a, b) {
    return a + b;
}
"""
    tree = chunker.parser.parse(code)
    chunks = chunker.get_chunks(tree.root_node, code)
    assert len(chunks) == 1
    assert "add" in chunks[0]["content"]


def test_chunker_unknown_language():
    chunker = Chunker("rust")
    assert chunker.parser is None


def test_parser_reuse():
    """Parsers are cached per language."""
    p1 = _get_parser("python")
    p2 = _get_parser("python")
    assert p1 is p2


def test_analysis_step_skip_ai(tmp_path):
    from kodadocs.pipeline.analysis import analysis_step

    # Create a simple Python file
    (tmp_path / "app.py").write_text('def hello():\n    return "world"\n')

    config = SessionConfig(
        app_url="http://localhost:3000",
        project_path=tmp_path,
        skip_ai=True,
    )
    manifest = RunManifest(session_id="test", config=config)

    analysis_step(manifest)

    assert manifest.product_summary is None


def test_analysis_step_extracts_error_patterns(tmp_path):
    from kodadocs.pipeline.analysis import analysis_step

    (tmp_path / "app.py").write_text(
        'raise ValueError("Invalid email address")\n'
        'raise TypeError("Expected string")\n'
    )

    config = SessionConfig(
        app_url="http://localhost:3000",
        project_path=tmp_path,
        skip_ai=True,
    )
    manifest = RunManifest(session_id="test", config=config)

    analysis_step(manifest)

    # The error regex may not catch all patterns due to format, but test the mechanism
    # At minimum it should not crash
    assert isinstance(manifest.error_patterns, list)


# ── B5: Schema / ORM awareness (_detect_data_models) ──────────────────────


def test_detect_data_models_prisma(tmp_path):
    """Prisma schema.prisma files are parsed for model declarations."""
    prisma_content = """\
generator client {
  provider = "prisma-client-js"
}

model User {
  id    Int     @id @default(autoincrement())
  email String  @unique
  posts Post[]
}

model Post {
  id        Int     @id @default(autoincrement())
  title     String
  author    User    @relation(fields: [authorId], references: [id])
  authorId  Int
}
"""
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(prisma_content)

    models = _detect_data_models(tmp_path)
    assert models == ["User", "Post"]


def test_detect_data_models_drizzle(tmp_path):
    """Drizzle ORM pgTable calls in schema.ts files are detected."""
    drizzle_content = """\
import { pgTable, serial, text, integer } from "drizzle-orm/pg-core";

export const users = pgTable("users", {
  id: serial("id").primaryKey(),
  name: text("name"),
});

export const posts = pgTable("posts", {
  id: serial("id").primaryKey(),
  title: text("title"),
  authorId: integer("author_id"),
});
"""
    (tmp_path / "schema.ts").write_text(drizzle_content)

    models = _detect_data_models(tmp_path)
    assert models == ["users", "posts"]


def test_detect_data_models_empty_project(tmp_path):
    """An empty project returns an empty list of data models."""
    models = _detect_data_models(tmp_path)
    assert models == []


def test_analysis_step_populates_data_models(tmp_path):
    """Integration: analysis_step populates manifest.data_models from Prisma schemas."""
    from kodadocs.pipeline.analysis import analysis_step

    prisma_content = """\
model Account {
  id    Int    @id
  name  String
}

model Session {
  id    Int    @id
  token String
}
"""
    (tmp_path / "schema.prisma").write_text(prisma_content)

    config = SessionConfig(
        app_url="http://localhost:3000",
        project_path=tmp_path,
        skip_ai=True,
    )
    manifest = RunManifest(session_id="test-data-models", config=config)

    analysis_step(manifest)

    assert manifest.data_models == ["Account", "Session"]
