from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "scripts" / "cli.js"


@unittest.skipUnless(shutil.which("node"), "Node.js is required for CLI tests")
class CliTests(unittest.TestCase):
    def run_cli(
        self, project: Path, home: Path, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["HOME"] = str(home)
        environment["USERPROFILE"] = str(home)
        return subprocess.run(
            ["node", str(CLI), *arguments],
            cwd=project,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def test_add_installs_one_skill_into_explicit_project_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            home = root / "home"
            project.mkdir()
            home.mkdir()

            result = self.run_cli(
                project,
                home,
                "add",
                "systematic-debugging",
                "--scope=project",
                "--target=codex",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            installed = project / ".codex" / "skills"
            self.assertEqual(
                sorted(path.name for path in installed.iterdir()),
                ["systematic-debugging"],
            )
            self.assertFalse((home / ".claude").exists())
            self.assertFalse((home / ".codex").exists())

    def test_auto_target_fails_closed_when_no_tool_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            home = root / "home"
            project.mkdir()
            home.mkdir()

            result = self.run_cli(project, home, "install", "--scope=project")

            self.assertEqual(result.returncode, 2)
            self.assertIn("No agent target was detected", result.stderr)
            self.assertEqual(list(project.iterdir()), [])
            self.assertEqual(list(home.iterdir()), [])

    def test_project_dir_controls_the_only_project_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launcher = root / "launcher"
            destination = root / "destination"
            home = root / "home"
            launcher.mkdir()
            destination.mkdir()
            home.mkdir()

            result = self.run_cli(
                launcher,
                home,
                "add",
                "systematic-debugging",
                "--scope=project",
                f"--project-dir={destination}",
                "--target=codex",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(
                (
                    destination
                    / ".codex"
                    / "skills"
                    / "systematic-debugging"
                    / "SKILL.md"
                ).is_file()
            )
            self.assertEqual(list(launcher.iterdir()), [])
            self.assertEqual(list(home.iterdir()), [])


    def test_install_bundle_skips_internal_items_and_passes_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            home = root / "home"
            project.mkdir()
            home.mkdir()

            first = self.run_cli(project, home, "install", "--scope=project", "--target=claude")
            self.assertEqual(first.returncode, 0, first.stderr)
            skills = project / ".claude" / "skills"
            self.assertTrue((skills / "review-change" / "SKILL.md").is_file())
            self.assertFalse((skills / "author-agentkit-content").exists())

            stale = skills / "review-change" / "SKILL.md"
            stale.write_text("old\n", encoding="utf-8")
            forced = self.run_cli(
                project, home, "install", "--scope=project", "--target=claude", "--force"
            )
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertNotEqual(stale.read_text(encoding="utf-8"), "old\n")

if __name__ == "__main__":
    unittest.main()
