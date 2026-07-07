import unittest

import anti_afk


class EnvironmentReadinessTests(unittest.TestCase):
    def test_missing_pywin32_reports_exact_install_guidance(self):
        original_win32gui = anti_afk.win32gui
        original_win32process = anti_afk.win32process
        original_win32api = anti_afk.win32api

        try:
            anti_afk.win32gui = None
            anti_afk.win32process = None
            anti_afk.win32api = None

            ok, message = anti_afk.is_environment_ready()

            self.assertFalse(ok)
            self.assertEqual(
                message,
                "Missing dependency: pywin32 (listed in requirements.txt). Install with:\npip install -r requirements.txt",
            )
        finally:
            anti_afk.win32gui = original_win32gui
            anti_afk.win32process = original_win32process
            anti_afk.win32api = original_win32api


if __name__ == "__main__":
    unittest.main()
