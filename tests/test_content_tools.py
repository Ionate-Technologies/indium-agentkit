from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ContentToolTests(unittest.TestCase):
    def run_script(self, script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / script), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_scaffold_creates_valid_skill_and_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill = self.run_script(
                "scaffold_content.py", "skill", "demo-skill", "--description", "Demo skill description", "--repo-root", str(root)
            )
            agent = self.run_script(
                "scaffold_content.py", "agent", "demo-agent", "--description", "Demo agent description", "--repo-root", str(root)
            )
            self.assertEqual(skill.returncode, 0, skill.stderr)
            self.assertEqual(agent.returncode, 0, agent.stderr)
            self.assertIn("name: demo-skill", (root / "skills" / "demo-skill" / "SKILL.md").read_text(encoding="utf-8"))
            agent_text = (root / "agents" / "demo-agent.md").read_text(encoding="utf-8")
            self.assertIn("name: demo-agent", agent_text)
            self.assertIn("Read-only.", agent_text)

            sys.path.insert(0, str(REPO_ROOT / "scripts"))
            try:
                import validate_content
            finally:
                sys.path.pop(0)
            self.assertEqual(validate_content.validate_skill(root / "skills" / "demo-skill"), [])
            self.assertEqual(validate_content.validate_agent(root / "agents" / "demo-agent.md"), [])

    def test_scaffold_marks_write_scoped_agents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            result = self.run_script(
                "scaffold_content.py", "agent", "demo-builder",
                "--description", "Implement assigned changes. Use when the parent assigns a bounded slice",
                "--tools", "Read, Grep, Glob, Edit, Write, Bash",
                "--repo-root", str(root),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            text = (root / "agents" / "demo-builder.md").read_text(encoding="utf-8")
            self.assertIn("bounded slice. Edits only assigned paths.", text)
            self.assertNotIn("Read-only.", text)

    def test_scaffold_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = self.run_script("scaffold_content.py", "skill", "demo", "--description", "Demo description", "--repo-root", str(root))
            second = self.run_script("scaffold_content.py", "skill", "demo", "--description", "Demo description", "--repo-root", str(root))
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("refusing to overwrite", second.stderr)

    def test_list_content_emits_json_inventory(self) -> None:
        result = self.run_script("list_content.py", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        inventory = json.loads(result.stdout)
        names = {item["name"] for item in inventory}
        self.assertTrue({"plan-change", "security-review", "migration-planner"}.issubset(names))

    def test_check_install_reports_missing_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = self.run_script("check_install.py", "--home", temporary_directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("collection directory is missing", result.stdout)


if __name__ == "__main__":
    unittest.main()
