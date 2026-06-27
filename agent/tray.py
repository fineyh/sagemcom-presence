"""sagemcom-presence tray controller (Windows).

A tiny system-tray app so the collector is easy to start, stop, and fully
remove on a personal PC — no fear of a background poller you can't see or kill.

Launch it (double-click start-tray.vbs, or `pythonw tray.py`) and an icon shows
up in the tray; the collector starts polling right away. Right-click for:

    Status: running / stopped   (icon is green when running, grey when not)
    Start / Stop collector      (toggle, without quitting the tray)
    Start on login              (checkbox -> an HKCU "Run" entry, no admin)
    Open log
    Quit                        (stops the collector and exits)

The collector runs as a CHILD process (collector.py is untouched) tied to a
Windows job object with KILL_ON_JOB_CLOSE: if the tray exits for ANY reason —
Quit, logout, or even Task Manager ending it — Windows kills the collector too.
You can never end up with an orphaned, invisible poller you can't stop.

    pip install -r requirements.txt
    pythonw tray.py        # or double-click start-tray.vbs
"""

from __future__ import annotations

import atexit
import ctypes
import os
import subprocess
import sys
import threading
import webbrowser
import winreg
from ctypes import wintypes
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

try:  # optional: pick up DASHBOARD_URL from .env if present
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

AGENT_DIR = Path(__file__).resolve().parent
COLLECTOR = AGENT_DIR / "collector.py"
TRAY = AGENT_DIR / "tray.py"
LOG_PATH = AGENT_DIR / "collector.log"
ENV_PATH = AGENT_DIR / ".env"

APP_NAME = "SagemcomPresenceCollector"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")


def _pythonw() -> str:
    """pythonw.exe runs windowless; fall back to whatever launched us."""
    cand = Path(sys.executable).with_name("pythonw.exe")
    return str(cand) if cand.exists() else sys.executable


# --------------------------------------------------------------------------- #
# Windows job object: ties the collector child's lifetime to this process so a
# dead tray can never leave an orphaned poller behind.
# --------------------------------------------------------------------------- #
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateJobObjectW.restype = wintypes.HANDLE
_k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
_k32.SetInformationJobObject.restype = wintypes.BOOL
_k32.SetInformationJobObject.argtypes = [
    wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.AssignProcessToJobObject.restype = wintypes.BOOL
_k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_k32.CloseHandle.restype = wintypes.BOOL
_k32.CloseHandle.argtypes = [wintypes.HANDLE]

_JobObjectExtendedLimitInformation = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_ULONG_PTR = ctypes.c_size_t


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _BASIC_LIMIT(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", _ULONG_PTR),
        ("MaximumWorkingSetSize", _ULONG_PTR),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", _ULONG_PTR),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BASIC_LIMIT),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", _ULONG_PTR),
        ("JobMemoryLimit", _ULONG_PTR),
        ("PeakProcessMemoryUsed", _ULONG_PTR),
        ("PeakJobMemoryUsed", _ULONG_PTR),
    ]


def _create_kill_on_close_job():
    job = _k32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    info = _EXTENDED_LIMIT()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not _k32.SetInformationJobObject(
        job, _JobObjectExtendedLimitInformation,
        ctypes.byref(info), ctypes.sizeof(info),
    ):
        err = ctypes.get_last_error()
        _k32.CloseHandle(job)
        raise ctypes.WinError(err)
    return job


def _assign_pid_to_job(job, pid: int) -> None:
    h = _k32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
    if not h:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not _k32.AssignProcessToJobObject(job, h):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        _k32.CloseHandle(h)


# --------------------------------------------------------------------------- #
# Collector child-process controller.
# --------------------------------------------------------------------------- #
class Collector:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._logf = None
        self._lock = threading.Lock()
        try:  # held open for our whole lifetime; closing it kills the child
            self._job = _create_kill_on_close_job()
        except OSError:
            self._job = None  # degrade gracefully to plain terminate()

    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return
            self._close_log()
            self._logf = open(LOG_PATH, "a", buffering=1,
                              encoding="utf-8", errors="replace")
            self._proc = subprocess.Popen(
                [sys.executable, str(COLLECTOR)],
                cwd=str(AGENT_DIR),
                stdout=self._logf, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if self._job:
                try:
                    _assign_pid_to_job(self._job, self._proc.pid)
                except OSError:
                    pass  # already exited, or race; terminate() still works

    def stop(self) -> None:
        with self._lock:
            p, self._proc = self._proc, None
            if p is not None and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
            self._close_log()

    def _close_log(self) -> None:
        if self._logf is not None:
            try:
                self._logf.close()
            except Exception:
                pass
            self._logf = None


# --------------------------------------------------------------------------- #
# "Start on login" via an HKCU Run entry (per-user, no admin needed).
# --------------------------------------------------------------------------- #
def autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except FileNotFoundError:
        return False


def set_autostart(enable: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                        winreg.KEY_SET_VALUE) as k:
        if enable:
            cmd = f'"{_pythonw()}" "{TRAY}"'
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


# --------------------------------------------------------------------------- #
# Tray UI.
# --------------------------------------------------------------------------- #
def _icon_image(running: bool) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (40, 200, 90, 255) if running else (140, 140, 140, 255)
    d.ellipse((8, 8, 56, 56), fill=color)
    return img


def main() -> None:
    collector = Collector()
    stop_event = threading.Event()

    def refresh(icon) -> None:
        running = collector.running()
        icon.icon = _icon_image(running)
        icon.title = "Sagemcom collector — " + ("running" if running else "stopped")
        icon.update_menu()

    def on_toggle_run(icon, item) -> None:
        collector.stop() if collector.running() else collector.start()
        refresh(icon)

    def on_toggle_autostart(icon, item) -> None:
        set_autostart(not autostart_enabled())
        icon.update_menu()

    def on_open_log(icon, item) -> None:
        if not LOG_PATH.exists():
            LOG_PATH.touch()
        os.startfile(str(LOG_PATH))

    def on_open_dashboard(icon, item) -> None:
        if DASHBOARD_URL:
            webbrowser.open(DASHBOARD_URL)

    def on_quit(icon, item) -> None:
        stop_event.set()
        collector.stop()
        icon.visible = False
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            lambda item: f"Status: {'running' if collector.running() else 'stopped'}",
            None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            lambda item: "Stop collector" if collector.running() else "Start collector",
            on_toggle_run, default=True),
        pystray.MenuItem("Start on login", on_toggle_autostart,
                         checked=lambda item: autostart_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open log", on_open_log),
        pystray.MenuItem("Open dashboard", on_open_dashboard,
                         visible=bool(DASHBOARD_URL)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )

    icon = pystray.Icon(APP_NAME, _icon_image(False),
                        "Sagemcom presence collector", menu)

    def watch() -> None:
        """Reflect a crashed/exited child in the icon without user interaction."""
        prev = None
        while not stop_event.wait(3):
            running = collector.running()
            if running != prev:
                prev = running
                try:
                    refresh(icon)
                except Exception:
                    pass

    def setup(icon) -> None:
        icon.visible = True
        if ENV_PATH.exists():
            collector.start()
        else:
            icon.notify(
                "agent\\.env not found. Fill it in, then right-click → Start collector.",
                APP_NAME)
        refresh(icon)
        threading.Thread(target=watch, daemon=True).start()

    atexit.register(collector.stop)
    icon.run(setup=setup)


if __name__ == "__main__":
    main()
