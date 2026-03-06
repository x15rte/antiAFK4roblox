# Roblox anti-AFK GUI: interval (min+sec), Start/Stop, status; refuse start if window minimized.
import webbrowser
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

from anti_afk import (
    AntiAFKWorker,
    is_environment_ready,
    run_action,
    find_roblox_window,
    STATUS_OK,
    STATUS_MINIMIZED,
    STATUS_NOT_FOUND,
)

APP_NAME = "antiAFK4roblox"
APP_VERSION = "1.0"
WINDOW_TITLE = f"{APP_NAME} v{APP_VERSION}"

PADX, PADY = 8, 4
HINT_NOT_FOUND = "Roblox window not found. Start Roblox and join a game first."
HINT_MINIMIZED = "Restore Roblox window from taskbar, then click Start again."
TIP_NO_MINIMIZE = "Do not minimize Roblox"
WARN_MINIMIZED_TITLE = "Roblox minimized"
WARN_MINIMIZED = "Roblox window is minimized. Restore it from the taskbar for anti-AFK to work."


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
    root.geometry("320x180")
    root.minsize(300, 160)

    ttk.Label(root, text=TIP_NO_MINIMIZE, foreground="gray", wraplength=300).pack(fill=tk.X, padx=PADX, pady=(PADY, 2))

    style = ttk.Style()
    style.configure("TButton", padding=(8, 4))
    style.configure("TFrame", padding=0)

    interval_min_var = tk.StringVar(value="15")
    interval_sec_var = tk.StringVar(value="0")
    status_var = tk.StringVar(value="Stopped")
    worker = [None]
    btn_start_ref, btn_stop_ref = [None], [None]
    spin_min_ref, spin_sec_ref = [None], [None]

    def validate_interval():
        """Parse min/sec, clamp range; total interval at least 1 second."""
        try:
            m = int(interval_min_var.get().strip())
            s = int(interval_sec_var.get().strip())
        except ValueError:
            return 15, 0
        m = max(0, min(999, m))
        s = max(0, min(59, s))
        if m == 0 and s == 0:
            m, s = 15, 0
        return m, s

    lf_interval = ttk.LabelFrame(root, text="Interval", padding=6)
    lf_interval.pack(fill=tk.X, padx=PADX, pady=(PADY, 2))
    f_interval = ttk.Frame(lf_interval)
    f_interval.pack(fill=tk.X)
    ttk.Label(f_interval, text="Minutes").pack(side=tk.LEFT, padx=(0, 4))
    spin_min = tk.Spinbox(f_interval, from_=0, to=999, textvariable=interval_min_var, width=6)
    spin_min.pack(side=tk.LEFT, padx=(0, 8))
    ttk.Label(f_interval, text="Seconds").pack(side=tk.LEFT, padx=(0, 4))
    spin_sec = tk.Spinbox(f_interval, from_=0, to=59, textvariable=interval_sec_var, width=6)
    spin_sec.pack(side=tk.LEFT)
    spin_min_ref[0], spin_sec_ref[0] = spin_min, spin_sec

    hint_var = tk.StringVar(value="")
    hint_label = ttk.Label(root, textvariable=hint_var, foreground="gray", wraplength=300)

    def pause_and_warn():
        """Stop worker, set status to paused/minimized, re-enable Start, show warning."""
        if worker[0] is None:
            return
        worker[0].stop()
        worker[0] = None
        status_var.set("Paused: Roblox minimized")
        hint_var.set(HINT_MINIMIZED)
        if btn_start_ref[0]:
            btn_start_ref[0].config(state="normal")
        if btn_stop_ref[0]:
            btn_stop_ref[0].config(state="disabled")
        for wdg in (spin_min_ref[0], spin_sec_ref[0]):
            if wdg:
                wdg.config(state="normal")
        messagebox.showwarning(WARN_MINIMIZED_TITLE, WARN_MINIMIZED)

    def on_status(msg):
        root.after(0, lambda: status_var.set(msg))
        if msg == "Roblox window not found":
            root.after(0, lambda: hint_var.set(HINT_NOT_FOUND))
        elif msg == "Roblox minimized":
            root.after(0, pause_and_warn)
        else:
            root.after(0, lambda: hint_var.set(""))

    def start():
        if worker[0] is not None:
            return
        hwnd, status = find_roblox_window()
        if status == STATUS_MINIMIZED:
            messagebox.showwarning(WARN_MINIMIZED_TITLE, WARN_MINIMIZED)
            status_var.set("Refused: Roblox minimized")
            hint_var.set(HINT_MINIMIZED)
            return
        if status == STATUS_NOT_FOUND or hwnd is None:
            status_var.set("Roblox window not found")
            hint_var.set(HINT_NOT_FOUND)
            return
        mins, secs = validate_interval()
        interval_min_var.set(str(mins))
        interval_sec_var.set(str(secs))
        total_sec = mins * 60 + secs
        status_var.set("Running...")
        hint_var.set("")

        def do_action(hwnd):
            try:
                run_action(hwnd)
                status_var.set("Action sent")
            except Exception as e:
                status_var.set(f"Error: {e}")

        def schedule_action(h):
            root.after(0, lambda hw=h: do_action(hw))

        w = AntiAFKWorker(total_sec, on_status=on_status, schedule_action=schedule_action)
        worker[0] = w
        w.start()
        if btn_start_ref[0]:
            btn_start_ref[0].config(state="disabled")
        if btn_stop_ref[0]:
            btn_stop_ref[0].config(state="normal")
        for wdg in (spin_min_ref[0], spin_sec_ref[0]):
            if wdg:
                wdg.config(state="disabled")

    def stop():
        if worker[0] is None:
            return
        worker[0].stop()
        worker[0] = None
        status_var.set("Stopped")
        hint_var.set("")
        if btn_start_ref[0]:
            btn_start_ref[0].config(state="normal")
        if btn_stop_ref[0]:
            btn_stop_ref[0].config(state="disabled")
        for wdg in (spin_min_ref[0], spin_sec_ref[0]):
            if wdg:
                wdg.config(state="normal")

    f_btn = ttk.Frame(root)
    f_btn.pack(fill=tk.X, padx=PADX, pady=PADY)
    btn_start = ttk.Button(f_btn, text="Start", command=start)
    btn_start.pack(side=tk.LEFT, padx=(0, 8))
    btn_start_ref[0] = btn_start
    btn_stop = ttk.Button(f_btn, text="Stop", command=stop, state="disabled")
    btn_stop.pack(side=tk.LEFT)
    btn_stop_ref[0] = btn_stop

    f_status = ttk.Frame(root)
    f_status.pack(fill=tk.X, padx=PADX, pady=(0, 2))
    ttk.Label(f_status, text="Status:").pack(side=tk.LEFT, padx=(0, 4))
    ttk.Label(f_status, textvariable=status_var, foreground="gray").pack(side=tk.LEFT)
    hint_label.pack(fill=tk.X, padx=PADX, pady=(0, PADY))

    repo_url = "https://github.com/x15rte/antiAFK4roblox"
    link_label = tk.Label(root, text=repo_url, fg="blue", cursor="hand2", font=("TkDefaultFont", 9), wraplength=280)
    link_label.pack(pady=(0, PADY))
    link_label.bind("<Button-1>", lambda e: webbrowser.open(repo_url))

    root.mainloop()
    if worker[0] is not None:
        worker[0].stop()


if __name__ == "__main__":
    main()
