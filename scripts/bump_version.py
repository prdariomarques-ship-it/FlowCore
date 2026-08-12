#!/usr/bin/env python3
"""FlowCore — SemVer version bump tool.

Usage:
    python3 scripts/bump_version.py major
    python3 scripts/bump_version.py minor
    python3 scripts/bump_version.py patch
    python3 scripts/bump_version.py set 1.2.0
    python3 scripts/bump_version.py show

Updates VERSION file, config/default.yml, and appends to CHANGELOG.md.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
CONFIG_FILE = ROOT / "config" / "default.yml"
CHANGELOG_FILE = ROOT / "CHANGELOG.md"


def read_version() -> tuple[int, int, int]:
    """Read the current version from VERSION file."""
    text = VERSION_FILE.read_text().strip()
    parts = text.split(".")
    return int(parts[0]), int(parts[1]), int(parts[2])


def write_version(major: int, minor: int, patch: int) -> str:
    """Write new version to VERSION and config/default.yml."""
    version_str = f"{major}.{minor}.{patch}"
    VERSION_FILE.write_text(f"{version_str}\n")

    # Update config/default.yml
    config = CONFIG_FILE.read_text()
    config = re.sub(
        r'version:\s*"[^"]*"',
        f'version: "{version_str}"',
        config,
    )
    CONFIG_FILE.write_text(config)

    return version_str


def update_changelog_header(version: str) -> None:
    """Append a new version section header to CHANGELOG.md."""
    today = Path().cwd()  # not used; we use fixed format
    import datetime
    today_str = datetime.date.today().isoformat()

    changelog = CHANGELOG_FILE.read_text()

    # Check if this version already has a section
    if f"[{version}]" in changelog:
        print(f"  CHANGELOG: version {version} already exists, skipping")
        return

    new_section = f"\n## [{version}] — {today_str}\n\n### Added\n\n- \n\n### Fixed\n\n- \n\n### Changed\n\n- \n"

    # Insert after the header section (after the two description lines)
    lines = changelog.split("\n")
    # Find the last line of the header (the blank line before the first version)
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("## ["):
            insert_idx = i
            break

    lines.insert(insert_idx, new_section.strip())
    CHANGELOG_FILE.write_text("\n".join(lines) + "\n")


def cmd_show() -> None:
    major, minor, patch = read_version()
    print(f"{major}.{minor}.{patch}")


def cmd_bump(bump_type: str) -> None:
    major, minor, patch = read_version()

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1
    else:
        print(f"Unknown bump type: {bump_type}", file=sys.stderr)
        sys.exit(1)

    new_version = write_version(major, minor, patch)
    update_changelog_header(new_version)
    print(f"Version bumped: {read_version_formatted()} -> {new_version}")
    print(f"  VERSION:      updated")
    print(f"  config:       updated")
    print(f"  CHANGELOG.md: new section added")


def read_version_formatted() -> str:
    major, minor, patch = read_version()
    return f"{major}.{minor}.{patch}"


def cmd_set(version_str: str) -> None:
    """Set an explicit version."""
    parts = version_str.split(".")
    if len(parts) != 3:
        print(f"Invalid version format: {version_str} (expected X.Y.Z)", file=sys.stderr)
        sys.exit(1)

    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    old = read_version_formatted()
    new = write_version(major, minor, patch)
    update_changelog_header(new)
    print(f"Version set: {old} -> {new}")


def main() -> None:
    parser = argparse.ArgumentParser(description="FlowCore SemVer version manager")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("show", help="Show current version")
    sub.add_parser("major", help="Bump major version (1.0.0 -> 2.0.0)")
    sub.add_parser("minor", help="Bump minor version (1.0.0 -> 1.1.0)")
    sub.add_parser("patch", help="Bump patch version (1.0.0 -> 1.0.1)")

    set_parser = sub.add_parser("set", help="Set explicit version")
    set_parser.add_argument("version", help="Version string (e.g., 1.2.0)")

    args = parser.parse_args()

    if args.command == "show":
        cmd_show()
    elif args.command in ("major", "minor", "patch"):
        cmd_bump(args.command)
    elif args.command == "set":
        cmd_set(args.version)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
