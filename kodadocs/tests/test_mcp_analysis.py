import json
from kodadocs.mcp.tools.analysis import analyze_codebase_tool


def test_analyze_codebase_returns_json(tmp_path):
    """Tool always returns valid JSON with expected top-level keys."""
    (tmp_path / "app.py").write_text('def hello():\n    return "world"\n')

    result = analyze_codebase_tool(str(tmp_path))
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert "code_chunks" in parsed
    assert "error_patterns" in parsed
    assert "data_models" in parsed
    assert "chunk_count" in parsed
    assert "files_analyzed" in parsed


def test_analyze_codebase_python_functions(tmp_path):
    """Tree-sitter extracts Python function definitions."""
    (tmp_path / "app.py").write_text(
        """
def create_user(name: str):
    return {"name": name}

def delete_user(user_id: int):
    return True
"""
    )

    result = analyze_codebase_tool(str(tmp_path))
    parsed = json.loads(result)
    assert parsed["chunk_count"] == 2
    contents = [c["content"] for c in parsed["code_chunks"]]
    assert any("create_user" in c for c in contents)
    assert any("delete_user" in c for c in contents)


def test_analyze_codebase_typescript_classes(tmp_path):
    """Tree-sitter extracts TypeScript function declarations."""
    (tmp_path / "app.ts").write_text(
        """
function fetchUsers(): Promise<User[]> {
    return fetch("/api/users").then(r => r.json());
}
"""
    )

    result = analyze_codebase_tool(str(tmp_path))
    parsed = json.loads(result)
    assert parsed["chunk_count"] >= 1
    contents = [c["content"] for c in parsed["code_chunks"]]
    assert any("fetchUsers" in c for c in contents)


def test_analyze_codebase_error_patterns(tmp_path):
    """Regex extracts throw/raise error patterns."""
    (tmp_path / "app.ts").write_text(
        """
function validate(email: string) {
    if (!email) throw new Error("Email is required");
    if (!email.includes("@")) throw new Error("Invalid email format");
}
"""
    )

    result = analyze_codebase_tool(str(tmp_path))
    parsed = json.loads(result)
    assert "Email is required" in parsed["error_patterns"]
    assert "Invalid email format" in parsed["error_patterns"]


def test_analyze_codebase_prisma_models(tmp_path):
    """Detects Prisma model declarations."""
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(
        """
model User {
  id    Int     @id @default(autoincrement())
  email String  @unique
}

model Post {
  id    Int     @id @default(autoincrement())
  title String
}
"""
    )

    result = analyze_codebase_tool(str(tmp_path))
    parsed = json.loads(result)
    assert "User" in parsed["data_models"]
    assert "Post" in parsed["data_models"]


def test_analyze_codebase_drizzle_models(tmp_path):
    """Detects Drizzle ORM pgTable declarations."""
    (tmp_path / "schema.ts").write_text(
        """
import { pgTable, serial, text } from "drizzle-orm/pg-core";

export const users = pgTable("users", {
  id: serial("id").primaryKey(),
  name: text("name"),
});
"""
    )

    result = analyze_codebase_tool(str(tmp_path))
    parsed = json.loads(result)
    assert "users" in parsed["data_models"]


def test_analyze_codebase_empty_project(tmp_path):
    """Empty project returns empty arrays without crashing."""
    result = analyze_codebase_tool(str(tmp_path))
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert parsed["code_chunks"] == []
    assert parsed["error_patterns"] == []
    assert parsed["data_models"] == []
    assert parsed["chunk_count"] == 0
    assert parsed["files_analyzed"] == 0


def test_analyze_codebase_chunk_limit(tmp_path):
    """Large projects cap code chunks at 100."""
    for i in range(120):
        (tmp_path / f"module_{i}.py").write_text(
            f"def func_{i}():\n    return {i}\n"
        )

    result = analyze_codebase_tool(str(tmp_path))
    parsed = json.loads(result)
    assert parsed["chunk_count"] <= 100
    assert len(parsed["code_chunks"]) <= 100


def test_analyze_codebase_ignores_node_modules(tmp_path):
    """Skips node_modules, .git, dist, and other ignored directories."""
    (tmp_path / "app.py").write_text('def real():\n    return "yes"\n')
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text(
        "function hidden() { return false; }"
    )
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hook.py").write_text("def git_internal():\n    pass\n")

    result = analyze_codebase_tool(str(tmp_path))
    parsed = json.loads(result)
    contents = [c["content"] for c in parsed["code_chunks"]]
    assert any("real" in c for c in contents)
    assert not any("hidden" in c for c in contents)
    assert not any("git_internal" in c for c in contents)


def test_analyze_codebase_invalid_path():
    """Non-existent path returns error status."""
    result = analyze_codebase_tool("/nonexistent/path/that/does/not/exist")
    parsed = json.loads(result)
    assert parsed["status"] == "error"


def test_analyze_codebase_with_routes_context(tmp_path):
    """Passing discovered_routes doesn't break anything."""
    (tmp_path / "app.py").write_text('def hello():\n    return "world"\n')

    result = analyze_codebase_tool(
        str(tmp_path), discovered_routes=["/", "/dashboard"]
    )
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert parsed["chunk_count"] >= 1
