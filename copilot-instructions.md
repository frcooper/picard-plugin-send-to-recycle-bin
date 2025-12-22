# Copilot instructions for Recycle Bin

Context: This folder contains the `Recycle Bin` plugin (`recycle-bin.py`). It adds a Picard file action that sends the selected files to the OS recycle bin / trash.

Key behaviors
- Provide a file context action labeled "Send to Recycle Bin".
- Operate only on selected File items (objects exposing a `filename`).
- Confirm before trashing, then move files to the OS trash in an undoable way when possible.

Implementation notes
- No external dependencies.
- Prefer platform-specific implementations:
  - Windows: native Shell API delete with allow-undo.
  - macOS: move to `~/.Trash`.
  - Linux/Unix: freedesktop.org Trash spec (`~/.local/share/Trash`).
- Log via `log.debug/info/error` with the "Recycle Bin:" prefix.

Config & UI
- No options page.
- Stores a single user preference to allow opting out of future delete warnings (`recycle_bin_confirm_trash`).
- Do not register an options page.
- Do not expose Reset / Self-Uninstall actions.

Testing tips
- Add unit-style tests under `tests/` focusing on path handling and platform selection (avoid requiring a real GUI).

Dev environment invariants (keep these maintained)
- This plugin is developed against a local Picard source checkout at `f:/repos/picard`.
- Import resolution MUST work during development (no suppressing missing-import errors for Picard).
- The repository uses:
  - `pyrightconfig.json` with `extraPaths: ["f:/repos/picard"]`.
  - `.vscode/settings.json` with `python.analysis.extraPaths` pointing at `f:/repos/picard`.
  - A local `.env` (ignored by git) setting `PYTHONPATH=f:/repos/picard`.

Maintaining dev config
- If Picard imports start failing, prefer fixing the dev environment (dependencies / PYTHONPATH) rather than muting diagnostics.
- Keep `requirements-dev.txt` up to date with the minimum packages required for `import picard.plugin3.api` to succeed in the plugin venv.
- When updating imports or Picard API usage, ensure Pylance/Pyright still resolves Picard types via the local checkout.

Release/versioning rules
- When asked whether changes warrant a point release, evaluate everything since the last git tag (e.g., `git log <tag>..HEAD` and `git diff --name-status <tag>..HEAD`), not just the latest commit.
- Base the recommendation on user-facing behavior changes vs dev-only changes, and ensure `MANIFEST.toml` + `README.md` stay in sync when bumping versions.
