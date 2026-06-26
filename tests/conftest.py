"""Shared pytest fixtures and configuration."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest

# Ensure project root is on sys.path so `import src...` works from any cwd.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(_ROOT))


# ── Environment defaults for tests ───────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Set fake API keys for any module that calls load_dotenv() at import-time.

    Tests that explicitly need missing keys should clear them via monkeypatch.delenv().
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://test.deepseek.example/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "test-deepseek-model")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-minimax-key")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://test.minimax.example/v1")
    monkeypatch.setenv("MINIMAX_MODEL", "test-minimax-model")
    yield


# ── Fixture file paths ───────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_oh_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_oh.xlsx"


@pytest.fixture
def sample_der_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_der.xlsx"


@pytest.fixture
def sample_pn_tree_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_pn_tree.json"


@pytest.fixture
def sample_voice_input_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample-voice-inputs.md"
