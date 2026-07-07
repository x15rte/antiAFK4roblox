# antiAFK4roblox

This tool periodically locates the Roblox game process, brings the Roblox window to the foreground, and sends the I and O key presses to keep your session active. After the keys are sent, it automatically restores the previously focused window so your workflow is not interrupted.  

If the Roblox window is minimized, the tool will not run the anti-AFK action and will instead warn you to restore the window from the taskbar and click Start again.

It only sends I then O to a visible, restored Roblox window; it does not run the action while Roblox is minimized.

This tool currently supports Windows only.

This tool automates Roblox input. Automation may violate Roblox Terms of Use or individual experience rules and can put your account at risk. Use only if you understand and accept that risk.

## Requirements

- Windows.
- Release EXE: no Python install required.
- Run from source: Windows Python 3.11 with Tkinter/Tcl/Tk available, then `pip install -r requirements.txt`.
- Build the EXE: install `requirements-build.txt` in addition to runtime requirements.
Direct dependencies are pinned in requirements.txt and requirements-build.txt for repeatable Windows installs.

## Usage

### Method 1
Download the latest `antiAFK4roblox-vX.Y-windows.zip` asset from the Releases page, extract it, and run `antiAFK4roblox.exe`.

First launch of the frozen EXE can be delayed; if no window appears after a few seconds, run from source to see the error message.

### Method 2
```powershell
# Install
git clone https://github.com/x15rte/antiAFK4roblox.git
cd antiAFK4roblox
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

# Run
python .\main.py
```

Interval accepts 0-999 minutes and 0-59 seconds. Invalid input or 0m 0s is normalized to 15m 0s when Start is clicked.

## Statuses

| Status | Meaning |
| --- | --- |
| Stopped | No worker is running. |
| Running | The worker is polling and will send I then O when Roblox is visible and restored. |
| Paused: Roblox is minimized | Restore Roblox from the taskbar, keep the acknowledgement checked, then click Start again. |
| Windows automation unavailable | The app cannot query or control Windows automation state; follow Troubleshooting. |

After a successful anti-AFK action, the Status remains Running and the hint text shows Action sent.

## Validation
```powershell
python -m py_compile main.py app.py anti_afk.py
python -m unittest discover -s tests -t . -p "test*.py" -v
```

## Troubleshooting

| Status | What to do |
| --- | --- |
| Roblox window not found | Open Roblox, join a game, and keep the Roblox window visible. |
| Roblox is minimized | Restore Roblox from the taskbar, then click Start again. |
| Windows automation unavailable | The app pauses if it was running. Restart the app; if running from source, install or repair pywin32 with `pip install -r requirements.txt`, then check the risk acknowledgement and click Start again. |
| Could not bring Roblox to the foreground; action skipped | Stop interacting with other windows for a moment; the next interval will retry. |

## Freeze to exe
```powershell
pip install -r requirements.txt
pip install -r requirements-build.txt
pyinstaller --onefile --noconsole --name antiAFK4roblox --hidden-import=pythoncom --hidden-import=win32com.client main.py
```
