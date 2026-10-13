# backend/tests/test_no_conflict_markers.py
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # tests/ -> backend/ -> repo root

# Line-start seven-char conflict marker followed by a space or end of line.
# Built from fragments so this file never contains a marker line itself.
MARKER = re.compile(r"^(?:" + "<" * 7 + "|" + ">" * 7 + r")(?: |\r?$)", re.MULTILINE)

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".next", "out", ".pytest_cache"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pyc", ".db", ".lock", ".woff", ".woff2"}


def _candidate_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
        paths = [ROOT / line for line in out.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        paths = [p for p in ROOT.rglob("*") if not (set(p.relative_to(ROOT).parts) & SKIP_DIRS)]
    return [p for p in paths if p.suffix.lower() not in SKIP_SUFFIXES and p.is_file()]


def test_marker_regex_detects_markers():
    assert MARKER.search("<" * 7 + " HEAD\nx")
    assert MARKER.search("x\n" + ">" * 7 + " abc123\n")
    assert MARKER.search("a\r\n" + "<" * 7 + " HEAD\r\nb")
    assert MARKER.search("<" * 7 + "\n")


def test_marker_regex_ignores_non_markers():
    assert not MARKER.search("x " + "<" * 7 + " y")
    assert not MARKER.search("=" * 7 + "\n")
    assert not MARKER.search("<" * 8 + "x")


def test_no_conflict_markers():
    offenders = []
    for path in _candidate_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if MARKER.search(text):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == [], f"conflict markers found in: {offenders}"
