# Recycle Bin (MusicBrainz Picard plugin)

Adds a Picard file action that sends the currently selected files to the OS recycle bin / trash (instead of permanently deleting them).

- Plugin name: Recycle Bin
- Plugin version: 0.1.3
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
