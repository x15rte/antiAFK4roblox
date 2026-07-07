# Roblox anti-AFK GUI: interval (min+sec), Start/Stop, status; refuse start if window minimized.
import webbrowser
from typing import Optional
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

from anti_afk import (
    AntiAFKWorker,
    is_environment_ready,
    run_action,
    find_roblox_window,
    STATUS_BACKEND_ERROR,
    STATUS_MINIMIZED,
    STATUS_NOT_FOUND,
    MSG_ACTION_SENT,
    MSG_BACKEND_ERROR,
    MSG_ROBLOX_MINIMIZED,
    MSG_FOREGROUND_SKIPPED,
    MSG_ROBLOX_NOT_FOUND,
    RobloxWindowMinimizedError,
    RobloxWindowUnavailableError,
    RobloxBackendError,
    RobloxForegroundError,
)

APP_NAME = "antiAFK4roblox"
APP_VERSION = "1.2"
WINDOW_TITLE = f"{APP_NAME} v{APP_VERSION}"

PADX, PADY = 8, 4
HINT_NOT_FOUND = "Roblox window not found. Open Roblox, join a game, and keep the window visible."
HINT_MINIMIZED = "Roblox is minimized. Restore it from the taskbar to continue."
HINT_BACKEND_ERROR = "Could not query Windows process/window state. Restart the app or reinstall pywin32 if this keeps happening."
HINT_FOREGROUND_SKIPPED = "Stop interacting with other windows for a moment; the next interval will retry."
TIP_NO_MINIMIZE = "Keep Roblox restored; do not minimize it."
HINT_INTERVAL_ADJUSTED = "Interval adjusted to {mins}m {secs}s."
INTERVAL_HELP = "Invalid input or 0m 0s resets to 15m 0s."
RISK_WARNING = "Automation may violate Roblox Terms of Use or individual experience rules and can put your account at risk. Use only if you understand and accept that risk."
RISK_ACK_TEXT = "I understand and accept the Roblox automation/account risk."
WARN_MINIMIZED_TITLE = "Roblox minimized"
WARN_MINIMIZED = HINT_MINIMIZED


def validate_interval_values(minutes_text: str, seconds_text: str) -> tuple[int, int, bool]:
    corrected = False
    try:
        raw_m = int(minutes_text.strip())
        raw_s = int(seconds_text.strip())
    except ValueError:
        return 15, 0, True
    mins = max(0, min(999, raw_m))
    secs = max(0, min(59, raw_s))
    if mins != raw_m or secs != raw_s:
        corrected = True
    if mins == 0 and secs == 0:
        return 15, 0, True
    return mins, secs, corrected

def main():
    ok, env_msg = is_environment_ready()
    if not ok:
        root = tk.Tk()
        root.title(WINDOW_TITLE)
        root.resizable(False, False)
        tk.Label(root, text=env_msg, wraplength=280, justify=tk.LEFT, padx=12, pady=12).pack()
        root.mainloop()
        return

    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.resizable(False, False)
    root.geometry("360x280")
    root.minsize(340, 260)

    ttk.Label(root, text=TIP_NO_MINIMIZE, foreground="gray", wraplength=340).pack(fill=tk.X, padx=PADX, pady=(PADY, 2))

    style = ttk.Style()
    style.configure("TButton", padding=(8, 4))
    style.configure("TFrame", padding=0)

    interval_min_var = tk.StringVar(value="15")
    interval_sec_var = tk.StringVar(value="0")
    status_var = tk.StringVar(value="Stopped")
    risk_ack_var = tk.BooleanVar(value=False)
    worker: Optional[AntiAFKWorker] = None
    worker_generation = 0
    closing = False
    btn_start_ref: Optional[ttk.Button] = None
    btn_stop_ref: Optional[ttk.Button] = None
    spin_min_ref: Optional[tk.Spinbox] = None
    spin_sec_ref: Optional[tk.Spinbox] = None

    def validate_interval():
        return validate_interval_values(interval_min_var.get(), interval_sec_var.get())

    lf_interval = ttk.LabelFrame(root, text="Interval", padding=6)
    lf_interval.pack(fill=tk.X, padx=PADX, pady=(PADY, 2))
    f_interval = ttk.Frame(lf_interval)
    f_interval.pack(fill=tk.X)
    ttk.Label(lf_interval, text=INTERVAL_HELP, foreground="gray", wraplength=340).pack(fill=tk.X, pady=(4, 0))
    ttk.Label(f_interval, text="Minutes").pack(side=tk.LEFT, padx=(0, 4))
    spin_min = tk.Spinbox(f_interval, from_=0, to=999, textvariable=interval_min_var, width=6)
    spin_min.pack(side=tk.LEFT, padx=(0, 8))
    ttk.Label(f_interval, text="Seconds").pack(side=tk.LEFT, padx=(0, 4))
    spin_sec = tk.Spinbox(f_interval, from_=0, to=59, textvariable=interval_sec_var, width=6)
    spin_sec.pack(side=tk.LEFT)
    spin_min_ref, spin_sec_ref = spin_min, spin_sec

    hint_var = tk.StringVar(value="")
    hint_label = ttk.Label(root, textvariable=hint_var, foreground="gray", wraplength=340)

    def set_controls_running(is_running: bool):
        if btn_start_ref:
            start_state = "disabled" if is_running or not risk_ack_var.get() else "normal"
            btn_start_ref.config(state=start_state)
        if btn_stop_ref:
            btn_stop_ref.config(state="normal" if is_running else "disabled")
        state = "disabled" if is_running else "normal"
        for wdg in (spin_min_ref, spin_sec_ref):
            if wdg:
                wdg.config(state=state)

    def stop_current_worker():
        nonlocal worker, worker_generation
        if worker is None:
            return None
        current_worker = worker
        worker_generation += 1
        worker = None
        current_worker.stop()
        return current_worker

    def pause_and_warn(owner_generation=None):
        """Stop worker, set status to paused/minimized, re-enable Start, show warning."""
        if owner_generation is not None and owner_generation != worker_generation:
            return
        if stop_current_worker() is None:
            return
        status_var.set("Paused: Roblox is minimized")
        hint_var.set(HINT_MINIMIZED)
        set_controls_running(False)
        messagebox.showwarning(WARN_MINIMIZED_TITLE, WARN_MINIMIZED)

    def pause_for_backend_error(owner_generation=None):
        """Stop worker, set automation-unavailable status, and re-enable Start."""
        if owner_generation is not None and owner_generation != worker_generation:
            return
        stop_current_worker()
        status_var.set(MSG_BACKEND_ERROR)
        hint_var.set(HINT_BACKEND_ERROR)
        set_controls_running(False)

    def apply_status(msg, owner_generation):
        nonlocal worker_generation, closing
        if closing or owner_generation != worker_generation:
            return
        if msg == MSG_ACTION_SENT:
            status_var.set("Running")
            hint_var.set(MSG_ACTION_SENT)
        elif msg == MSG_ROBLOX_NOT_FOUND:
            status_var.set(MSG_ROBLOX_NOT_FOUND)
            hint_var.set(HINT_NOT_FOUND)
        elif msg == MSG_ROBLOX_MINIMIZED:
            pause_and_warn(owner_generation)
        elif msg == MSG_BACKEND_ERROR:
            pause_for_backend_error(owner_generation)
        elif msg == MSG_FOREGROUND_SKIPPED:
            status_var.set(MSG_FOREGROUND_SKIPPED)
            hint_var.set(HINT_FOREGROUND_SKIPPED)
        else:
            status_var.set(msg)
            hint_var.set("")

    def start():
        nonlocal worker, worker_generation
        if worker is not None:
            return
        mins, secs, corrected = validate_interval()
        interval_min_var.set(str(mins))
        interval_sec_var.set(str(secs))
        interval_hint = HINT_INTERVAL_ADJUSTED.format(mins=mins, secs=secs) if corrected else ""

        def set_start_hint(base_hint=""):
            if base_hint and interval_hint:
                hint_var.set(f"{base_hint} {interval_hint}")
            else:
                hint_var.set(base_hint or interval_hint)

        hwnd, status = find_roblox_window()
        if status == STATUS_MINIMIZED:
            messagebox.showwarning(WARN_MINIMIZED_TITLE, WARN_MINIMIZED)
            status_var.set("Refused: Roblox is minimized")
            set_start_hint(HINT_MINIMIZED)
            return
        if status == STATUS_BACKEND_ERROR:
            status_var.set(MSG_BACKEND_ERROR)
            set_start_hint(HINT_BACKEND_ERROR)
            return
        if status == STATUS_NOT_FOUND or hwnd is None:
            status_var.set(MSG_ROBLOX_NOT_FOUND)
            set_start_hint(HINT_NOT_FOUND)
            return
        total_sec = mins * 60 + secs
        worker_generation += 1
        generation = worker_generation
        status_var.set("Running")
        set_start_hint()

        def on_status(msg, gen=generation):
            if closing or gen != worker_generation:
                return
            try:
                root.after(0, lambda m=msg, g=gen: apply_status(m, g))
            except Exception:
                return

        def do_action(hwnd, owner, owner_generation, action_done):
            nonlocal worker, worker_generation, closing
            try:
                if (
                    closing
                    or owner is None
                    or worker is not owner
                    or owner_generation != worker_generation
                    or not owner.running
                ):
                    return
                fresh_hwnd, fresh_status = find_roblox_window()
                if fresh_status == STATUS_MINIMIZED:
                    pause_and_warn(owner_generation)
                    return
                if fresh_status == STATUS_BACKEND_ERROR:
                    pause_for_backend_error(owner_generation)
                    return
                if fresh_status == STATUS_NOT_FOUND or fresh_hwnd is None:
                    status_var.set(MSG_ROBLOX_NOT_FOUND)
                    hint_var.set(HINT_NOT_FOUND)
                    return
                run_action(fresh_hwnd)
                status_var.set("Running")
                hint_var.set(MSG_ACTION_SENT)
            except RobloxWindowMinimizedError:
                pause_and_warn(owner_generation)
            except RobloxBackendError:
                pause_for_backend_error(owner_generation)
            except RobloxWindowUnavailableError:
                status_var.set(MSG_ROBLOX_NOT_FOUND)
                hint_var.set(HINT_NOT_FOUND)
            except RobloxForegroundError:
                status_var.set(MSG_FOREGROUND_SKIPPED)
                hint_var.set(HINT_FOREGROUND_SKIPPED)
            except Exception as e:
                status_var.set(f"Error: {e}")
            finally:
                action_done()

        def schedule_action(h, action_done, gen=generation):
            nonlocal worker
            owner = worker
            if (
                closing
                or owner is None
                or worker is not owner
                or gen != worker_generation
                or not owner.running
            ):
                action_done()
                return
            root.after(0, lambda hw=h, owner=owner, gen=gen, done=action_done: do_action(hw, owner, gen, done))

        w = AntiAFKWorker(total_sec, on_status=on_status, schedule_action=schedule_action)
        worker = w
        w.start()
        set_controls_running(True)

    def stop():
        if stop_current_worker() is None:
            return
        status_var.set("Stopped")
        hint_var.set("")
        set_controls_running(False)
    def on_close():
        nonlocal closing
        closing = True
        stop_current_worker()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    ttk.Label(root, text=RISK_WARNING, foreground="red", wraplength=340).pack(fill=tk.X, padx=PADX, pady=(0, PADY))
    risk_ack = ttk.Checkbutton(
        root,
        text=RISK_ACK_TEXT,
        variable=risk_ack_var,
        command=lambda: set_controls_running(worker is not None),
    )
    risk_ack.pack(fill=tk.X, padx=PADX, pady=(0, PADY))
    f_btn = ttk.Frame(root)
    f_btn.pack(fill=tk.X, padx=PADX, pady=PADY)
    btn_start = ttk.Button(f_btn, text="Start", command=start, state="disabled")
    btn_start.pack(side=tk.LEFT, padx=(0, 8))
    btn_start_ref = btn_start
    btn_stop = ttk.Button(f_btn, text="Stop", command=stop, state="disabled")
    btn_stop.pack(side=tk.LEFT)
    btn_stop_ref = btn_stop

    f_status = ttk.Frame(root)
    f_status.pack(fill=tk.X, padx=PADX, pady=(0, 2))
    ttk.Label(f_status, text="Status:").pack(side=tk.LEFT, padx=(0, 4))
    ttk.Label(f_status, textvariable=status_var, foreground="gray").pack(side=tk.LEFT)
    hint_label.pack(fill=tk.X, padx=PADX, pady=(0, PADY))

    repo_url = "https://github.com/x15rte/antiAFK4roblox"
    link_label = tk.Label(root, text="Open project page", fg="blue", cursor="hand2", font=("TkDefaultFont", 9), wraplength=340)
    link_label.pack(pady=(0, PADY))
    link_label.bind("<Button-1>", lambda e: webbrowser.open(repo_url))

    root.mainloop()
    if worker is not None:
        worker.stop()


if __name__ == "__main__":
    main()
