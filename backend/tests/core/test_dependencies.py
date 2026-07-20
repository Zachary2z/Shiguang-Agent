from __future__ import annotations

import ast
from pathlib import Path


def test_core_has_no_forbidden_framework_storage_or_business_imports() -> None:
    core_root = Path(__file__).resolve().parents[2] / "nanobot_core"
    forbidden_roots = {
        "app",
        "fastapi",
        "sqlalchemy",
        "alembic",
        "aiosqlite",
        "httpx",
        "openai",
        "pathlib",
    }
    discovered: list[tuple[str, str]] = []

    for source_path in sorted(core_root.rglob("*.py")):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                root = name.split(".", maxsplit=1)[0]
                if root in forbidden_roots:
                    discovered.append((str(source_path.relative_to(core_root)), name))

    assert discovered == []
