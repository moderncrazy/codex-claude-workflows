#!/usr/bin/env python3

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "shared/claude-permission-broker.md"
TARGETS = (
    ROOT
    / "skills/superpowers-claude-workflow/references/claude-permission-broker.md",
    ROOT / "skills/matt-claude-workflow/references/claude-permission-broker.md",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync shared agent references into standalone Skill packages."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when a packaged hard copy differs from the shared source",
    )
    args = parser.parse_args()
    source = SOURCE.read_text()

    stale = [target for target in TARGETS if not target.exists() or target.read_text() != source]
    if args.check:
        for target in stale:
            print(f"stale: {target.relative_to(ROOT)}")
        return 1 if stale else 0

    for target in TARGETS:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
