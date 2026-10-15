import shutil
from pathlib import Path

import pytest

from taxadvisor.config import Settings

ROOT = Path(__file__).resolve().parent.parent
FAKE_CLAUDE = Path(__file__).resolve().parent / "fake_claude.py"


@pytest.fixture
def advisor_dir(tmp_path: Path) -> Path:
    """A throwaway copy of the advisor workspace (without synced law data)."""
    dst = tmp_path / "advisor"
    shutil.copytree(ROOT / "advisor", dst, ignore=shutil.ignore_patterns("manifest.json", "versions", "diffs", "current.md"))
    return dst


@pytest.fixture
def settings(tmp_path: Path, advisor_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    log = tmp_path / "claude_calls.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    return Settings(
        advisor_dir=advisor_dir,
        data_dir=tmp_path / "data",
        web_dir=ROOT / "web",
        claude_bin=str(FAKE_CLAUDE),
        law_sync_interval_hours=0,
        law_news_interval_days=0,
    )
