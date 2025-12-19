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
