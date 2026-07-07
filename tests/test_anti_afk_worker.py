import sys
import types
import unittest

import anti_afk


class AntiAFKWorkerPollOnceTests(unittest.TestCase):
    def test_poll_once_maps_find_window_statuses(self):
        cases = [
            ((None, anti_afk.STATUS_BACKEND_ERROR), [anti_afk.MSG_BACKEND_ERROR]),
            ((None, anti_afk.STATUS_MINIMIZED), [anti_afk.MSG_ROBLOX_MINIMIZED]),
            ((None, anti_afk.STATUS_NOT_FOUND), [anti_afk.MSG_ROBLOX_NOT_FOUND]),
            ((None, anti_afk.STATUS_OK), [anti_afk.MSG_ROBLOX_NOT_FOUND]),
        ]

        for (hwnd, status), expected_statuses in cases:
            with self.subTest(hwnd=hwnd, status=status):
                statuses = []
                worker = anti_afk.AntiAFKWorker(
                    1,
                    on_status=statuses.append,
                    find_window=lambda hwnd=hwnd, status=status: (hwnd, status),
                )

                worker._poll_once()

                self.assertEqual(statuses, expected_statuses)

    def test_poll_once_emits_action_sent_after_successful_action(self):
        statuses = []
        action_hwnds = []
        worker = anti_afk.AntiAFKWorker(
            1,
            on_status=statuses.append,
            find_window=lambda: (123, anti_afk.STATUS_OK),
            action=lambda hwnd: action_hwnds.append(hwnd),
        )

        worker._poll_once()

        self.assertEqual(action_hwnds, [123])
        self.assertEqual(statuses, [anti_afk.MSG_ACTION_SENT])

    def test_poll_once_maps_minimized_exception_to_minimized_message(self):
        statuses = []

        def action(_hwnd):
            raise anti_afk.RobloxWindowMinimizedError("Roblox window is minimized")

        worker = anti_afk.AntiAFKWorker(
            1,
            on_status=statuses.append,
            find_window=lambda: (123, anti_afk.STATUS_OK),
            action=action,
        )

        worker._poll_once()

        self.assertEqual(statuses, [anti_afk.MSG_ROBLOX_MINIMIZED])

    def test_poll_once_maps_backend_exception_to_backend_error_message(self):
        statuses = []

        def action(_hwnd):
            raise anti_afk.RobloxBackendError("state boom")

        worker = anti_afk.AntiAFKWorker(
            1,
            on_status=statuses.append,
            find_window=lambda: (123, anti_afk.STATUS_OK),
            action=action,
        )

        worker._poll_once()

        self.assertEqual(statuses, [anti_afk.MSG_BACKEND_ERROR])


    def test_poll_once_maps_unavailable_exception_to_not_found_message(self):
        statuses = []

        def action(_hwnd):
            raise anti_afk.RobloxWindowUnavailableError("Roblox window is no longer valid")

        worker = anti_afk.AntiAFKWorker(
            1,
            on_status=statuses.append,
            find_window=lambda: (123, anti_afk.STATUS_OK),
            action=action,
        )

        worker._poll_once()

        self.assertEqual(statuses, [anti_afk.MSG_ROBLOX_NOT_FOUND])


    def test_poll_once_maps_unexpected_action_errors_to_error_status(self):
        statuses = []

        def action(_hwnd):
            raise RuntimeError("boom")

        worker = anti_afk.AntiAFKWorker(
            1,
            on_status=statuses.append,
            find_window=lambda: (123, anti_afk.STATUS_OK),
            action=action,
        )

        worker._poll_once()

        self.assertEqual(statuses, ["Error: boom"])

    def test_poll_once_maps_find_window_exception_to_backend_error(self):
        statuses = []

        def find_window():
            raise RuntimeError("boom")

        worker = anti_afk.AntiAFKWorker(
            1,
            on_status=statuses.append,
            find_window=find_window,
        )

        worker._poll_once()

        self.assertEqual(statuses, [anti_afk.MSG_BACKEND_ERROR])


class AntiAFKWorkerSchedulingTests(unittest.TestCase):
    def test_poll_once_applies_backpressure_until_action_done(self):
        statuses = []
        scheduled_calls = []

        def schedule_action(hwnd, action_done):
            scheduled_calls.append((hwnd, action_done))

        worker = anti_afk.AntiAFKWorker(
            1,
            on_status=statuses.append,
            schedule_action=schedule_action,
            find_window=lambda: (123, anti_afk.STATUS_OK),
        )

        worker._poll_once()
        worker._poll_once()

        self.assertEqual(len(scheduled_calls), 1)
        self.assertEqual(scheduled_calls[0][0], 123)
        self.assertEqual(statuses, [])

        first_done = scheduled_calls[0][1]
        first_done()

        worker._poll_once()

        self.assertEqual([hwnd for hwnd, _done in scheduled_calls], [123, 123])
        self.assertEqual(statuses, [])

    def test_poll_once_reports_scheduler_errors_and_allows_retry(self):
        statuses = []
        scheduled_hwnds = []

        def schedule_action(hwnd, _action_done):
            scheduled_hwnds.append(hwnd)
            raise RuntimeError("boom")

        worker = anti_afk.AntiAFKWorker(
            1,
            on_status=statuses.append,
            schedule_action=schedule_action,
            find_window=lambda: (123, anti_afk.STATUS_OK),
        )

        worker._poll_once()
        worker._poll_once()

        self.assertEqual(scheduled_hwnds, [123, 123])
        self.assertEqual(statuses, ["Error: boom", "Error: boom"])

    def test_poll_once_finishes_once_when_scheduler_done_then_raises(self):
        statuses = []
        scheduled_hwnds = []

        def schedule_action(hwnd, action_done):
            scheduled_hwnds.append(hwnd)
            action_done()
            raise RuntimeError("boom")

        worker = anti_afk.AntiAFKWorker(
            1,
            on_status=statuses.append,
            schedule_action=schedule_action,
            find_window=lambda: (123, anti_afk.STATUS_OK),
        )
        original_finish_action = worker._finish_action
        finish_calls = []

        def finish_action_spy():
            finish_calls.append("finish")
            original_finish_action()

        worker._finish_action = finish_action_spy

        worker._poll_once()

        self.assertEqual(scheduled_hwnds, [123])
        self.assertEqual(finish_calls, ["finish"])
        self.assertEqual(statuses, ["Error: boom"])

        worker._poll_once()

        self.assertEqual(scheduled_hwnds, [123, 123])
        self.assertEqual(finish_calls, ["finish", "finish"])
        self.assertEqual(statuses, ["Error: boom", "Error: boom"])




class ProcessLookupComTests(unittest.TestCase):
    def _install_fake_com_modules(self, coinitialize, couninitialize=lambda: None):
        events = []

        class FakePythonCom(types.SimpleNamespace):
            def CoInitialize(self):
                events.append("initialize")
                coinitialize()

            def CoUninitialize(self):
                events.append("uninitialize")
                couninitialize()

        class FakeProcess:
            ProcessId = 123

        class FakeWmi:
            def ExecQuery(self, query):
                events.append(("query", query))
                return [FakeProcess()]

        class FakeClient(types.SimpleNamespace):
            def GetObject(self, moniker):
                events.append(("get_object", moniker))
                return FakeWmi()

        fake_client = FakeClient()
        fake_win32com = types.ModuleType("win32com")
        setattr(fake_win32com, "client", fake_client)
        modules = {
            "pythoncom": FakePythonCom(),
            "win32com": fake_win32com,
            "win32com.client": fake_client,
        }
        originals = {name: sys.modules.get(name) for name in modules}
        missing = {name for name, value in originals.items() if value is None}
        sys.modules.update(modules)
        return events, originals, missing

    def _restore_modules(self, originals, missing):
        for name, module in originals.items():
            if name in missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_process_lookup_initializes_and_uninitializes_com(self):
        events, originals, missing = self._install_fake_com_modules(lambda: None)
        try:
            self.assertEqual(
                anti_afk._get_pids_by_process_name(anti_afk.ROBLOX_PROCESS_NAME),
                ([123], None),
            )
        finally:
            self._restore_modules(originals, missing)

        self.assertEqual(events[0], "initialize")
        self.assertEqual(events[-1], "uninitialize")
        self.assertIn(("get_object", "winmgmts:"), events)

    def test_process_lookup_does_not_uninitialize_when_initialize_fails(self):
        events, originals, missing = self._install_fake_com_modules(
            lambda: (_ for _ in ()).throw(RuntimeError("init boom"))
        )
        try:
            pids, error = anti_afk._get_pids_by_process_name(anti_afk.ROBLOX_PROCESS_NAME)
        finally:
            self._restore_modules(originals, missing)

        self.assertEqual(pids, [])
        self.assertEqual(error, "init boom")
        self.assertEqual(events, ["initialize"])

    def test_process_lookup_preserves_pid_result_when_uninitialize_fails(self):
        events, originals, missing = self._install_fake_com_modules(
            lambda: None,
            couninitialize=lambda: (_ for _ in ()).throw(RuntimeError("cleanup boom")),
        )
        try:
            pids, error = anti_afk._get_pids_by_process_name(anti_afk.ROBLOX_PROCESS_NAME)
        finally:
            self._restore_modules(originals, missing)

        expected_query = "SELECT ProcessId FROM Win32_Process WHERE Name = '%s'" % anti_afk.ROBLOX_PROCESS_NAME
        self.assertEqual(pids, [123])
        self.assertIsNone(error)
        self.assertIn(("query", expected_query), events)
        self.assertLess(events.index(("query", expected_query)), events.index("uninitialize"))

class FindRobloxWindowMappingTests(unittest.TestCase):
    def _find_window_with_pid_result(self, pid_result):
        original_get_pids = anti_afk._get_pids_by_process_name
        original_win32gui = anti_afk.win32gui
        original_win32process = anti_afk.win32process

        try:
            anti_afk._get_pids_by_process_name = lambda _process_name: pid_result
            anti_afk.win32gui = object()
            anti_afk.win32process = object()
            return anti_afk.find_roblox_window()
        finally:
            anti_afk._get_pids_by_process_name = original_get_pids
            anti_afk.win32gui = original_win32gui
            anti_afk.win32process = original_win32process

    def _find_window_with_modules(
        self,
        pid_result,
        windows,
        minimized_hwnds=(),
        visible_errors=(),
        pid_errors=(),
        minimized_errors=(),
        parent_hwnds=(),
        owner_hwnds=(),
        owner_errors=(),
    ):
        original_get_pids = anti_afk._get_pids_by_process_name
        original_win32gui = anti_afk.win32gui
        original_win32process = anti_afk.win32process
        original_is_window_minimized = anti_afk.is_window_minimized
        visible_by_hwnd = {hwnd: visible for hwnd, visible, _pid in windows}
        pid_by_hwnd = {hwnd: pid for hwnd, _visible, pid in windows}
        minimized_hwnds = set(minimized_hwnds)
        visible_errors = set(visible_errors)
        pid_errors = set(pid_errors)
        minimized_errors = set(minimized_errors)
        parent_hwnds = set(parent_hwnds)
        owner_hwnds = set(owner_hwnds)
        owner_errors = set(owner_errors)
        include_ownership_checks = bool(parent_hwnds or owner_hwnds or owner_errors)
        owner_query_commands = []

        def enum_windows(callback, arg):
            for hwnd, _visible, _pid in windows:
                if callback(hwnd, arg) is False:
                    break

        def is_window_visible(hwnd):
            if hwnd in visible_errors:
                raise RuntimeError("visible boom")
            return visible_by_hwnd[hwnd]

        def get_window_thread_process_id(hwnd):
            if hwnd in pid_errors:
                raise RuntimeError("pid boom")
            return 0, pid_by_hwnd[hwnd]

        def get_parent(hwnd):
            return hwnd + 1000 if hwnd in parent_hwnds else 0

        def get_window(hwnd, command):
            owner_query_commands.append(command)
            if hwnd in owner_errors:
                raise RuntimeError("owner boom")
            if command == anti_afk.GW_OWNER and hwnd in owner_hwnds:
                return hwnd + 2000
            return 0

        def is_window_minimized(hwnd):
            if hwnd in minimized_errors:
                raise RuntimeError("minimized boom")
            return hwnd in minimized_hwnds

        try:
            anti_afk._get_pids_by_process_name = lambda _process_name: pid_result
            win32gui_kwargs = {
                "IsWindowVisible": is_window_visible,
                "EnumWindows": enum_windows,
            }
            if include_ownership_checks:
                win32gui_kwargs["GetParent"] = get_parent
                win32gui_kwargs["GetWindow"] = get_window
            anti_afk.win32gui = types.SimpleNamespace(**win32gui_kwargs)
            anti_afk.win32process = types.SimpleNamespace(
                GetWindowThreadProcessId=get_window_thread_process_id,
            )
            anti_afk.is_window_minimized = is_window_minimized
            result = anti_afk.find_roblox_window()
            self.assertTrue(
                all(command == anti_afk.GW_OWNER for command in owner_query_commands)
            )
            return result
        finally:
            anti_afk._get_pids_by_process_name = original_get_pids
            anti_afk.win32gui = original_win32gui
            anti_afk.win32process = original_win32process
            anti_afk.is_window_minimized = original_is_window_minimized

    def test_find_roblox_window_maps_pid_lookup_errors_to_backend_error(self):
        self.assertEqual(
            self._find_window_with_pid_result(([], "boom")),
            (None, anti_afk.STATUS_BACKEND_ERROR),
        )

    def test_find_roblox_window_maps_empty_pid_list_to_not_found(self):
        self.assertEqual(
            self._find_window_with_pid_result(([], None)),
            (None, anti_afk.STATUS_NOT_FOUND),
        )

    def test_find_roblox_window_returns_visible_matching_hwnd(self):
        self.assertEqual(
            self._find_window_with_modules(
                ([123], None),
                [(10, True, 123)],
            ),
            (10, anti_afk.STATUS_OK),
        )

    def test_find_roblox_window_ignores_invisible_matching_hwnd(self):
        self.assertEqual(
            self._find_window_with_modules(
                ([123], None),
                [(10, False, 123), (11, True, 123)],
            ),
            (11, anti_afk.STATUS_OK),
        )

    def test_find_roblox_window_maps_single_minimized_match_to_minimized(self):
        self.assertEqual(
            self._find_window_with_modules(
                ([123], None),
                [(10, True, 123)],
                minimized_hwnds=(10,),
            ),
            (10, anti_afk.STATUS_MINIMIZED),
        )

    def test_find_roblox_window_prefers_restored_match_over_earlier_minimized_match(self):
        self.assertEqual(
            self._find_window_with_modules(
                ([123], None),
                [(10, True, 123), (11, True, 123)],
                minimized_hwnds=(10,),
            ),
            (11, anti_afk.STATUS_OK),
        )

    def test_find_roblox_window_ignores_parented_match_for_later_unowned_match(self):
        self.assertEqual(
            self._find_window_with_modules(
                ([123], None),
                [(10, True, 123), (11, True, 123)],
                parent_hwnds=(10,),
            ),
            (11, anti_afk.STATUS_OK),
        )

    def test_find_roblox_window_ignores_owned_match_for_later_unowned_match(self):
        self.assertEqual(
            self._find_window_with_modules(
                ([123], None),
                [(10, True, 123), (11, True, 123)],
                owner_hwnds=(10,),
            ),
            (11, anti_afk.STATUS_OK),
        )

    def test_find_roblox_window_maps_all_ownership_query_failures_to_backend_error(self):
        self.assertEqual(
            self._find_window_with_modules(
                ([123], None),
                [(10, True, 123), (11, True, 123)],
                owner_errors=(10, 11),
            ),
            (None, anti_afk.STATUS_BACKEND_ERROR),
        )

    def test_find_roblox_window_continues_after_window_query_errors_to_valid_restored_candidate(self):
        self.assertEqual(
            self._find_window_with_modules(
                ([123], None),
                [(10, True, 123), (11, True, 123), (12, True, 123)],
                visible_errors=(10,),
                pid_errors=(11,),
            ),
            (12, anti_afk.STATUS_OK),
        )

    def test_find_roblox_window_maps_all_window_query_failures_to_backend_error(self):
        self.assertEqual(
            self._find_window_with_modules(
                ([123], None),
                [(10, True, 123), (11, True, 123)],
                visible_errors=(10,),
                pid_errors=(11,),
            ),
            (None, anti_afk.STATUS_BACKEND_ERROR),
        )

    def test_find_roblox_window_maps_minimized_query_failure_to_backend_error(self):
        self.assertEqual(
            self._find_window_with_modules(
                ([123], None),
                [(10, True, 123)],
                minimized_errors=(10,),
            ),
            (None, anti_afk.STATUS_BACKEND_ERROR),
        )

    def test_find_roblox_window_maps_all_minimized_candidates_to_first_minimized(self):
        self.assertEqual(
            self._find_window_with_modules(
                ([123], None),
                [(10, True, 123), (11, True, 123)],
                minimized_hwnds=(10, 11),
            ),
            (10, anti_afk.STATUS_MINIMIZED),
        )


class ActionSequenceTests(unittest.TestCase):
    def _replace_user32(self, fake_user32):
        had_windll = hasattr(anti_afk.ctypes, "windll")
        if had_windll:
            original_windll = anti_afk.ctypes.windll
            had_user32 = hasattr(original_windll, "user32")
            original_user32 = original_windll.user32 if had_user32 else None
            setattr(original_windll, "user32", fake_user32)
        else:
            original_windll = None
            had_user32 = False
            original_user32 = None
            anti_afk.ctypes.windll = types.SimpleNamespace(user32=fake_user32)

        def restore():
            if not had_windll:
                del anti_afk.ctypes.windll
            elif had_user32:
                setattr(original_windll, "user32", original_user32)
            else:
                delattr(original_windll, "user32")

        return restore

    def test_press_key_vk_sends_scancode_down_then_keyup_input(self):
        import ctypes
        original_sleep = anti_afk.time.sleep

        class FakeUser32:
            def __init__(self):
                self.send_input_calls = []

            def MapVirtualKeyW(self, _vk, _map_type):
                return 0x17

            def SendInput(self, count, input_pointer, input_size):
                input_struct = anti_afk.ctypes.cast(
                    input_pointer,
                    anti_afk.ctypes.POINTER(anti_afk.INPUT),
                ).contents
                keyboard_input = input_struct.union.ki
                self.send_input_calls.append(
                    {
                        "count": count,
                        "flags": keyboard_input.dwFlags,
                        "size": input_size,
                        "scan": keyboard_input.wScan,
                    }
                )
                return 1

        fake_user32 = FakeUser32()
        restore_user32 = self._replace_user32(fake_user32)

        try:
            anti_afk.time.sleep = lambda _seconds: None

            anti_afk._press_key_vk(anti_afk.VK_I)
        finally:
            restore_user32()
            anti_afk.time.sleep = original_sleep

        self.assertEqual(len(fake_user32.send_input_calls), 2)
        expected_input_size = ctypes.sizeof(anti_afk.INPUT)
        self.assertEqual(
            [call["size"] for call in fake_user32.send_input_calls],
            [expected_input_size, expected_input_size],
        )
        self.assertEqual(
            [call["scan"] for call in fake_user32.send_input_calls],
            [0x17, 0x17],
        )
        first_flags = fake_user32.send_input_calls[0]["flags"]
        second_flags = fake_user32.send_input_calls[1]["flags"]
        self.assertTrue(first_flags & anti_afk.KEYEVENTF_SCANCODE)
        self.assertFalse(first_flags & anti_afk.KEYEVENTF_KEYUP)
        self.assertTrue(second_flags & anti_afk.KEYEVENTF_SCANCODE)
        self.assertTrue(second_flags & anti_afk.KEYEVENTF_KEYUP)

    def test_press_key_vk_maps_sendinput_failure_to_backend_error(self):
        original_sleep = anti_afk.time.sleep

        class FakeUser32:
            def MapVirtualKeyW(self, _vk, _map_type):
                return 0x17

            def SendInput(self, _count, _input_pointer, _input_size):
                return 0

        fake_user32 = FakeUser32()
        restore_user32 = self._replace_user32(fake_user32)
        try:
            anti_afk.time.sleep = lambda _seconds: None

            with self.assertRaisesRegex(anti_afk.RobloxBackendError, "SendInput failed"):
                anti_afk._press_key_vk(anti_afk.VK_I)
        finally:
            restore_user32()
            anti_afk.time.sleep = original_sleep

    def test_action_i_o_presses_i_then_o(self):
        original_press_key_vk = anti_afk._press_key_vk
        original_get_foreground_window = anti_afk._get_foreground_window
        pressed_keys = []

        try:
            anti_afk._press_key_vk = pressed_keys.append
            anti_afk._get_foreground_window = lambda: 123
            anti_afk._action_i_o(123)
        finally:
            anti_afk._press_key_vk = original_press_key_vk
            anti_afk._get_foreground_window = original_get_foreground_window

        self.assertEqual(pressed_keys, [anti_afk.VK_I, anti_afk.VK_O])

    def test_action_i_o_raises_foreground_error_if_focus_changes_before_o(self):
        original_press_key_vk = anti_afk._press_key_vk
        original_get_foreground_window = anti_afk._get_foreground_window
        pressed_keys = []
        foreground_sequence = [123, 999]

        try:
            anti_afk._press_key_vk = pressed_keys.append
            anti_afk._get_foreground_window = lambda: foreground_sequence.pop(0)
            with self.assertRaises(anti_afk.RobloxForegroundError):
                anti_afk._action_i_o(123)
        finally:
            anti_afk._press_key_vk = original_press_key_vk
            anti_afk._get_foreground_window = original_get_foreground_window

        self.assertEqual(pressed_keys, [anti_afk.VK_I])



class RunActionTests(unittest.TestCase):
    def test_run_action_raises_foreground_error_and_restores_previous_window(self):
        original_win32gui = anti_afk.win32gui
        original_is_window_minimized = anti_afk.is_window_minimized
        original_get_foreground_window = anti_afk._get_foreground_window
        original_bring_to_front = anti_afk._bring_to_front
        original_wait_for_foreground = anti_afk._wait_for_foreground
        original_action_i_o = anti_afk._action_i_o
        restore_calls = []
        action_calls = []

        try:
            anti_afk.win32gui = types.SimpleNamespace(
                IsWindow=lambda _hwnd: True,
                IsWindowVisible=lambda _hwnd: True,
                SetForegroundWindow=restore_calls.append,
            )
            anti_afk.is_window_minimized = lambda _hwnd: False
            anti_afk._get_foreground_window = lambda: 55
            anti_afk._bring_to_front = lambda _hwnd: None
            anti_afk._wait_for_foreground = lambda _hwnd: False
            anti_afk._action_i_o = lambda _hwnd: action_calls.append("action")

            with self.assertRaises(anti_afk.RobloxForegroundError):
                anti_afk.run_action(123)
        finally:
            anti_afk.win32gui = original_win32gui
            anti_afk.is_window_minimized = original_is_window_minimized
            anti_afk._get_foreground_window = original_get_foreground_window
            anti_afk._bring_to_front = original_bring_to_front
            anti_afk._wait_for_foreground = original_wait_for_foreground
            anti_afk._action_i_o = original_action_i_o

        self.assertEqual(action_calls, [])
        self.assertEqual(restore_calls, [55])

    def test_run_action_sends_action_and_restores_previous_window_on_success(self):
        original_win32gui = anti_afk.win32gui
        original_is_window_minimized = anti_afk.is_window_minimized
        original_get_foreground_window = anti_afk._get_foreground_window
        original_bring_to_front = anti_afk._bring_to_front
        original_wait_for_foreground = anti_afk._wait_for_foreground
        original_action_i_o = anti_afk._action_i_o
        restore_calls = []
        action_hwnds = []

        try:
            anti_afk.win32gui = types.SimpleNamespace(
                IsWindow=lambda _hwnd: True,
                IsWindowVisible=lambda _hwnd: True,
                SetForegroundWindow=restore_calls.append,
            )
            anti_afk.is_window_minimized = lambda _hwnd: False
            anti_afk._get_foreground_window = lambda: 55
            anti_afk._bring_to_front = lambda _hwnd: None
            anti_afk._wait_for_foreground = lambda _hwnd: True
            anti_afk._action_i_o = action_hwnds.append

            anti_afk.run_action(123)
        finally:
            anti_afk.win32gui = original_win32gui
            anti_afk.is_window_minimized = original_is_window_minimized
            anti_afk._get_foreground_window = original_get_foreground_window
            anti_afk._bring_to_front = original_bring_to_front
            anti_afk._wait_for_foreground = original_wait_for_foreground
            anti_afk._action_i_o = original_action_i_o

        self.assertEqual(action_hwnds, [123])
        self.assertIn(55, restore_calls)

    def test_run_action_maps_minimized_query_failure_to_backend_error(self):
        original_win32gui = anti_afk.win32gui
        original_is_window_minimized = anti_afk.is_window_minimized

        try:
            anti_afk.win32gui = types.SimpleNamespace(IsWindow=lambda _hwnd: True)

            def is_window_minimized(_hwnd):
                raise RuntimeError("state boom")

            anti_afk.is_window_minimized = is_window_minimized

            with self.assertRaises(anti_afk.RobloxBackendError):
                anti_afk.run_action(123)
        finally:
            anti_afk.win32gui = original_win32gui
            anti_afk.is_window_minimized = original_is_window_minimized

    def test_worker_maps_foreground_error_to_foreground_skipped_message(self):
        statuses = []

        def action(_hwnd):
            raise anti_afk.RobloxForegroundError(anti_afk.MSG_FOREGROUND_SKIPPED)

        worker = anti_afk.AntiAFKWorker(
            1,
            on_status=statuses.append,
            find_window=lambda: (123, anti_afk.STATUS_OK),
            action=action,
        )

        worker._poll_once()

        self.assertEqual(statuses, [anti_afk.MSG_FOREGROUND_SKIPPED])

if __name__ == "__main__":
    unittest.main()
