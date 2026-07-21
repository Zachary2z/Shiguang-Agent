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
        "aiohttp",
        "dashscope",
        "httpx",
        "openai",
        "pathlib",
        "requests",
        "socket",
        "urllib",
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


def test_application_persistence_does_not_import_nanobot_core() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    persistence_roots = [
        backend_root / "app" / "infrastructure" / "db",
        backend_root / "app" / "infrastructure" / "repositories",
    ]
    discovered: list[tuple[str, str]] = []

    for persistence_root in persistence_roots:
        for source_path in sorted(persistence_root.rglob("*.py")):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                else:
                    continue
                for name in names:
                    if name.split(".", maxsplit=1)[0] == "nanobot_core":
                        discovered.append((str(source_path.relative_to(backend_root)), name))

    assert discovered == []


def test_public_runtime_contracts_each_have_one_production_definition() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    production_roots = [backend_root / "app", backend_root / "nanobot_core"]
    expected_once = {
        "AgentRunRepository",
        "AgentRunStatus",
        "AgentRunner",
        "ModelProvider",
        "ProviderError",
        "TokenUsage",
        "ToolRegistry",
        "ToolResult",
        "ToolRunStatus",
    }
    definitions: dict[str, list[str]] = {name: [] for name in expected_once}

    for production_root in production_roots:
        for source_path in sorted(production_root.rglob("*.py")):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name in definitions:
                    definitions[node.name].append(str(source_path.relative_to(backend_root)))

    assert all(len(paths) == 1 for paths in definitions.values()), definitions
