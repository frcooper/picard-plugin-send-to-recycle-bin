# Recycle Bin (MusicBrainz Picard plugin)

Adds a Picard file action that sends the currently selected files to the OS recycle bin / trash (instead of permanently deleting them).

- Plugin name: Recycle Bin
- Plugin version: 0.1.5
- Picard plugin API: 3.0

## What it does

After installing and enabling the plugin, Picard’s file context menu includes an action labeled **Send to Recycle Bin**.

When invoked, the plugin:

- Collects file paths from the current selection (items that expose a `filename`).
- Prompts for confirmation (once per user, unless re-enabled).
- Moves the files to your OS’s recycle bin / trash in an undoable way when possible.

## Platform behavior

- Windows: Uses the native Shell API (allow-undo delete into Recycle Bin).
- macOS: Moves files into ~/.Trash.
- Linux / other Unix: Uses the freedesktop.org Trash spec under ~/.local/share/Trash.

## Confirmation prompt

By default, the plugin shows a confirmation dialog before trashing files. You can tick “Don’t show this warning again” to disable future prompts.

## Usage

1. In Picard, select one or more files.
2. Open the context menu.
3. Choose **Send to Recycle Bin**.

## Troubleshooting

- If nothing happens, ensure your selection contains File items (items with a `filename`).
- If some files fail to trash, check Picard’s log for entries prefixed with “Recycle Bin:”.

## License

GPL-3.0-or-later. See the license reference in MANIFEST.toml.

## Releasing

This repository uses tags to publish releases. Creating a tag `vX.Y.Z` triggers a GitHub Action that creates a GitHub Release with notes listing all commits since the previous tag.

To bump the version (updates MANIFEST.toml and this README), commit, tag, and push:

- `python scripts/bump_version.py --bump patch`

Or set an explicit version:

- `python scripts/bump_version.py --new-version 0.1.4`
- `python scripts/bump_version.py --new-version 0.1.5`

## Developer notes

- `AGENTS.md` is the canonical source for agent instructions.
- Generated files: `.github/copilot-instructions.md`, `GEMINI.md`, `.gemini/styleguide.md`.
- Regenerate: `python scripts/sync_agent_docs.py --write`.
