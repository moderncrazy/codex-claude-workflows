#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("superpowers-claude-workflow", "matt-claude-workflow")
BROKER_SOURCE = ROOT / "shared/claude-permission-broker.md"
RUNNER_SOURCE = ROOT / "shared/claude-runner"


def source_files(root: Path) -> dict[Path, Path]:
    return {
        path.relative_to(root): path
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
    }


def differences(source: Path, target: Path) -> list[str]:
    expected = source_files(source)
    actual = source_files(target) if target.exists() else {}
    issues: list[str] = []
    if target.is_symlink():
        issues.append(f"symlink: {target.relative_to(ROOT)}")
    for relative, source_path in expected.items():
        target_path = target / relative
        if not target_path.exists():
            issues.append(f"missing: {target_path.relative_to(ROOT)}")
        elif target_path.is_symlink():
            issues.append(f"symlink: {target_path.relative_to(ROOT)}")
        elif target_path.read_bytes() != source_path.read_bytes():
            issues.append(f"stale: {target_path.relative_to(ROOT)}")
        elif (target_path.stat().st_mode & 0o111) != (source_path.stat().st_mode & 0o111):
            issues.append(f"mode: {target_path.relative_to(ROOT)}")
    for relative in sorted(set(actual) - set(expected)):
        issues.append(f"extra: {(target / relative).relative_to(ROOT)}")
    return issues


def sync_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    expected = source_files(source)
    for path in sorted(target.rglob("*"), reverse=True):
        if path.is_symlink() or (path.is_file() and path.relative_to(target) not in expected):
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    for relative, source_path in expected.items():
        target_path = target / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
        os.chmod(target_path, source_path.stat().st_mode & 0o777)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync shared assets into standalone Skill packages.")
    parser.add_argument("--check", action="store_true", help="report differences without writing")
    args = parser.parse_args()
    issues: list[str] = []
    for skill in SKILLS:
        skill_root = ROOT / "skills" / skill
        broker_target = skill_root / "references/claude-permission-broker.md"
        runner_target = skill_root / "scripts/claude-runner"
        if not broker_target.exists() or broker_target.read_bytes() != BROKER_SOURCE.read_bytes():
            issues.append(f"stale: {broker_target.relative_to(ROOT)}")
        issues.extend(differences(RUNNER_SOURCE, runner_target))
        if not args.check:
            broker_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(BROKER_SOURCE, broker_target)
            sync_tree(RUNNER_SOURCE, runner_target)
    if args.check:
        for issue in issues:
            print(issue)
        return 1 if issues else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

