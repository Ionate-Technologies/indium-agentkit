"""Tests for the Codex delegation packet adapter."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "codex_delegate.py"


class CodexDelegateTests(unittest.TestCase):
    def run_adapter(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_builds_structured_packet(self) -> None:
        result = self.run_adapter(
            "--agent", "reviewer", "--task", "Review the latest diff.", "--files", "src", "tests"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        packet = json.loads(result.stdout)
        self.assertEqual(packet["agent"]["name"], "reviewer")
        self.assertEqual(packet["task"], "Review the latest diff.")
        self.assertEqual(packet["allowed_files"], ["src", "tests"])
        self.assertIn("evidence-backed report", packet["prompt"])

    def test_write_mode_follows_declared_tools(self) -> None:
        for agent, expected in (("reviewer", "read-only"), ("backend-builder", "scoped")):
            with self.subTest(agent=agent):
                result = self.run_adapter("--agent", agent, "--task", "Inspect it.")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["write_mode"], expected)

    def test_unknown_agent_fails(self) -> None:
        result = self.run_adapter("--agent", "missing", "--task", "Inspect it.")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown agent", result.stderr)
