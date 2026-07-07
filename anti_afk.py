# Roblox anti-AFK: find window, bring to front, send I+O, restore foreground.
import time
import threading
import ctypes
import ctypes.wintypes

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
INPUT_KEYBOARD = 1
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0
GW_OWNER = 4
SLEEP_CHUNK_SEC = 0.25
JOIN_TIMEOUT_SEC = 2.0
FOREGROUND_WAIT_TIMEOUT_SEC = 1.0
FOREGROUND_POLL_SEC = 0.05
FOREGROUND_RESTORE_ATTEMPTS = 2

# Find result status
STATUS_OK = None
STATUS_NOT_FOUND = "not_found"
STATUS_MINIMIZED = "minimized"
STATUS_BACKEND_ERROR = "backend_error"

MSG_ACTION_SENT = "Action sent"
MSG_ROBLOX_MINIMIZED = "Roblox minimized"
MSG_ROBLOX_NOT_FOUND = "Roblox window not found"
MSG_BACKEND_ERROR = "Windows automation unavailable"
MSG_FOREGROUND_SKIPPED = "Could not bring Roblox to the foreground; action skipped"


def _get_pids_by_process_name(process_name):
    """Return (pids, error_message) for process name via WMI."""
    pythoncom = None
    com_initialized = False
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        com_initialized = True
        wmi = win32com.client.GetObject("winmgmts:")
        pids = [p.ProcessId for p in wmi.ExecQuery(
            "SELECT ProcessId FROM Win32_Process WHERE Name = '%s'" % process_name
        )]
        result = (pids, None)
    except Exception as e:
        result = ([], str(e) or e.__class__.__name__)
    if com_initialized:
        try:
            assert pythoncom is not None
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return result


def is_environment_ready():
    """Return (ok, message). Ok if pywin32 is available."""
    if win32gui is None or win32process is None or win32api is None:
        return False, "Missing dependency: pywin32 (listed in requirements.txt). Install with:\npip install -r requirements.txt"
    return True, ""


def is_window_minimized(hwnd):
    """Return True if window is minimized."""
    if not hwnd or win32gui is None:
        return False
    return bool(ctypes.windll.user32.IsIconic(hwnd))


def _is_unowned_top_level_window(gui, hwnd):
    """Return whether hwnd is an unowned top-level window plus whether the query failed."""
    get_parent = getattr(gui, "GetParent", None)
    if get_parent is not None:
        try:
            if get_parent(hwnd):
                return False, False
        except Exception:
            return False, True
    get_window = getattr(gui, "GetWindow", None)
    if get_window is not None:
        try:
            if get_window(hwnd, GW_OWNER):
                return False, False
        except Exception:
            return False, True
    return True, False


def find_roblox_window():
    """Find visible Roblox window. Return (hwnd, status)."""
    if win32gui is None or win32process is None:
        return None, STATUS_BACKEND_ERROR
    gui = win32gui
    process = win32process
    pids, pid_error = _get_pids_by_process_name(ROBLOX_PROCESS_NAME)
    if pid_error is not None:
        return None, STATUS_BACKEND_ERROR
    pids = set(pids)
    if not pids:
        return None, STATUS_NOT_FOUND
    candidates = []
    window_query_failed = False

    def callback(hwnd, _):
        nonlocal window_query_failed
        try:
            if not gui.IsWindowVisible(hwnd):
                return True
        except Exception:
            window_query_failed = True
            return True
        is_candidate, ownership_query_failed = _is_unowned_top_level_window(gui, hwnd)
        if ownership_query_failed:
            window_query_failed = True
            return True
        if not is_candidate:
            return True
        try:
            _, pid = process.GetWindowThreadProcessId(hwnd)
        except Exception:
            window_query_failed = True
            return True
        if pid in pids:
            candidates.append(hwnd)
        return True

    try:
        gui.EnumWindows(callback, None)
    except Exception:
        return None, STATUS_BACKEND_ERROR

    if not candidates:
        if window_query_failed:
            return None, STATUS_BACKEND_ERROR
        return None, STATUS_NOT_FOUND

    minimized_candidates = []
    minimize_query_failed = False
    for hwnd in candidates:
        try:
            minimized = is_window_minimized(hwnd)
        except Exception:
            minimize_query_failed = True
            continue
        if not minimized:
            return hwnd, STATUS_OK
        minimized_candidates.append(hwnd)
    if minimize_query_failed:
        return None, STATUS_BACKEND_ERROR
    if minimized_candidates:
        return minimized_candidates[0], STATUS_MINIMIZED
    return None, STATUS_NOT_FOUND


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


ULONG_PTR = ctypes.wintypes.WPARAM


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.wintypes.DWORD),
        ("wParamL", ctypes.wintypes.WORD),
        ("wParamH", ctypes.wintypes.WORD),
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.wintypes.DWORD), ("union", INPUT_UNION)]


def _send_keyboard_input(vk: int, flags: int) -> None:
    scan = ctypes.windll.user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    keyboard_input = KEYBDINPUT(
        wVk=0,
        wScan=scan,
        dwFlags=KEYEVENTF_SCANCODE | flags,
        time=0,
        dwExtraInfo=0,
    )
    input_struct = INPUT()
    input_struct.type = INPUT_KEYBOARD
    input_struct.union.ki = keyboard_input
    sent = ctypes.windll.user32.SendInput(1, ctypes.byref(input_struct), ctypes.sizeof(INPUT))
    if sent != 1:
        raise RobloxBackendError("SendInput failed")


def _press_key_vk(vk):
    """Press and release key via SendInput with delay."""
    _send_keyboard_input(vk, 0)
    time.sleep(KEYPRESS_DELAY_MS)
    _send_keyboard_input(vk, KEYEVENTF_KEYUP)
    time.sleep(INTERACTION_DELAY_MS)


def _action_i_o(hwnd):
    """Send I then O if Roblox remains foreground."""
    _raise_if_not_foreground(hwnd)
    _press_key_vk(VK_I)
    _raise_if_not_foreground(hwnd)
    _press_key_vk(VK_O)


def _get_foreground_window():
    return ctypes.windll.user32.GetForegroundWindow()


class RobloxWindowMinimizedError(ValueError):
    pass


class RobloxWindowUnavailableError(ValueError):
    pass

class RobloxBackendError(ValueError):
    pass

class RobloxForegroundError(ValueError):
    pass

def _raise_if_not_foreground(hwnd):
    if _get_foreground_window() != hwnd:
        raise RobloxForegroundError(MSG_FOREGROUND_SKIPPED)


def _wait_for_foreground(hwnd, timeout_sec=FOREGROUND_WAIT_TIMEOUT_SEC):
    deadline = time.monotonic() + timeout_sec
    while True:
        if _get_foreground_window() == hwnd:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(FOREGROUND_POLL_SEC)


def run_action(hwnd):
    """Bring Roblox to front, send I+O, restore previous foreground. Raises ValueError if minimized."""
    if win32gui and not win32gui.IsWindow(hwnd):
        raise RobloxWindowUnavailableError("Roblox window is no longer valid")
    try:
        minimized = is_window_minimized(hwnd)
    except Exception:
        raise RobloxBackendError("Could not verify Roblox window state")
    if minimized:
        raise RobloxWindowMinimizedError("Roblox window is minimized")
    prev_hwnd = _get_foreground_window()
    _bring_to_front(hwnd)
    try:
        if not _wait_for_foreground(hwnd):
            raise RobloxForegroundError(MSG_FOREGROUND_SKIPPED)
        _action_i_o(hwnd)
    finally:
        if prev_hwnd and win32gui and win32gui.IsWindow(prev_hwnd) and win32gui.IsWindowVisible(prev_hwnd):
            for attempt in range(FOREGROUND_RESTORE_ATTEMPTS):
                try:
                    win32gui.SetForegroundWindow(prev_hwnd)
                    if _get_foreground_window() == prev_hwnd:
                        break
                except Exception:
                    pass
                if attempt + 1 < FOREGROUND_RESTORE_ATTEMPTS:
                    time.sleep(FOREGROUND_POLL_SEC)


class AntiAFKWorker:
    """Background thread: find Roblox each interval, run run_action on main thread via schedule_action."""

    def __init__(self, interval_seconds, on_status=None, schedule_action=None, find_window=None, action=None):
        self.interval_sec = max(1, int(interval_seconds))
        self.on_status = on_status
        self.schedule_action = schedule_action
        self.find_window = find_window or find_roblox_window
        self.action = action or run_action
        self.running = False
        self._thread = None
        self._action_lock = threading.Lock()
        self._action_pending = False

    def _try_begin_action(self):
        with self._action_lock:
            if self._action_pending:
                return False
            self._action_pending = True
            return True

    def _finish_action(self):
        with self._action_lock:
            self._action_pending = False

    def _emit_status(self, msg):
        if self.on_status is not None:
            self.on_status(msg)

    def _poll_once(self):
        try:
            hwnd, status = self.find_window()
        except Exception:
            self._emit_status(MSG_BACKEND_ERROR)
            return
        if status == STATUS_OK and hwnd is not None:
            if self.schedule_action:
                if not self._try_begin_action():
                    return
                completed = False
                completed_lock = threading.Lock()

                def action_done():
                    nonlocal completed
                    should_finish = False
                    with completed_lock:
                        if not completed:
                            completed = True
                            should_finish = True
                    if should_finish:
                        self._finish_action()

                try:
                    self.schedule_action(hwnd, action_done)
                except Exception as e:
                    action_done()
                    self._emit_status(f"Error: {e}")
            else:
                try:
                    self.action(hwnd)
                    self._emit_status(MSG_ACTION_SENT)
                except RobloxWindowMinimizedError:
                    self._emit_status(MSG_ROBLOX_MINIMIZED)
                except RobloxBackendError:
                    self._emit_status(MSG_BACKEND_ERROR)
                except RobloxWindowUnavailableError:
                    self._emit_status(MSG_ROBLOX_NOT_FOUND)
                except RobloxForegroundError:
                    self._emit_status(MSG_FOREGROUND_SKIPPED)
                except Exception as e:
                    self._emit_status(f"Error: {e}")
        elif status == STATUS_MINIMIZED:
            self._emit_status(MSG_ROBLOX_MINIMIZED)
        elif status == STATUS_BACKEND_ERROR:
            self._emit_status(MSG_BACKEND_ERROR)
        else:
            self._emit_status(MSG_ROBLOX_NOT_FOUND)

    def _run(self):
        while self.running:
            try:
                self._poll_once()
            except Exception as e:
                try:
                    self._emit_status(f"Error: {e}")
                except Exception:
                    pass
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
