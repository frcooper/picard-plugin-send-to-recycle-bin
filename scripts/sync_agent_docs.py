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
import hashlib
import pathlib
import sys
from dataclasses import dataclass


BEGIN_MARKER = "<!-- BEGIN AGENT INSTRUCTIONS -->"
END_MARKER = "<!-- END AGENT INSTRUCTIONS -->"

README_STAMP_PREFIX = "<!-- sync_agent_docs: AGENTS_SHA256="
README_STAMP_SUFFIX = " -->"


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


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _extract_instructions(agents_text: str) -> str:
    agents_text = _normalize_newlines(agents_text)
    begin = agents_text.find(BEGIN_MARKER)
    end = agents_text.find(END_MARKER)
    if begin == -1 or end == -1 or end <= begin:
        raise ValueError(
            f"AGENTS.md must contain markers {BEGIN_MARKER!r} and {END_MARKER!r}"
        )

    content = agents_text[begin + len(BEGIN_MARKER) : end]
    content = content.strip("\n") + "\n"
    return content


def _agents_sha256(agents_text: str) -> str:
    normalized = _normalize_newlines(agents_text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _readme_stamp_line(sha256_hex: str) -> str:
    return f"{README_STAMP_PREFIX}{sha256_hex}{README_STAMP_SUFFIX}"


def _sync_readme_stamp(repo_root: pathlib.Path, agents_sha: str, write: bool) -> list[str]:
    readme_path = repo_root / "README.md"
    if not readme_path.exists():
        return []

    readme = _normalize_newlines(_read_text(readme_path))
    expected_line = _readme_stamp_line(agents_sha)

    # Replace existing stamp if present.
    start = readme.find(README_STAMP_PREFIX)
    if start != -1:
        end = readme.find(README_STAMP_SUFFIX, start)
        if end != -1:
            end += len(README_STAMP_SUFFIX)
            current_line = readme[start:end]
            if current_line == expected_line:
                return []
            if write:
                new_readme = readme[:start] + expected_line + readme[end:]
                _write_text(readme_path, new_readme)
                return []
            return ["README.md does not match AGENTS.md (sync stamp mismatch)."]

    # No stamp: append one at end.
    if write:
        suffix = "" if readme.endswith("\n") else "\n"
        _write_text(readme_path, readme + suffix + expected_line + "\n")
        return []
    return [
        "README.md is missing sync stamp for AGENTS.md. "
        "Run `python scripts/sync_agent_docs.py --write` and commit the result."
    ]


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

    agents_sha = _agents_sha256(agents_text)
    errors.extend(_sync_readme_stamp(repo_root, agents_sha=agents_sha, write=write))

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
