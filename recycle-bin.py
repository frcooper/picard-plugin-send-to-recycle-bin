"""Recycle Bin plugin entry point.

Adds a file context action to send the currently selected files to the
OS recycle bin / trash.

Windows uses the native Shell API (allow-undo delete).
macOS moves files into ~/.Trash.
Linux / other Unix tries the freedesktop.org Trash spec.
"""

PLUGIN_NAME = "Recycle Bin"
PLUGIN_AUTHOR = "FRC + GitHub Copilot"
PLUGIN_DESCRIPTION = "Adds an action to send selected files to the OS recycle bin/trash."
PLUGIN_VERSION = "0.1.2"
PLUGIN_API_VERSIONS = ["2.0"]
PLUGIN_LICENSE = "GPL-3.0-or-later"
PLUGIN_LICENSE_URL = "https://gnu.org/licenses/gpl.html"

from picard import config, log
from picard.config import BoolOption
from picard.extension_points.item_actions import BaseAction, register_file_action

import ctypes
import datetime as _dt
import os
import shutil
import sys
import urllib.parse


def _plugin_module_name():
	name = __name__
	prefix = "picard.plugins."
	if name.startswith(prefix):
		name = name[len(prefix):]
	if "." in name:
		name = name.split(".")[0]
	return name


PLUGIN_MODULE_NAME = _plugin_module_name()

CONFIRM_TRASH_SETTING_KEY = "recycle_bin_confirm_trash"

PLUGIN_OPTIONS = [
	BoolOption("setting", CONFIRM_TRASH_SETTING_KEY, True),
]


def _confirm_send_to_trash(parent, count: int):
	if not _get_setting(CONFIRM_TRASH_SETTING_KEY, True):
		return True
	try:
		from PyQt5.QtWidgets import QCheckBox, QMessageBox
	except Exception:
		return True

	box = QMessageBox(parent)
	box.setIcon(QMessageBox.Warning)
	box.setWindowTitle("Send to Recycle Bin")
	box.setText(f"Send {count} selected file(s) to the Recycle Bin?")
	box.setInformativeText("This can usually be undone from the OS Recycle Bin / Trash.")
	box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
	box.setDefaultButton(QMessageBox.No)

	checkbox = QCheckBox("Don't show this warning again")
	box.setCheckBox(checkbox)
	choice = box.exec_()
	confirmed = choice == QMessageBox.StandardButton.Yes
	if confirmed and checkbox.isChecked():
		config.setting[CONFIRM_TRASH_SETTING_KEY] = False
		log.debug("Recycle Bin: user disabled future confirmation prompts")
	return confirmed


def _get_setting(name, default):
	try:
		value = config.setting[name]
	except Exception:
		return default
	return default if value is None else value


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
	NAME = "Send to Recycle Bin"

	def callback(self, objs):
		paths = _extract_file_paths(objs)
		if not paths:
			log.debug("Recycle Bin: no file paths in selection")
			return

		count = len(paths)
		if not _confirm_send_to_trash(self.parent() or None, count):
			log.debug("Recycle Bin: user cancelled")
			return

		ok, failed = send_paths_to_trash(paths)
		log.info("Recycle Bin: sent %d file(s) to trash", len(ok))
		if failed:
			log.error("Recycle Bin: failed to trash %d file(s)", len(failed))

		# Best-effort: remove files from Picard UI if supported.
		for obj in objs or []:
			try:
				if getattr(obj, "filename", None) in ok and hasattr(obj, "remove"):
					obj.remove()
			except Exception:
				pass
register_file_action(SendToRecycleBinAction)
log.info("Recycle Bin: loaded v%s", PLUGIN_VERSION)
