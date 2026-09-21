"""Phase 0 smoke tests: prove the development environment is set up correctly.

If every test here passes, four things are true:
1. The code runs on Python 3.12, the same version Google Colab uses.
2. It runs inside this project's own venv, not the system Python.
3. Every package under src/ can be imported, so the folder skeleton is correct.
4. The secrets file (.env) is ignored by Git and a template (.env.example) exists.
"""

import importlib
import sys
from pathlib import Path

import pytest

# tests/test_environment.py -> tests/ -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Every package the build plan creates under src/ (one per module).
SRC_PACKAGES = [
    "src",
    "src.data",
    "src.preprocess",
    "src.headers",
    "src.thread",
    "src.models",
    "src.claims",
    "src.verifiers",
    "src.router",
    "src.explain",
    "src.baseline",
    "src.eval",
    "src.api",
]


def test_python_version_is_3_12():
    """The interpreter must be Python 3.12 to match Colab."""
    found = sys.version.split()[0]
    assert sys.version_info[:2] == (3, 12), (
        f"Expected Python 3.12, got {found}. Is the venv activated?"
    )


def test_running_inside_project_venv():
    """The interpreter must be the one inside ./venv, not a global Python."""
    # Inside a venv, sys.prefix points at the venv folder, while
    # sys.base_prefix points at the Python the venv was created from.
    assert sys.prefix != sys.base_prefix, "Not running inside a virtual environment."
    expected = (PROJECT_ROOT / "venv").resolve()
    actual = Path(sys.prefix).resolve()
    assert actual == expected, f"Running inside {actual}, not this project's venv."


@pytest.mark.parametrize("package", SRC_PACKAGES)
def test_src_package_imports(package):
    """Each src package must be importable from the project root."""
    importlib.import_module(package)


def test_secrets_are_kept_out_of_git():
    """.env must be listed in .gitignore, and .env.example must exist."""
    ignored = (PROJECT_ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in ignored, ".env is not listed in .gitignore"
    assert (PROJECT_ROOT / ".env.example").is_file(), ".env.example is missing"
