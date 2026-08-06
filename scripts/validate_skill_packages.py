#!/usr/bin/env python3

import re
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("superpowers-claude-workflow", "matt-claude-workflow")
ALLOWED_FRONTMATTER = {
    "allowed-tools",
    "description",
    "disable-model-invocation",
    "license",
    "metadata",
    "name",
}


def frontmatter(path: Path) -> dict:
    match = re.match(r"^---\n(.*?)\n---", path.read_text(), re.DOTALL)
    if not match:
        raise ValueError(f"{path}: invalid frontmatter")
    value = yaml.safe_load(match.group(1))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: frontmatter must be a mapping")
    return value


def validate(skill_name: str) -> list[str]:
    skill_dir = ROOT / "skills" / skill_name
    data = frontmatter(skill_dir / "SKILL.md")
    errors: list[str] = []

    extra = set(data) - ALLOWED_FRONTMATTER
    if extra:
        errors.append(f"unexpected frontmatter keys: {sorted(extra)}")
    if data.get("name") != skill_name:
        errors.append("name must match its directory")
    if not isinstance(data.get("description"), str) or not data["description"].strip():
        errors.append("description must be a non-empty string")
    if data.get("disable-model-invocation") is not True:
        errors.append("disable-model-invocation must be true")

    interface = yaml.safe_load((skill_dir / "agents/openai.yaml").read_text())
    if interface.get("policy", {}).get("allow_implicit_invocation") is not False:
        errors.append("agents/openai.yaml must disable implicit invocation")
    runner = skill_dir / "scripts/claude-runner"
    required_runner_files = {
        "claude_runner.py",
        "work-unit.schema.json",
        "runner/__init__.py",
        "runner/cli.py",
        "runner/contracts.py",
        "runner/permission_hooks.py",
        "runner/progress_mcp.py",
        "runner/state_store.py",
        "runner/stream_capture.py",
        "runner/supervisor.py",
    }
    for relative in sorted(required_runner_files):
        if not (runner / relative).is_file():
            errors.append(f"missing packaged Runner asset: {relative}")
    if any(path.is_symlink() for path in skill_dir.rglob("*")):
        errors.append("Skill package must contain hard copies, not symlinks")
    entrypoint = runner / "claude_runner.py"
    if entrypoint.exists():
        if not entrypoint.stat().st_mode & 0o111:
            errors.append("packaged Runner entrypoint must be executable")
        result = subprocess.run(
            [sys.executable, str(entrypoint), "--help"],
            cwd=Path("/tmp"),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            errors.append(f"packaged Runner is not self-contained: {result.stderr.strip()}")
    return [f"{skill_name}: {error}" for error in errors]


def main() -> int:
    errors = [error for skill in SKILLS for error in validate(skill)]
    if errors:
        print("\n".join(errors))
        return 1
    print("Skill packages are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
