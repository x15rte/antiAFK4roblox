import unittest

import app


class FakeVar:
    instances = []

    def __init__(self, value=""):
        self.initial_value = value
        self.value = value
        FakeVar.instances.append(self)

    def get(self):
        return self.value

    def set(self, value):
        self.value = value




class FakeWidget:
    instances = []

    def __init__(self, *args, **kwargs):
        self.text = kwargs.get("text")
        self.textvariable = kwargs.get("textvariable")
        self.variable = kwargs.get("variable")
        self.command = kwargs.get("command")
        self.state = kwargs.get("state")
        FakeWidget.instances.append(self)

    def pack(self, *args, **kwargs):
        return None

    def bind(self, *args, **kwargs):
        return None

    def config(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]



class FakeRoot(FakeWidget):
    last = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.after_calls = []
        self.protocols = {}
        self.raise_on_after = False
        self.destroyed = False
        FakeRoot.last = self

    def title(self, value):
        self.window_title = value

    def resizable(self, *args):
        return None

    def geometry(self, value):
        return None

    def minsize(self, *args):
        return None

    def mainloop(self):
        return None

    def after(self, delay, callback):
        if self.raise_on_after:
            raise RuntimeError("after closed")
        self.after_calls.append((delay, callback))

    def protocol(self, name, callback):
        self.protocols[name] = callback

    def destroy(self):
        self.destroyed = True


class FakeStyle:
    def configure(self, *args, **kwargs):
        return None


class FakeButton(FakeWidget):
    instances = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        FakeButton.instances.append(self)

class FakeSpinbox(FakeWidget):
    instances = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        FakeSpinbox.instances.append(self)



class FakeTkModule:
    Tk = FakeRoot
    StringVar = FakeVar
    BooleanVar = FakeVar
    Spinbox = FakeSpinbox
    Label = FakeWidget
    LEFT = "left"
    X = "x"


class FakeTtkModule:
    Style = FakeStyle
    Label = FakeWidget
    LabelFrame = FakeWidget
    Frame = FakeWidget
    Button = FakeButton
    Checkbutton = FakeButton


class FakeMessagebox:
    warnings = []

    @staticmethod
    def showwarning(title, message):
        FakeMessagebox.warnings.append((title, message))


class FakeWorker:
    instances = []

    def __init__(self, interval_seconds, on_status=None, schedule_action=None):
        self.interval_seconds = interval_seconds
        self.on_status = on_status
        self.schedule_action = schedule_action
        self.running = False
        FakeWorker.instances.append(self)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


class AppLifecycleSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.originals = {
            "tk": app.tk,
            "ttk": app.ttk,
            "messagebox": app.messagebox,
            "AntiAFKWorker": app.AntiAFKWorker,
            "is_environment_ready": app.is_environment_ready,
            "find_roblox_window": app.find_roblox_window,
            "run_action": app.run_action,
        }
        FakeRoot.last = None
        FakeVar.instances = []
        FakeWidget.instances = []
        FakeSpinbox.instances = []
        FakeButton.instances = []
        FakeWorker.instances = []
        FakeMessagebox.warnings = []
        app.tk = FakeTkModule
        app.ttk = FakeTtkModule
        app.messagebox = FakeMessagebox
        app.AntiAFKWorker = FakeWorker
        app.is_environment_ready = lambda: (True, "")
        app.find_roblox_window = lambda: (123, None)
        app.run_action = lambda _hwnd: None

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(app, name, value)

    def _last_root(self) -> FakeRoot:
        root = FakeRoot.last
        assert root is not None
        return root

    def _start_button(self):
        return next(button for button in FakeButton.instances if button.text == "Start")

    def _risk_ack_checkbox(self):
        return next(widget for widget in FakeWidget.instances if widget.text == app.RISK_ACK_TEXT)

    def _acknowledge_risk_and_get_start_button(self):
        start_button = self._start_button()
        risk_ack_checkbox = self._risk_ack_checkbox()
        risk_ack_checkbox.variable.set(True)
        risk_ack_checkbox.command()
        self.assertEqual(start_button.state, "normal")
        return start_button

    def _start_app_worker(self):
        app.main()
        start_button = self._acknowledge_risk_and_get_start_button()
        start_button.command()
        self.assertEqual(len(FakeWorker.instances), 1)
        return self._last_root(), FakeWorker.instances[0]

    def _status_var(self):
        return next(var for var in FakeVar.instances if var.initial_value == "Stopped")

    def _hint_var(self):
        return next(var for var in FakeVar.instances if var.initial_value == "")

    def test_missing_environment_shows_guidance_window_without_main_controls(self):
        app.is_environment_ready = lambda: (False, "missing guidance")

        app.main()

        root = self._last_root()
        self.assertEqual(root.window_title, app.WINDOW_TITLE)
        self.assertTrue(any(widget.text == "missing guidance" for widget in FakeWidget.instances))
        self.assertFalse(any(button.text == "Start" for button in FakeButton.instances))
        self.assertFalse(any(button.text == "Stop" for button in FakeButton.instances))

    def test_start_requires_risk_acknowledgement(self):
        app.main()
        start_button = self._start_button()
        risk_ack_checkbox = self._risk_ack_checkbox()

        self.assertEqual(start_button.state, "disabled")

        risk_ack_checkbox.variable.set(True)
        risk_ack_checkbox.command()
        self.assertEqual(start_button.state, "normal")

        risk_ack_checkbox.variable.set(False)
        risk_ack_checkbox.command()
        self.assertEqual(start_button.state, "disabled")

    def test_start_disables_inputs_and_stop_reenables_inputs(self):
        app.main()
        start_button = self._acknowledge_risk_and_get_start_button()
        stop_button = next(button for button in FakeButton.instances if button.text == "Stop")

        start_button.command()

        self.assertEqual(len(FakeWorker.instances), 1)
        self.assertEqual(start_button.state, "disabled")
        self.assertEqual(stop_button.state, "normal")
        self.assertEqual(len(FakeSpinbox.instances), 2)
        self.assertEqual([spinbox.state for spinbox in FakeSpinbox.instances], ["disabled", "disabled"])

        stop_button.command()

        self.assertFalse(FakeWorker.instances[0].running)
        self.assertEqual(start_button.state, "normal")
        self.assertEqual(stop_button.state, "disabled")
        self.assertEqual([spinbox.state for spinbox in FakeSpinbox.instances], ["normal", "normal"])
        self.assertEqual(self._status_var().get(), "Stopped")

    def test_minimized_start_refuses_worker_and_warns(self):
        app.find_roblox_window = lambda: (123, app.STATUS_MINIMIZED)
        app.main()
        start_button = self._acknowledge_risk_and_get_start_button()

        start_button.command()

        self.assertEqual(FakeWorker.instances, [])
        self.assertEqual(FakeMessagebox.warnings, [(app.WARN_MINIMIZED_TITLE, app.WARN_MINIMIZED)])
        self.assertEqual(self._status_var().get(), "Refused: Roblox is minimized")
        self.assertEqual(self._hint_var().get(), app.HINT_MINIMIZED)

    def test_start_normalizes_interval_before_not_found_refusal(self):
        app.main()
        interval_min_var, interval_sec_var = FakeVar.instances[:2]
        interval_min_var.set("1000")
        interval_sec_var.set("60")
        app.find_roblox_window = lambda: (None, app.STATUS_NOT_FOUND)
        start_button = self._acknowledge_risk_and_get_start_button()

        start_button.command()

        self.assertEqual(FakeWorker.instances, [])
        self.assertEqual(interval_min_var.get(), "999")
        self.assertEqual(interval_sec_var.get(), "59")
        self.assertEqual(self._status_var().get(), app.MSG_ROBLOX_NOT_FOUND)
        hint = self._hint_var().get()
        self.assertIn(app.HINT_NOT_FOUND, hint)
        self.assertIn("Interval adjusted to 999m 59s.", hint)


    def test_successful_scheduled_action_keeps_running_status_and_shows_action_hint(self):
        action_calls = []
        done_calls = []
        app.find_roblox_window = lambda: (123, None)
        app.run_action = lambda _hwnd: action_calls.append(_hwnd)
        app.main()
        root = self._last_root()
        start_button = self._acknowledge_risk_and_get_start_button()
        start_button.command()
        worker = FakeWorker.instances[0]

        worker.schedule_action(123, lambda: done_calls.append("done"))
        root.after_calls[-1][1]()

        self.assertEqual(action_calls, [123])
        self.assertEqual(done_calls, ["done"])
        self.assertEqual(self._status_var().get(), "Running")
        self.assertEqual(self._hint_var().get(), app.MSG_ACTION_SENT)

    def test_foreground_skip_status_shows_retry_hint(self):
        root, worker = self._start_app_worker()

        worker.on_status(app.MSG_FOREGROUND_SKIPPED)
        root.after_calls[-1][1]()

        self.assertEqual(self._status_var().get(), app.MSG_FOREGROUND_SKIPPED)
        self.assertEqual(self._hint_var().get(), app.HINT_FOREGROUND_SKIPPED)

    def test_foreground_error_during_action_shows_retry_hint(self):
        done_calls = []

        def raise_foreground(_hwnd):
            raise app.RobloxForegroundError(app.MSG_FOREGROUND_SKIPPED)

        app.run_action = raise_foreground
        root, worker = self._start_app_worker()

        worker.schedule_action(123, lambda: done_calls.append("done"))
        root.after_calls[-1][1]()

        self.assertEqual(done_calls, ["done"])
        self.assertEqual(self._status_var().get(), app.MSG_FOREGROUND_SKIPPED)
        self.assertEqual(self._hint_var().get(), app.HINT_FOREGROUND_SKIPPED)

    def test_mid_run_backend_error_pauses_worker_without_modal(self):
        root, worker = self._start_app_worker()
        start_button = self._start_button()
        stop_button = next(button for button in FakeButton.instances if button.text == "Stop")

        worker.on_status(app.MSG_BACKEND_ERROR)
        root.after_calls[-1][1]()

        self.assertFalse(worker.running)
        self.assertEqual(start_button.state, "normal")
        self.assertEqual(stop_button.state, "disabled")
        self.assertEqual([spinbox.state for spinbox in FakeSpinbox.instances], ["normal", "normal"])
        self.assertEqual(self._status_var().get(), app.MSG_BACKEND_ERROR)
        self.assertEqual(self._hint_var().get(), app.HINT_BACKEND_ERROR)
        self.assertEqual(FakeMessagebox.warnings, [])

    def test_backend_error_during_action_pauses_worker_and_finishes(self):
        done_calls = []
        find_results = [(123, None), (None, app.STATUS_BACKEND_ERROR)]
        app.find_roblox_window = lambda: find_results.pop(0)
        app.main()
        root = self._last_root()
        start_button = self._acknowledge_risk_and_get_start_button()
        stop_button = next(button for button in FakeButton.instances if button.text == "Stop")
        start_button.command()
        worker = FakeWorker.instances[0]

        worker.schedule_action(123, lambda: done_calls.append("done"))
        root.after_calls[-1][1]()

        self.assertFalse(worker.running)
        self.assertEqual(start_button.state, "normal")
        self.assertEqual(stop_button.state, "disabled")
        self.assertEqual([spinbox.state for spinbox in FakeSpinbox.instances], ["normal", "normal"])
        self.assertEqual(self._status_var().get(), app.MSG_BACKEND_ERROR)
        self.assertEqual(self._hint_var().get(), app.HINT_BACKEND_ERROR)
        self.assertEqual(FakeMessagebox.warnings, [])
        self.assertEqual(done_calls, ["done"])

    def test_backend_exception_during_action_pauses_worker_and_finishes(self):
        done_calls = []

        def raise_backend(_hwnd):
            raise app.RobloxBackendError("state boom")

        app.run_action = raise_backend
        app.main()
        root = self._last_root()
        start_button = self._acknowledge_risk_and_get_start_button()
        stop_button = next(button for button in FakeButton.instances if button.text == "Stop")
        start_button.command()
        worker = FakeWorker.instances[0]

        worker.schedule_action(123, lambda: done_calls.append("done"))
        root.after_calls[-1][1]()

        self.assertFalse(worker.running)
        self.assertEqual(start_button.state, "normal")
        self.assertEqual(stop_button.state, "disabled")
        self.assertEqual([spinbox.state for spinbox in FakeSpinbox.instances], ["normal", "normal"])
        self.assertEqual(self._status_var().get(), app.MSG_BACKEND_ERROR)
        self.assertEqual(self._hint_var().get(), app.HINT_BACKEND_ERROR)
        self.assertEqual(FakeMessagebox.warnings, [])
        self.assertEqual(done_calls, ["done"])


    def test_mid_run_minimized_status_pauses_worker_and_warns(self):
        action_done_calls = []
        find_results = [(123, None), (123, app.STATUS_MINIMIZED)]
        app.find_roblox_window = lambda: find_results.pop(0)
        app.main()
        root = self._last_root()
        start_button = self._acknowledge_risk_and_get_start_button()
        stop_button = next(button for button in FakeButton.instances if button.text == "Stop")
        start_button.command()
        worker = FakeWorker.instances[0]

        worker.schedule_action(123, lambda: action_done_calls.append("done"))
        root.after_calls[-1][1]()

        self.assertFalse(worker.running)
        self.assertEqual(start_button.state, "normal")
        self.assertEqual(stop_button.state, "disabled")
        self.assertEqual([spinbox.state for spinbox in FakeSpinbox.instances], ["normal", "normal"])
        self.assertEqual(self._status_var().get(), "Paused: Roblox is minimized")
        self.assertEqual(self._hint_var().get(), app.HINT_MINIMIZED)
        self.assertEqual(FakeMessagebox.warnings, [(app.WARN_MINIMIZED_TITLE, app.WARN_MINIMIZED)])
        self.assertEqual(action_done_calls, ["done"])

    def test_schedule_action_after_close_drops_without_after_and_finishes(self):
        root, worker = self._start_app_worker()
        root.protocols["WM_DELETE_WINDOW"]()
        done_calls = []

        worker.schedule_action(123, lambda: done_calls.append("done"))

        self.assertEqual(done_calls, ["done"])
        self.assertEqual(root.after_calls, [])
        self.assertFalse(worker.running)
        self.assertTrue(root.destroyed)

    def test_on_status_drops_when_root_after_raises_during_teardown(self):
        root, worker = self._start_app_worker()
        root.raise_on_after = True

        worker.on_status(app.MSG_BACKEND_ERROR)

        self.assertEqual(root.after_calls, [])

    def test_schedule_action_after_failure_reraises_without_finishing(self):
        root, worker = self._start_app_worker()
        root.raise_on_after = True
        done_calls = []

        with self.assertRaises(RuntimeError):
            worker.schedule_action(123, lambda: done_calls.append("done"))

        self.assertEqual(done_calls, [])


if __name__ == "__main__":
    unittest.main()
