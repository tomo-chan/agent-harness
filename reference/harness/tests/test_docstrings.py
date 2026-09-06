"""Regression checks for reference-implementation docstring requirements."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_DIRS = (
    ROOT / "reference" / "hooks",
    ROOT / "reference" / "harness",
    ROOT / "reference" / "posture",
    ROOT / "reference" / "launcher",
)


def _production_python_files() -> list[Path]:
    """Return production Python files while excluding test packages."""
    files: list[Path] = []
    for directory in PRODUCTION_DIRS:
        files.extend(
            path
            for path in directory.rglob("*.py")
            if "tests" not in path.relative_to(ROOT).parts
        )
    return sorted(files)


def _missing_docstrings(path: Path) -> list[str]:
    """Return missing module, top-level function, class, and method docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    missing: list[str] = []
    if ast.get_docstring(tree) is None:
        missing.append("module")

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node) is None:
                missing.append(node.name)
        elif isinstance(node, ast.ClassDef):
            if ast.get_docstring(node) is None:
                missing.append(node.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if ast.get_docstring(item) is None:
                        missing.append(f"{node.name}.{item.name}")
    return missing


def test_reference_python_code_has_docstrings():
    """Require reviewable contracts on all production Python modules and callables."""
    failures: list[str] = []
    for path in _production_python_files():
        for symbol in _missing_docstrings(path):
            failures.append(f"{path.relative_to(ROOT)}: {symbol}")
    assert not failures, "missing docstrings:\n" + "\n".join(failures)
