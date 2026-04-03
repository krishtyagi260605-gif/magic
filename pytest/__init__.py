from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_real_pytest() -> None:
    root = Path(__file__).resolve().parents[1]
    candidates = sorted((root / ".venv" / "lib").glob("python*/site-packages/pytest/__init__.py"))
    if not candidates:
        raise ModuleNotFoundError("Real pytest is not installed in the project .venv")

    init_py = candidates[0]
    site_packages = str(init_py.parents[1])
    if site_packages not in sys.path:
        sys.path.insert(0, site_packages)

    spec = importlib.util.spec_from_file_location(
        __name__,
        init_py,
        submodule_search_locations=[str(init_py.parent)],
    )
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"Could not load pytest from {init_py}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[__name__] = module
    spec.loader.exec_module(module)
    globals().update(module.__dict__)


_load_real_pytest()
