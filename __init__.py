"""Recycle Bin plugin (Picard 3 plugin system).

Adds a file context action to send the currently selected files to the
OS recycle bin / trash.

Windows uses the native Shell API (allow-undo delete).
macOS moves files into ~/.Trash.
Linux / other Unix tries the freedesktop.org Trash spec.
"""
from picard.plugin3.api import BaseAction, PluginApi

import ctypes
import datetime as _dt
import os
import shutil
import sys
import urllib.parse


CONFIRM_TRASH_SETTING_KEY = "confirm_trash"


def _confirm_send_to_trash(api: PluginApi, parent, count: int) -> bool:
	api.plugin_config.register_option(CONFIRM_TRASH_SETTING_KEY, True)
	if not api.plugin_config[CONFIRM_TRASH_SETTING_KEY]:
		return True
	try:
		from PyQt6.QtWidgets import QCheckBox, QMessageBox
	except Exception:
		return True

	box = QMessageBox(parent)
	box.setIcon(QMessageBox.Icon.Warning)
	box.setWindowTitle("Send to Recycle Bin")
	box.setText(f"Send {count} selected file(s) to the Recycle Bin?")
	box.setInformativeText("This can usually be undone from the OS Recycle Bin / Trash.")
	box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
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
	op = _WinSHFILEOPSTRUCTW()
	op.hwnd = None
	op.wFunc = FO_DELETE
	op.pFrom = from_buf
	op.pTo = None
	op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
	op.fAnyOperationsAborted = 0

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
	paths = []
	for obj in objs or []:
		p = getattr(obj, "filename", None)
		if p:
			paths.append(p)
	return paths


class SendToRecycleBinAction(BaseAction):
	# Picard v3 menu label is derived from BaseAction.display_title(), which
	# prefers TITLE (falling back to NAME). BaseAction defines TITLE="Unknown",
	# so plugins must override TITLE to avoid the default.
	TITLE = "Send to Recycle Bin"
	NAME = "Send to Recycle Bin"

	def callback(self, objs):
		paths = _extract_file_paths(objs)
		if not paths:
			self.api.logger.debug("Recycle Bin: no file paths in selection")
			return

		count = len(paths)
		if not _confirm_send_to_trash(self.api, self.parent() or None, count):
			self.api.logger.debug("Recycle Bin: user cancelled")
			return

		ok, failed = send_paths_to_trash(paths)
		self.api.logger.info("Recycle Bin: sent %d file(s) to trash", len(ok))
		if failed:
			self.api.logger.error("Recycle Bin: failed to trash %d file(s)", len(failed))

		# Best-effort: remove files from Picard UI if supported.
		for obj in objs or []:
			try:
				if getattr(obj, "filename", None) in ok and hasattr(obj, "remove"):
					obj.remove()
			except Exception:
				pass


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
