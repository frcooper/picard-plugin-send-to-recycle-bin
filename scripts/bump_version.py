#!/usr/bin/env python3
"""Bump Picard plugin version across files.

Updates:
- MANIFEST.toml: version = "X.Y.Z"
- README.md: "- Plugin version: X.Y.Z"

Optionally:
- commits the change
- creates an annotated git tag vX.Y.Z
- pushes commit + tag

Designed for plugin maintainers working in a git clone.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "MANIFEST.toml"
README_PATH = REPO_ROOT / "README.md"


_VERSION_RE = re.compile(r'^(?P<key>version)\s*=\s*"(?P<version>[^"]+)"\s*$', re.MULTILINE)
_README_VERSION_RE = re.compile(r'^(?P<prefix>-\s+Plugin version:)\s*(?P<version>\S+)\s*$', re.MULTILINE)
_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _run(cmd: list[str], *, cwd: Path = REPO_ROOT) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout}{proc.stderr}"
        )
    return proc.stdout.strip()


def _require_clean_worktree() -> None:
    out = _run(["git", "status", "--porcelain=v1"])  # empty when clean
    if out:
        raise RuntimeError(
            "Working tree is not clean. Commit/stash changes before bumping.\n"
            + out
        )


def _parse_manifest_version(text: str) -> str:
    m = _VERSION_RE.search(text)
    if not m:
        raise RuntimeError("Could not find version in MANIFEST.toml")
    return m.group("version")


def _bump_semver(version: str, bump: str) -> str:
    if not _SEMVER_RE.match(version):
        raise RuntimeError(f"Current version is not simple semver (X.Y.Z): {version}")
    major_s, minor_s, patch_s = version.split(".")
    major, minor, patch = int(major_s), int(minor_s), int(patch_s)

    if bump == "patch":
        patch += 1
    elif bump == "minor":
        minor += 1
        patch = 0
    elif bump == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise RuntimeError(f"Unknown bump kind: {bump}")

    return f"{major}.{minor}.{patch}"


def _replace_once(pattern: re.Pattern[str], text: str, repl: str, *, what: str) -> str:
    new_text, count = pattern.subn(repl, text, count=1)
    if count != 1:
        raise RuntimeError(f"Expected to update 1 occurrence for {what}, updated {count}")
    return new_text


def bump_version(new_version: str) -> None:
    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    readme_text = README_PATH.read_text(encoding="utf-8")

    current = _parse_manifest_version(manifest_text)
    if current == new_version:
        raise RuntimeError(f"Version is already {new_version}")

    manifest_text = _replace_once(
        _VERSION_RE,
        manifest_text,
        f'version = "{new_version}"',
        what="MANIFEST.toml version",
    )

    readme_text = _replace_once(
        _README_VERSION_RE,
        readme_text,
        f"- Plugin version: {new_version}",
        what="README.md plugin version",
    )

    MANIFEST_PATH.write_text(manifest_text, encoding="utf-8")
    README_PATH.write_text(readme_text, encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--new-version", help="Set version explicitly (X.Y.Z)")
    group.add_argument(
        "--bump",
        choices=["patch", "minor", "major"],
        help="Bump current version by semver component",
    )

    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Do not create a git commit",
    )
    parser.add_argument(
        "--no-tag",
        action="store_true",
        help="Do not create a git tag",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Do not push commit/tag",
    )
    parser.add_argument(
        "--message",
        default=None,
        help='Commit message (default: "Bump version to X.Y.Z")',
    )
    parser.add_argument(
        "--tag-prefix",
        default="v",
        help='Tag prefix (default: "v" => vX.Y.Z)',
    )
    parser.add_argument(
        "--remote",
        default="origin",
        help='Git remote (default: "origin")',
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Branch to push (default: current branch)",
    )

    args = parser.parse_args(argv)

    _require_clean_worktree()

    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    current = _parse_manifest_version(manifest_text)

    if args.new_version:
        new_version = args.new_version.strip()
        if not _SEMVER_RE.match(new_version):
            raise RuntimeError(f"--new-version must be X.Y.Z, got {new_version}")
    else:
        new_version = _bump_semver(current, args.bump)

    bump_version(new_version)

    commit_msg = args.message or f"Bump version to {new_version}"
    tag_name = f"{args.tag_prefix}{new_version}"

    if not args.no_commit:
        _run(["git", "add", str(MANIFEST_PATH), str(README_PATH)])
        _run(["git", "commit", "-m", commit_msg])

    if not args.no_tag:
        _run(["git", "tag", "-a", tag_name, "-m", tag_name])

    if not args.no_push:
        branch = args.branch or _run(["git", "branch", "--show-current"])
        if not branch:
            raise RuntimeError("Could not determine current branch; pass --branch")
        _run(["git", "push", args.remote, branch])
        if not args.no_tag:
            _run(["git", "push", args.remote, tag_name])

    print(f"Updated version: {current} -> {new_version}")
    if not args.no_tag:
        print(f"Tag: {tag_name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1) from e
