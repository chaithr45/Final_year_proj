"""Run bookkeeping (Section 10.3) and the test-set guard (Section 10.4).

Every run writes results/runs/<id>/ with its config, git commit, seed and metrics,
and never overwrites another run. Any code path that touches test patients
(sub-097..sub-125) must pass through `require_test_access`, which refuses unless
the caller explicitly opted in, and records that it happened.
"""
from __future__ import annotations

import datetime as _dt
import json
import subprocess
from pathlib import Path

import yaml

from ..data.split import official_test_subjects, official_train_subjects

REPO = Path(__file__).resolve().parents[2]


def git_state() -> dict:
    def run(*a):
        try:
            return subprocess.check_output(["git", *a], cwd=REPO, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return "unknown"
    return {"commit": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain", "--untracked-files=no"))}


def resolve_subjects(spec) -> list[str]:
    if spec == "official_train":
        return official_train_subjects()
    if spec == "official_test":
        return official_test_subjects()
    return list(spec)


def touches_test(subjects: list[str]) -> bool:
    return bool(set(subjects) & set(official_test_subjects()))


def require_test_access(subjects: list[str], allowed: bool, reason: str = "") -> None:
    if touches_test(subjects) and not allowed:
        raise PermissionError(
            "These subjects include official TEST patients (sub-097..sub-125). Test patients are scored "
            "once per final model (M6), or for the published-baseline reproduction (M2). "
            "Re-run with --final-test if that is what you are doing.")


def new_run_dir(name: str, config: dict, seed: int, root: Path | None = None) -> Path:
    root = root or REPO / "results" / "runs"
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = root / f"{stamp}_{name}_s{seed}"
    i = 1
    while d.exists():
        d = root / f"{stamp}_{name}_s{seed}_{i}"
        i += 1
    d.mkdir(parents=True)
    # ignored by git until mark_complete(): unfinished runs never show up as uncommitted changes
    (d / ".gitignore").write_text("# run in progress; removed by mark_complete()\n*\n")
    (d / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    (d / "run.json").write_text(json.dumps({"name": name, "seed": seed, "git": git_state(),
                                            "created": stamp}, indent=2) + "\n")
    return d


def mark_complete(run_dir: Path) -> None:
    """Make a finished run visible to git (removes the in-progress .gitignore)."""
    (Path(run_dir) / ".gitignore").unlink(missing_ok=True)


def log_test_access(run_dir: Path, reason: str) -> None:
    with open(run_dir / "TEST_ACCESS.log", "a") as fh:
        fh.write(f"{_dt.datetime.now().isoformat()} {reason}\n")
