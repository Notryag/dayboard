#!/usr/bin/env python3
"""Fail when a lower application layer imports a higher product layer."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class LayerRule:
    name: str
    source_root: Path
    forbidden_import_roots: tuple[str, ...]


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    imported_module: str
    layer: str


RULES = (
    LayerRule(
        name="agent_platform",
        source_root=REPOSITORY_ROOT
        / "packages"
        / "agent-platform"
        / "src"
        / "agent_platform",
        forbidden_import_roots=("dayboard",),
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

    violations: list[Violation] = []
    for path in sorted(rule.source_root.rglob("*.py")):
        for line, imported_module in imported_modules(path):
            import_root = imported_module.partition(".")[0]
            if import_root in rule.forbidden_import_roots:
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
