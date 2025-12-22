"""Recycle Bin plugin (Picard 3 plugin system).

Adds a file context action to send the currently selected files to the
OS recycle bin / trash.

Windows uses the native Shell API (allow-undo delete).
macOS moves files into ~/.Trash.
Linux / other Unix tries the freedesktop.org Trash spec.
"""

import ctypes
import datetime as _dt
import os
import shutil
import sys
import urllib.parse
from collections.abc import Iterable

from picard.plugin3.api import BaseAction, PluginApi


CONFIRM_TRASH_SETTING_KEY = "confirm_trash"


def _confirm_send_to_trash(api: PluginApi, parent, count: int) -> bool:
    api.plugin_config.register_option(CONFIRM_TRASH_SETTING_KEY, True)
    if not api.plugin_config[CONFIRM_TRASH_SETTING_KEY]:
        return True
    try:
        import importlib

        qtwidgets = importlib.import_module("PyQt6.QtWidgets")
        QCheckBox = qtwidgets.QCheckBox
        QMessageBox = qtwidgets.QMessageBox
    except Exception:
        return True

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Send to Recycle Bin")
    box.setText(f"Send {count} selected file(s) to the Recycle Bin?")
    box.setInformativeText("This can usually be undone from the OS Recycle Bin / Trash.")
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    box.setDefaultButton(QMessageBox.StandardButton.No)

    checkbox = QCheckBox("Don't show this warning again")
    box.setCheckBox(checkbox)
    choice = box.exec()
    confirmed = choice == QMessageBox.StandardButton.Yes
    if confirmed and checkbox.isChecked():
        api.plugin_config[CONFIRM_TRASH_SETTING_KEY] = False
        api.logger.debug("Recycle Bin: user disabled future confirmation prompts")
    return confirmed


class _WinSHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", ctypes.c_int),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", ctypes.c_wchar_p),
    ]


def _trash_windows(paths):
    FO_DELETE = 0x0003
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_SILENT = 0x0004
    FOF_NOERRORUI = 0x0400

    existing = [p for p in paths if p and os.path.exists(p)]
    if not existing:
        return [], paths

    # Double-null terminated list of files
    from_buf = "\0".join(existing) + "\0\0"
    flags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    op = _WinSHFILEOPSTRUCTW(
        None,
        FO_DELETE,
        from_buf,
        None,
        flags,
        0,
        None,
        None,
    )

    ret = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if ret != 0 or op.fAnyOperationsAborted:
        return [], existing
    return existing, []


def _unique_dest_path(dest_dir, base_name):
    candidate = os.path.join(dest_dir, base_name)
    if not os.path.exists(candidate):
        return candidate
    root, ext = os.path.splitext(base_name)
    for i in range(1, 10_000):
        candidate = os.path.join(dest_dir, f"{root}.{i}{ext}")
        if not os.path.exists(candidate):
            return candidate
    raise RuntimeError("Unable to find free destination name")


def _trash_macos(paths, home_dir=None):
    home_dir = home_dir or os.path.expanduser("~")
    trash_dir = os.path.join(home_dir, ".Trash")
    os.makedirs(trash_dir, exist_ok=True)
    ok, failed = [], []
    for p in paths:
        try:
            if not p or not os.path.exists(p):
                failed.append(p)
                continue
            dest = _unique_dest_path(trash_dir, os.path.basename(p))
            shutil.move(p, dest)
            ok.append(p)
        except Exception:
            failed.append(p)
    return ok, failed


def _trash_freedesktop(paths, home_dir=None, now=None):
    home_dir = home_dir or os.path.expanduser("~")
    trash_root = os.path.join(home_dir, ".local", "share", "Trash")
    files_dir = os.path.join(trash_root, "files")
    info_dir = os.path.join(trash_root, "info")
    os.makedirs(files_dir, exist_ok=True)
    os.makedirs(info_dir, exist_ok=True)

    now = now or _dt.datetime.now(_dt.timezone.utc)
    stamp = now.astimezone().strftime("%Y-%m-%dT%H:%M:%S")

    ok, failed = [], []
    for p in paths:
        try:
            if not p or not os.path.exists(p):
                failed.append(p)
                continue
            base = os.path.basename(p)
            dest = _unique_dest_path(files_dir, base)
            shutil.move(p, dest)
            info_name = os.path.basename(dest) + ".trashinfo"
            info_path = os.path.join(info_dir, info_name)
            abs_path = os.path.abspath(p)
            encoded = urllib.parse.quote(abs_path)
            with open(info_path, "w", encoding="utf-8") as f:
                f.write("[Trash Info]\n")
                f.write(f"Path={encoded}\n")
                f.write(f"DeletionDate={stamp}\n")
            ok.append(p)
        except Exception:
            failed.append(p)
    return ok, failed


def send_paths_to_trash(paths, platform=None, home_dir=None, now=None):
    platform = platform or sys.platform
    paths = [str(p) for p in (paths or []) if p]
    if not paths:
        return [], []
    if platform.startswith("win"):
        return _trash_windows(paths)
    if platform == "darwin":
        return _trash_macos(paths, home_dir=home_dir)
    return _trash_freedesktop(paths, home_dir=home_dir, now=now)


def _extract_file_paths(objs):
    """Extract filesystem paths from Picard selection objects.

    Note: In Picard, `tagger.window.selected_objects` can include File, Track,
    Album, Cluster and other container types. Containers typically expose linked
    File objects via `iterfiles()`.
    """

    _files, paths, _debug = _extract_files_and_paths(objs)
    return paths


def _extract_files_and_paths(objs):
    """Return (files, paths, debug_info) from Picard selection objects.

    - `files` are Picard File-like objects (must have `.filename`).
    - `paths` are unique file system paths.
    - `debug_info` is a list of per-object tuples (type_name, outcome, detail).
    """

    seen_paths = set()
    seen_file_ids = set()
    files = []
    paths = []
    debug_info = []

    for obj in objs or []:
        if obj is None:
            debug_info.append(("<None>", "skip", "None in selection"))
            continue
        type_name = type(obj).__name__

        def add_file_candidate(f):
            p = getattr(f, "filename", None)
            if not p:
                return 0
            added = 0
            if p not in seen_paths:
                seen_paths.add(p)
                paths.append(p)
                added = 1
            fid = id(f)
            if fid not in seen_file_ids:
                seen_file_ids.add(fid)
                files.append(f)
            return added

        # Preferred: objects that can yield linked File objects.
        iterfiles = getattr(obj, "iterfiles", None)
        if callable(iterfiles):
            try:
                count_added = 0
                try:
                    iterable = iterfiles()
                except TypeError:
                    # Some implementations require optional args.
                    iterable = iterfiles(False)
                if not isinstance(iterable, Iterable):
                    debug_info.append(
                        (type_name, "iterfiles", "not iterable")
                    )
                    continue
                for f in iterable:
                    count_added += add_file_candidate(f)
                debug_info.append((type_name, "iterfiles", f"added {count_added} path(s)"))
                continue
            except Exception as e:
                debug_info.append(
                    (type_name, "iterfiles_failed", f"{type(e).__name__}: {e}")
                )
                # fall through to other methods

        # Direct file object.
        if getattr(obj, "filename", None):
            count_added = add_file_candidate(obj)
            debug_info.append((type_name, "filename", f"added {count_added} path(s)"))
            continue

        # Containers sometimes expose linked files as `files`.
        linked = getattr(obj, "files", None)
        if linked:
            try:
                count_added = 0
                for f in linked:
                    count_added += add_file_candidate(f)
                debug_info.append((type_name, "files", f"added {count_added} path(s)"))
                continue
            except Exception as e:
                debug_info.append((type_name, "files_failed", f"{type(e).__name__}: {e}"))

        # Some wrappers might hold a single File in `file`.
        wrapped = getattr(obj, "file", None)
        if wrapped is not None and getattr(wrapped, "filename", None):
            count_added = add_file_candidate(wrapped)
            debug_info.append((type_name, "file", f"added {count_added} path(s)"))
            continue

        # Nothing matched.
        debug_info.append(
            (
                type_name,
                "unhandled",
                "no iterfiles()/filename/files/file on object",
            )
        )

    return files, paths, debug_info


class SendToRecycleBinAction(BaseAction):
    # Picard v3 menu label is derived from BaseAction.display_title(), which
    # prefers TITLE (falling back to NAME). BaseAction defines TITLE="Unknown",
    # so plugins must override TITLE to avoid the default.
    TITLE = "Send to Recycle Bin"
    NAME = "Send to Recycle Bin"

    def callback(self, objs):
        files, paths, debug_info = _extract_files_and_paths(objs)
        if not paths:
            # Make it easy to diagnose why the action can't run for a selection.
            try:
                counts_by_type = {}
                for obj in objs or []:
                    type_key = type(obj).__name__
                    counts_by_type[type_key] = counts_by_type.get(type_key, 0) + 1
            except Exception:
                counts_by_type = None
            self.api.logger.debug(
                "Recycle Bin: no file paths in selection (types=%r, details=%r)",
                counts_by_type,
                debug_info,
            )
            return

        count = len(paths)
        if not _confirm_send_to_trash(self.api, self.parent() or None, count):
            self.api.logger.debug("Recycle Bin: user cancelled")
            return

        ok, failed = send_paths_to_trash(paths)
        self.api.logger.info("Recycle Bin: sent %d file(s) to trash", len(ok))
        if failed:
            self.api.logger.error("Recycle Bin: failed to trash %d file(s)", len(failed))
            self.api.logger.debug("Recycle Bin: failed paths=%r", failed)

        # Best-effort: remove files from Picard UI.
        # This should never be silent: if we can't remove, we log why.
        ok_set = set(ok)
        files_to_remove = [f for f in files if getattr(f, "filename", None) in ok_set]
        if ok_set and not files_to_remove:
            self.api.logger.debug(
                "Recycle Bin: trashed files but couldn't map them back to File objects for UI removal (ok=%r)",
                sorted(ok_set),
            )
        elif files_to_remove:
            tagger = getattr(self, "tagger", None)
            remove_files = getattr(tagger, "remove_files", None)
            if callable(remove_files):
                try:
                    remove_files(files_to_remove)
                    self.api.logger.debug(
                        "Recycle Bin: removed %d file(s) from UI", len(files_to_remove)
                    )
                except Exception:
                    self.api.logger.warning(
                        "Recycle Bin: trashed files but failed to remove them from UI",
                        exc_info=True,
                    )
            else:
                self.api.logger.debug(
                    "Recycle Bin: trashed files but UI removal not supported (tagger has no remove_files)"
                )


def enable(api: PluginApi) -> None:
    """Picard plugin v3 entrypoint."""

    api.plugin_config.register_option(CONFIRM_TRASH_SETTING_KEY, True)
    api.register_file_action(SendToRecycleBinAction)
    version = api.manifest.version
    api.logger.info("Recycle Bin: enabled%s", f" v{version}" if version else "")


def disable() -> None:
    """Optional disable hook."""

    try:
        api = PluginApi.get_api()
        api.logger.info("Recycle Bin: disabled")
    except Exception:
        pass
