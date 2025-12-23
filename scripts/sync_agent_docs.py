#!/usr/bin/env python3
"""Sync derived agent instruction files from AGENTS.md.

Canonical source: AGENTS.md in repo root.

Generated targets:
- .github/copilot-instructions.md
- GEMINI.md
- .gemini/styleguide.md

Usage:
  python scripts/sync_agent_docs.py --write   # rewrite generated files
  python scripts/sync_agent_docs.py --check   # fail if out of date (default)

Also enforces: README.md must not be older than AGENTS.md (by git commit time).
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass


BEGIN_MARKER = "<!-- BEGIN AGENT INSTRUCTIONS -->"
END_MARKER = "<!-- END AGENT INSTRUCTIONS -->"


@dataclass(frozen=True)
class GeneratedTarget:
    relpath: str


GENERATED_TARGETS: tuple[GeneratedTarget, ...] = (
    GeneratedTarget(".github/copilot-instructions.md"),
    GeneratedTarget("GEMINI.md"),
    GeneratedTarget(".gemini/styleguide.md"),
)


def _repo_root() -> pathlib.Path:
    # scripts/sync_agent_docs.py -> repo root
    return pathlib.Path(__file__).resolve().parents[1]


def _read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _extract_instructions(agents_text: str) -> str:
    agents_text = agents_text.replace("\r\n", "\n").replace("\r", "\n")
    begin = agents_text.find(BEGIN_MARKER)
    end = agents_text.find(END_MARKER)
    if begin == -1 or end == -1 or end <= begin:
        raise ValueError(
            f"AGENTS.md must contain markers {BEGIN_MARKER!r} and {END_MARKER!r}"
        )

    content = agents_text[begin + len(BEGIN_MARKER) : end]
    content = content.strip("\n") + "\n"
    return content


def _run_git(args: list[str], cwd: pathlib.Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _git_commit_time_unix(path: pathlib.Path, repo_root: pathlib.Path) -> int | None:
    rel = os.fspath(path.relative_to(repo_root)).replace("\\", "/")
    out = _run_git(["log", "-1", "--format=%ct", "--", rel], cwd=repo_root)
    if not out:
        return None
    try:
        return int(out)
    except ValueError:
        return None


def _check_readme_freshness(repo_root: pathlib.Path) -> list[str]:
    agents = repo_root / "AGENTS.md"
    readme = repo_root / "README.md"

    if not agents.exists() or not readme.exists():
        return []

    if not (repo_root / ".git").exists():
        # In non-git contexts, skip (CI should have .git).
        return []

    agents_ct = _git_commit_time_unix(agents, repo_root)
    readme_ct = _git_commit_time_unix(readme, repo_root)

    if agents_ct is None or readme_ct is None:
        return []

    if readme_ct < agents_ct:
        return [
            "README.md is older than AGENTS.md (by last git commit time). "
            "Update README.md or amend commits so it is at least as new as AGENTS.md."
        ]

    return []


def _check_or_write(repo_root: pathlib.Path, write: bool) -> int:
    errors: list[str] = []

    agents_path = repo_root / "AGENTS.md"
    if not agents_path.exists():
        return 0

    agents_text = _read_text(agents_path)
    try:
        instructions = _extract_instructions(agents_text)
    except ValueError as exc:
        print(f"sync_agent_docs: {exc}", file=sys.stderr)
        return 2

    for target in GENERATED_TARGETS:
        out_path = repo_root / target.relpath
        if write:
            _write_text(out_path, instructions)
        else:
            if not out_path.exists():
                errors.append(f"Missing generated file: {target.relpath}")
                continue
            current = _read_text(out_path).replace("\r\n", "\n")
            if current != instructions:
                errors.append(f"Generated file out of date: {target.relpath}")

    errors.extend(_check_readme_freshness(repo_root))

    if errors:
        for msg in errors:
            print(f"sync_agent_docs: {msg}", file=sys.stderr)
        if not write:
            print(
                "sync_agent_docs: Run `python scripts/sync_agent_docs.py --write` and commit the results.",
                file=sys.stderr,
            )
        return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Rewrite generated files")
    mode.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated files do not match AGENTS.md (default)",
    )

    args = parser.parse_args()
    repo_root = _repo_root()

    write = bool(args.write)
    return _check_or_write(repo_root, write=write)


if __name__ == "__main__":
    raise SystemExit(main())
