import re
import tomllib
import unittest
from pathlib import Path

import app


REPO_ROOT = Path(__file__).resolve().parents[1]
PYINSTALLER_COMMAND = (
    "pyinstaller --onefile --noconsole --name antiAFK4roblox "
    "--hidden-import=pythoncom --hidden-import=win32com.client main.py"
)


EXPECTED_WORKFLOW_ACTION_REFS = {
    "ci.yml": (
        "actions/checkout@v4",
        "actions/setup-python@v5",
    ),
    "release.yml": (
        "actions/checkout@v4",
        "actions/setup-python@v5",
        "softprops/action-gh-release@v2",
    ),
}
RELEASE_ZIP_PATH = "dist/antiAFK4roblox-${{ steps.version.outputs.tag }}-windows.zip"
RELEASE_CHECKSUM_PATH = f"{RELEASE_ZIP_PATH}.sha256"


def read_workflow(name):
    return (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")




class ReleaseContractTests(unittest.TestCase):
    def test_release_workflow_can_parse_app_version(self):
        app_source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")

        match = re.search(r"(?m)^APP_VERSION\s*=\s*[\"']([^\"']+)[\"']", app_source)

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.group(1), app.APP_VERSION)
        self.assertEqual(app.WINDOW_TITLE, f"{app.APP_NAME} v{app.APP_VERSION}")

    def test_readme_top_risk_paragraph_matches_app_warning(self):
        readme_lines = (REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines()
        requirements_index = readme_lines.index("## Requirements")
        top_section = readme_lines[:requirements_index]
        risk_lines = [line for line in top_section if app.RISK_WARNING in line]

        self.assertEqual(
            risk_lines,
            [f"This tool automates Roblox input. {app.RISK_WARNING}"],
        )


    def test_readme_documents_statuses_and_validation_commands(self):
        readme_source = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        for expected_text in (
            "## Statuses",
            "Paused: Roblox is minimized",
            "After a successful anti-AFK action, the Status remains Running and the hint text shows Action sent.",
            "python -m py_compile main.py app.py anti_afk.py",
            'python -m unittest discover -s tests -t . -p "test*.py" -v',
        ):
            with self.subTest(expected_text=expected_text):
                self.assertIn(expected_text, readme_source)
        self.assertIn(
            "Direct dependencies are pinned in requirements.txt and requirements-build.txt for repeatable Windows installs.",
            readme_source,
        )
        self.assertNotIn(
            "| Action sent | The last anti-AFK action completed and focus restoration was attempted. |",
            readme_source,
        )
        self.assertNotIn(
            "Dependencies are pinned in requirements.txt and requirements-build.txt for reproducible Windows builds.",
            readme_source,
        )

    def test_dependency_versions_are_single_source_and_pinned(self):
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = pyproject["project"]

        self.assertNotIn("version", project)
        self.assertEqual(project["dynamic"], ["version"])
        self.assertEqual(
            pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"],
            "app.APP_VERSION",
        )
        self.assertEqual(project["dependencies"], ["pywin32==312"])
        self.assertEqual(
            project["optional-dependencies"]["build"],
            ["pyinstaller==6.21.0"],
        )
        self.assertEqual(
            [
                line.strip()
                for line in (REPO_ROOT / "requirements.txt")
                .read_text(encoding="utf-8")
                .splitlines()
            ],
            ["pywin32==312"],
        )
        self.assertEqual(
            [
                line.strip()
                for line in (REPO_ROOT / "requirements-build.txt")
                .read_text(encoding="utf-8")
                .splitlines()
            ],
            ["pyinstaller==6.21.0"],
        )


    def test_pyinstaller_hidden_import_command_is_documented(self):
        workflow_source = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        readme_source = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(PYINSTALLER_COMMAND, workflow_source)
        self.assertIn(PYINSTALLER_COMMAND, readme_source)

    def test_workflow_actions_use_version_tags(self):
        workflow_sources = {
            "ci.yml": read_workflow("ci.yml"),
            "release.yml": read_workflow("release.yml"),
        }

        for workflow_name, workflow_source in workflow_sources.items():
            with self.subTest(workflow=workflow_name):
                for expected_ref in EXPECTED_WORKFLOW_ACTION_REFS[workflow_name]:
                    self.assertIn(expected_ref, workflow_source)

    def test_release_workflow_writes_and_uploads_checksum(self):
        release_source = read_workflow("release.yml")

        self.assertIn("Write package checksum", release_source)
        self.assertIn("Get-FileHash -Algorithm SHA256", release_source)
        self.assertIn(".zip.sha256", release_source)

        release_step_match = re.search(
            r"(?ms)^\s*- name:\s*Create GitHub release\b(?P<body>.*?)(?=^\s*- name:|\Z)",
            release_source,
        )
        self.assertIsNotNone(release_step_match)
        assert release_step_match is not None
        files_block_match = re.search(
            r"(?ms)^\s*files:\s*\|\s*\n(?P<files>(?:^\s+\S.*\n?)+)",
            release_step_match.group("body"),
        )
        self.assertIsNotNone(files_block_match)
        assert files_block_match is not None
        files_block = files_block_match.group("files")

        self.assertIn(RELEASE_ZIP_PATH, files_block)
        self.assertIn(RELEASE_CHECKSUM_PATH, files_block)

    def test_release_tag_guard_resets_expected_missing_tag_exit_code(self):
        release_source = read_workflow("release.yml")

        self.assertIn(
            'if ($LASTEXITCODE -ne 0) { throw "Could not fetch tags before checking release tag $tag." }',
            release_source,
        )
        self.assertIn("$tagCheckExitCode = $LASTEXITCODE", release_source)
        self.assertIn(
            'if ($tagCheckExitCode -eq 0) { throw "Release tag $tag already exists. Bump APP_VERSION in app.py before dispatching." }',
            release_source,
        )
        self.assertIn(
            'if ($tagCheckExitCode -ne 1) { throw "Could not check release tag $tag (git rev-parse exited $tagCheckExitCode)." }',
            release_source,
        )
        self.assertIn("$global:LASTEXITCODE = 0", release_source)
        self.assertNotIn(
            'if ($LASTEXITCODE -eq 0) { throw "Release tag $tag already exists. Bump APP_VERSION in app.py before dispatching." }',
            release_source,
        )


if __name__ == "__main__":
    unittest.main()
