from __future__ import annotations

import sys
from pathlib import Path


def _add_project_venv_site_packages() -> None:
    root = Path(__file__).resolve().parent
    venv_lib = root / ".venv" / "lib"
    if not venv_lib.is_dir():
        return
    for python_dir in sorted(venv_lib.glob("python*/site-packages")):
        path = str(python_dir)
        if path not in sys.path:
            sys.path.insert(0, path)


_add_project_venv_site_packages()
