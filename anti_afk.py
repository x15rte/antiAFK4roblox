# Roblox anti-AFK: find window, bring to front, send I+O, restore foreground.
import time
import threading
import ctypes

try:
    import win32gui
    import win32process
    import win32api
except ImportError:
    win32gui = None
    win32process = None
    win32api = None

ROBLOX_PROCESS_NAME = "RobloxPlayerBeta.exe"
KEYPRESS_DELAY_MS = 0.045
INTERACTION_DELAY_MS = 0.05
VK_I, VK_O = 0x49, 0x4F
KEYEVENTF_KEYUP = 0x0002
MAPVK_VK_TO_VSC = 0
SLEEP_CHUNK_SEC = 0.25
JOIN_TIMEOUT_SEC = 2.0

# Find result status
STATUS_OK = None
STATUS_NOT_FOUND = "not_found"
STATUS_MINIMIZED = "minimized"

MSG_ACTION_SENT = "Action sent"
MSG_ROBLOX_MINIMIZED = "Roblox minimized"
MSG_ROBLOX_NOT_FOUND = "Roblox window not found"


def _get_pids_by_process_name(process_name):
    """Return PIDs for process name via WMI. On failure return []."""
    try:
        import win32com.client
        wmi = win32com.client.GetObject("winmgmts:")
        pids = [p.ProcessId for p in wmi.ExecQuery(
            "SELECT ProcessId FROM Win32_Process WHERE Name = '%s'" % process_name
        )]
        return pids
    except Exception:
        return []


def is_environment_ready():
    """Return (ok, message). Ok if pywin32 is available."""
    if win32gui is None or win32process is None or win32api is None:
        return False, "Missing dependency. Please install first:\npip install pywin32"
    return True, ""


def is_window_minimized(hwnd):
    """Return True if window is minimized."""
    if not hwnd or win32gui is None:
        return False
    try:
        return bool(ctypes.windll.user32.IsIconic(hwnd))
    except Exception:
        return False


def find_roblox_window():
    """Find visible Roblox window. Return (hwnd, status); status None = ok, else 'not_found' or 'minimized'."""
    if win32gui is None or win32process is None:
        return None, STATUS_NOT_FOUND
    gui = win32gui
    process = win32process
    pids = set(_get_pids_by_process_name(ROBLOX_PROCESS_NAME))
    if not pids:
        return None, STATUS_NOT_FOUND
    result = [None]

    def callback(hwnd, _):
        if not gui.IsWindowVisible(hwnd):
            return True
        try:
            _, pid = process.GetWindowThreadProcessId(hwnd)
            if pid in pids:
                result[0] = hwnd
                return False
        except Exception:
            pass
        return True

    try:
        gui.EnumWindows(callback, None)
    except Exception:
        return None, STATUS_NOT_FOUND

    hwnd = result[0]
    if hwnd is None:
        return None, STATUS_NOT_FOUND
    if is_window_minimized(hwnd):
        return hwnd, STATUS_MINIMIZED
    return hwnd, STATUS_OK


def _bring_to_front(hwnd):
    """Bring window to foreground (caller must have focus)."""
    if win32gui is None or win32process is None or win32api is None:
        return
    user32 = ctypes.windll.user32
    current_tid = win32api.GetCurrentThreadId()
    fg = _get_foreground_window()
    fg_tid = None
    target_tid = None
    attached_fg = False
    attached_target = False

    if fg:
        try:
            fg_tid, _ = win32process.GetWindowThreadProcessId(fg)
            if fg_tid and fg_tid != current_tid:
                user32.AttachThreadInput(current_tid, fg_tid, True)
                attached_fg = True
        except Exception:
            pass

    try:
        target_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
        if target_tid and current_tid != target_tid:
            user32.AttachThreadInput(current_tid, target_tid, True)
            attached_target = True
        user32.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
    finally:
        if attached_target and target_tid and current_tid != target_tid:
            try:
                user32.AttachThreadInput(current_tid, target_tid, False)
            except Exception:
                pass
        if attached_fg and fg_tid and fg_tid != current_tid:
            try:
                user32.AttachThreadInput(current_tid, fg_tid, False)
            except Exception:
                pass


def _keybd_event(bVk, bScan, dwFlags, dwExtraInfo=0):
    ctypes.windll.user32.keybd_event(bVk, bScan, dwFlags, dwExtraInfo)


def _press_key_vk(vk):
    """Press and release key via keybd_event with delay."""
    scan = ctypes.windll.user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    _keybd_event(vk, scan, 0, 0)
    time.sleep(KEYPRESS_DELAY_MS)
    _keybd_event(vk, scan, KEYEVENTF_KEYUP, 0)
    time.sleep(INTERACTION_DELAY_MS)


def _action_i_o():
    """Send I then O."""
    _press_key_vk(VK_I)
    _press_key_vk(VK_O)


def _get_foreground_window():
    return ctypes.windll.user32.GetForegroundWindow()


def run_action(hwnd):
    """Bring Roblox to front, send I+O, restore previous foreground. Raises ValueError if minimized."""
    if win32gui and not win32gui.IsWindow(hwnd):
        raise ValueError("Roblox window is no longer valid")
    if is_window_minimized(hwnd):
        raise ValueError("Roblox window is minimized")
    prev_hwnd = _get_foreground_window()
    _bring_to_front(hwnd)
    time.sleep(0.35)
    try:
        if _get_foreground_window() != hwnd:
            raise ValueError("Roblox not in foreground; action skipped")
        _action_i_o()
    finally:
        if prev_hwnd and win32gui and win32gui.IsWindow(prev_hwnd) and win32gui.IsWindowVisible(prev_hwnd):
            try:
                win32gui.SetForegroundWindow(prev_hwnd)
            except Exception:
                pass


class AntiAFKWorker:
    """Background thread: find Roblox each interval, run run_action on main thread via schedule_action."""

    def __init__(self, interval_seconds, on_status=None, schedule_action=None):
        self.interval_sec = max(1, int(interval_seconds))
        self.on_status = on_status
        self.schedule_action = schedule_action
        self.running = False
        self._thread = None

    def _run(self):
        while self.running:
            hwnd, status = find_roblox_window()
            if status == STATUS_OK and hwnd is not None:
                if self.schedule_action:
                    self.schedule_action(hwnd)
                else:
                    try:
                        run_action(hwnd)
                        if self.on_status:
                            self.on_status(MSG_ACTION_SENT)
                    except Exception as e:
                        if self.on_status:
                            self.on_status(f"Error: {e}")
            elif self.on_status:
                if status == STATUS_MINIMIZED:
                    self.on_status(MSG_ROBLOX_MINIMIZED)
                else:
                    self.on_status(MSG_ROBLOX_NOT_FOUND)
            deadline = time.monotonic() + self.interval_sec
            while self.running and time.monotonic() < deadline:
                time.sleep(SLEEP_CHUNK_SEC)

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=JOIN_TIMEOUT_SEC)
            self._thread = None
