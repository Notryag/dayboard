#!/usr/bin/env python3
"""Fail when a lower application layer imports a higher product layer."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_ROOT = REPOSITORY_ROOT / "packages" / "agent-platform" / "src" / "agent_platform"
DAYBOARD_ROOT = REPOSITORY_ROOT / "apps" / "api" / "src" / "dayboard"

FRAMEWORK_IMPORTS = (
    "fastapi",
    "langchain",
    "langchain_core",
    "north",
    "sqlalchemy",
)
DAYBOARD_OUTER_LAYERS = (
    "dayboard.agent",
    "dayboard.api",
    "dayboard.composition",
    "dayboard.db",
    "dayboard.integrations",
    "dayboard.tools",
    "dayboard.workers",
)


@dataclass(frozen=True)
class LayerRule:
    name: str
    source_root: Path
    forbidden_import_prefixes: tuple[str, ...]
    included_relative_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    imported_module: str
    layer: str


RULES = (
    LayerRule(
        name="agent_platform",
        source_root=PLATFORM_ROOT,
        forbidden_import_prefixes=("dayboard",),
    ),
    LayerRule(
        name="agent_platform.core",
        source_root=PLATFORM_ROOT / "core",
        forbidden_import_prefixes=(
            "agent_platform.application",
            "agent_platform.ports",
            "agent_platform.adapters",
            *FRAMEWORK_IMPORTS,
        ),
    ),
    LayerRule(
        name="agent_platform.ports",
        source_root=PLATFORM_ROOT / "ports",
        forbidden_import_prefixes=(
            "agent_platform.application",
            "agent_platform.adapters",
            *FRAMEWORK_IMPORTS,
        ),
    ),
    LayerRule(
        name="agent_platform.application",
        source_root=PLATFORM_ROOT / "application",
        forbidden_import_prefixes=(
            "agent_platform.adapters",
            *FRAMEWORK_IMPORTS,
        ),
    ),
    LayerRule(
        name="dayboard.domain",
        source_root=DAYBOARD_ROOT / "domain",
        forbidden_import_prefixes=(
            "dayboard.app",
            *DAYBOARD_OUTER_LAYERS,
            *FRAMEWORK_IMPORTS,
        ),
    ),
    LayerRule(
        name="dayboard.app",
        source_root=DAYBOARD_ROOT / "app",
        forbidden_import_prefixes=(
            *DAYBOARD_OUTER_LAYERS,
            *FRAMEWORK_IMPORTS,
        ),
    ),
    LayerRule(
        name="dayboard.agent_run_execution",
        source_root=DAYBOARD_ROOT / "agent",
        forbidden_import_prefixes=(
            "dayboard.api",
            "dayboard.composition",
            "dayboard.db",
            "dayboard.config",
            "fastapi",
            "sqlalchemy",
        ),
        included_relative_paths=(
            "run_execution.py",
            "run_result_projection.py",
        ),
    ),
)


def imported_modules(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append((node.lineno, node.module))
    return modules


def find_violations(rule: LayerRule) -> list[Violation]:
    if not rule.source_root.is_dir():
        raise FileNotFoundError(f"architecture source root is missing: {rule.source_root}")

    paths = (
        [rule.source_root / relative_path for relative_path in rule.included_relative_paths]
        if rule.included_relative_paths
        else list(rule.source_root.rglob("*.py"))
    )
    missing_paths = [path for path in paths if not path.is_file()]
    if missing_paths:
        missing = ", ".join(str(path) for path in missing_paths)
        raise FileNotFoundError(f"architecture source file is missing: {missing}")

    violations: list[Violation] = []
    for path in sorted(paths):
        for line, imported_module in imported_modules(path):
            if any(
                imported_module == prefix or imported_module.startswith(f"{prefix}.")
                for prefix in rule.forbidden_import_prefixes
            ):
                violations.append(
                    Violation(
                        path=path,
                        line=line,
                        imported_module=imported_module,
                        layer=rule.name,
                    )
                )
    return violations


def main() -> int:
    violations = [violation for rule in RULES for violation in find_violations(rule)]
    if not violations:
        print("Architecture dependency checks passed.")
        return 0

    print("Architecture dependency checks failed:")
    for violation in violations:
        relative_path = violation.path.relative_to(REPOSITORY_ROOT)
        print(
            f"- {relative_path}:{violation.line}: {violation.layer} must not import "
            f"{violation.imported_module}"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
