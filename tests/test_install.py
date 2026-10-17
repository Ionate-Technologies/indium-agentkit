from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "scripts" / "install.py"
CHECKER = REPO_ROOT / "scripts" / "check_install.py"


class InstallTests(unittest.TestCase):
    def run_installer(
        self, *arguments: str, home: Path
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["HOME"] = str(home)
        environment["USERPROFILE"] = str(home)
        return subprocess.run(
            [sys.executable, str(INSTALLER), *arguments, "--home", str(home)],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def test_project_scope_installs_only_selected_skill_and_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            home = root / "home"
            project.mkdir()
            home.mkdir()

            result = self.run_installer(
                "--scope",
                "project",
                "--project-dir",
                str(project),
                "--target",
                "codex",
                "--item",
                "systematic-debugging",
                "--mode",
                "copy",
                home=home,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            installed = project / ".codex" / "skills"
            self.assertEqual(
                sorted(path.name for path in installed.iterdir()),
                ["systematic-debugging"],
            )
            self.assertFalse((project / ".claude").exists())
            self.assertFalse((home / ".codex").exists())
            self.assertFalse((home / ".claude").exists())

            diagnostic = subprocess.run(
                [
                    sys.executable,
                    str(CHECKER),
                    "--project",
                    str(project),
                    "--target",
                    "codex",
                    "--item",
                    "systematic-debugging",
                    "--mode",
                    "copy",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(diagnostic.returncode, 0, diagnostic.stdout)

    def project_install(self, project: Path, home: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.run_installer(
            "--scope", "project", "--project-dir", str(project), "--target", "claude",
            "--mode", "copy", *extra, home=home,
        )

    def test_bundle_excludes_internal_items_but_add_installs_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            home = root / "home"
            project.mkdir()
            home.mkdir()

            bundle = self.project_install(project, home, "--item", "all", "--include-context")
            self.assertEqual(bundle.returncode, 0, bundle.stderr)
            skills = project / ".claude" / "skills"
            self.assertTrue((skills / "systematic-debugging").is_dir())
            self.assertFalse((skills / "author-agentkit-content").exists())

            check = subprocess.run(
                [sys.executable, str(CHECKER), "--project", str(project), "--target", "claude",
                 "--item", "all", "--mode", "copy"],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(check.returncode, 0, check.stdout)
            self.assertNotIn("author-agentkit-content", check.stdout)

            single = self.project_install(project, home, "--item", "author-agentkit-content")
            self.assertEqual(single.returncode, 0, single.stderr)
            self.assertTrue((skills / "author-agentkit-content" / "SKILL.md").is_file())

    def test_force_replaces_stale_copies_without_touching_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            home = root / "home"
            project.mkdir()
            home.mkdir()
            skills = project / ".claude" / "skills"
            stale = skills / "systematic-debugging"
            stale.mkdir(parents=True)
            (stale / "SKILL.md").write_text("old content\n", encoding="utf-8")
            unrelated = skills / "my-own-skill"
            unrelated.mkdir()
            (unrelated / "SKILL.md").write_text("mine\n", encoding="utf-8")
            context = project / "CLAUDE.md"
            context.write_text("project rules\n", encoding="utf-8")

            skipped = self.project_install(project, home, "--item", "systematic-debugging")
            self.assertEqual(skipped.returncode, 0, skipped.stderr)
            self.assertIn("skipped", skipped.stdout)
            self.assertIn("--force", skipped.stdout)
            self.assertEqual((stale / "SKILL.md").read_text(encoding="utf-8"), "old content\n")

            forced = self.project_install(
                project, home, "--item", "all", "--include-context", "--force"
            )
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertIn("replaced", forced.stdout)
            source = REPO_ROOT / "skills" / "systematic-debugging" / "SKILL.md"
            self.assertEqual(
                (stale / "SKILL.md").read_text(encoding="utf-8"),
                source.read_text(encoding="utf-8"),
            )
            self.assertEqual((unrelated / "SKILL.md").read_text(encoding="utf-8"), "mine\n")
            self.assertEqual(context.read_text(encoding="utf-8"), "project rules\n")

    def test_cursor_add_generates_only_the_selected_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            home = root / "home"
            project.mkdir()
            home.mkdir()

            result = self.run_installer(
                "--scope",
                "project",
                "--project-dir",
                str(project),
                "--target",
                "cursor",
                "--item",
                "systematic-debugging",
                "--mode",
                "copy",
                home=home,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            rules = project / ".cursor" / "rules"
            self.assertEqual(
                sorted(path.name for path in rules.iterdir()),
                ["systematic-debugging.mdc"],
            )

    def test_project_context_follows_the_selected_architecture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            home = root / "home"
            project.mkdir()
            home.mkdir()

            result = self.run_installer(
                "--scope",
                "project",
                "--project-dir",
                str(project),
                "--target",
                "claude",
                "--item",
                "all",
                "--mode",
                "copy",
                "--include-context",
                home=home,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((project / "CLAUDE.md").is_file())
            self.assertFalse((project / "AGENTS.md").exists())
            self.assertTrue((project / ".claude" / "skills").is_dir())
            self.assertTrue((project / ".claude" / "agents").is_dir())
            self.assertFalse((home / ".claude").exists())

    def test_user_scope_honors_target_without_project_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            home = root / "home"
            home.mkdir()

            result = self.run_installer(
                "--scope",
                "user",
                "--target",
                "codex",
                "--item",
                "systematic-debugging",
                "--mode",
                "copy",
                home=home,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(
                (home / ".codex" / "skills" / "systematic-debugging" / "SKILL.md").is_file()
            )
            self.assertFalse((home / ".claude").exists())
            self.assertFalse((home / ".gemini").exists())

    def test_unknown_item_fails_without_creating_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            home = root / "home"
            project.mkdir()
            home.mkdir()

            result = self.run_installer(
                "--scope",
                "project",
                "--project-dir",
                str(project),
                "--target",
                "codex",
                "--item",
                "does-not-exist",
                home=home,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("unknown skill or subagent", result.stderr)
            self.assertEqual(list(project.iterdir()), [])

    def test_subagent_fails_for_target_without_native_agent_support(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            home = root / "home"
            project.mkdir()
            home.mkdir()

            result = self.run_installer(
                "--scope",
                "project",
                "--project-dir",
                str(project),
                "--target",
                "codex",
                "--item",
                "reviewer",
                home=home,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("no native installation path", result.stderr)
            self.assertEqual(list(project.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
