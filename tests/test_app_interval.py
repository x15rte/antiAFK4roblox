import sys
import types
import unittest


def _load_validate_interval_values():
    try:
        from app import validate_interval_values
        return validate_interval_values
    except ImportError as exc:
        if getattr(exc, "name", None) not in {"tkinter", "_tkinter"}:
            raise

    original_tkinter = sys.modules.get("tkinter")
    original_ttk = sys.modules.get("tkinter.ttk")
    original_messagebox = sys.modules.get("tkinter.messagebox")

    tkinter_stub = types.ModuleType("tkinter")
    tkinter_stub.__path__ = []
    ttk_stub = types.ModuleType("tkinter.ttk")
    messagebox_stub = types.ModuleType("tkinter.messagebox")
    setattr(tkinter_stub, "ttk", ttk_stub)
    setattr(tkinter_stub, "messagebox", messagebox_stub)

    sys.modules["tkinter"] = tkinter_stub
    sys.modules["tkinter.ttk"] = ttk_stub
    sys.modules["tkinter.messagebox"] = messagebox_stub

    try:
        from app import validate_interval_values
        return validate_interval_values
    finally:
        sys.modules.pop("app", None)
        if original_tkinter is None:
            sys.modules.pop("tkinter", None)
        else:
            sys.modules["tkinter"] = original_tkinter
        if original_ttk is None:
            sys.modules.pop("tkinter.ttk", None)
        else:
            sys.modules["tkinter.ttk"] = original_ttk
        if original_messagebox is None:
            sys.modules.pop("tkinter.messagebox", None)
        else:
            sys.modules["tkinter.messagebox"] = original_messagebox


validate_interval_values = _load_validate_interval_values()


class ValidateIntervalValuesTests(unittest.TestCase):
    def test_validate_interval_values_contract_cases(self):
        cases = [
            (("15", "0"), (15, 0, False)),
            (("abc", "0"), (15, 0, True)),
            (("-1", "99"), (0, 59, True)),
            (("0", "0"), (15, 0, True)),
            ((" 5 ", " 7 "), (5, 7, False)),
            (("999", "59"), (999, 59, False)),
            (("1000", "60"), (999, 59, True)),
            (("", "10"), (15, 0, True)),
            (("1", ""), (15, 0, True)),
        ]

        for (minutes_text, seconds_text), expected in cases:
            with self.subTest(minutes_text=minutes_text, seconds_text=seconds_text):
                self.assertEqual(
                    validate_interval_values(minutes_text, seconds_text),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
