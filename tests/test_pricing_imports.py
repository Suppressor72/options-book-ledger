from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PURE_ROOTS = (
    REPO_ROOT / "optledger" / "pricing",
    REPO_ROOT / "optledger" / "book",
    REPO_ROOT / "optledger" / "metrics",
)

FORBIDDEN_PREFIXES = (
    "optledger.cli",
    "optledger.web",
    "optledger.data",
    "optledger.ledger",
    "optledger.simulate",
    "matplotlib",
    "pandas",
    "numpy",
    "vollib",
    "py_vollib",
    "QuantLib",
    "quantlib",
    "duckdb",
    "quantstats",
    "streamlit",
)


def _imported_modules(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_pure_layers_do_not_import_product_or_extra_layers() -> None:
    offenders: list[str] = []
    for root in PURE_ROOTS:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for module in _imported_modules(tree):
                if any(
                    module == prefix or module.startswith(prefix + ".")
                    for prefix in FORBIDDEN_PREFIXES
                ):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {module}")
    assert offenders == []
