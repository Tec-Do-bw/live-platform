from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SERVICE_DIR = Path(__file__).resolve().parents[1]
LOCAL_UTILS_DIR = (SERVICE_DIR / "utils").resolve()


@pytest.mark.parametrize(
    "module_name",
    [
        "utils.TiktokTool",
        "utils.ShopeeTool",
        "utils.LazadaTool",
        "utils.downloader",
    ],
)
def test_legacy_utils_resolve_to_local_package(module_name: str):
    spec = importlib.util.find_spec(module_name)

    assert spec is not None
    assert spec.origin is not None
    assert Path(spec.origin).resolve().is_relative_to(LOCAL_UTILS_DIR)
