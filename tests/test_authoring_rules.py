"""Tests for the authoring rules in scripts/validate_content.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import validate_content as vc  # noqa: E402

GOOD_SKILL_DESCRIPTION = (
    "Investigate a failing test by reproducing it and testing hypotheses. "
    "Use when the cause is unknown."
)
SKILLS = {"systematic-debugging", "review-change"}
AGENTS = {"reviewer", "debugger"}


def fence(*lines: str, info: str = "bash") -> str:
    return "\n".join([f"```{info}", *lines, "```"])


class DescriptionRuleTests(unittest.TestCase):
    def check(self, raw_line: str, description: str) -> list[str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "SKILL.md"
            path.write_text(f"---\nname: demo\n{raw_line}\n---\n# Demo\n", encoding="utf-8")
            return vc.validate_description(path, description)

    def test_accepts_quoted_description_with_trigger_cue(self) -> None:
        raw = f'description: "{GOOD_SKILL_DESCRIPTION}"'
        self.assertEqual(self.check(raw, GOOD_SKILL_DESCRIPTION), [])

    def test_rejects_short_description_without_cue(self) -> None:
        errors = self.check('description: "Build endpoints."', "Build endpoints.")
        self.assertTrue(any("80 to 600" in error for error in errors))
        self.assertTrue(any("when to use" in error for error in errors))

    def test_rejects_angle_brackets(self) -> None:
        text = GOOD_SKILL_DESCRIPTION + " Not for <x>."
        errors = self.check(f'description: "{text}"', text)
        self.assertTrue(any("< or >" in error for error in errors))

    def test_rejects_unquoted_yaml_syntax(self) -> None:
        text = "Debug things: reproduce first. " + GOOD_SKILL_DESCRIPTION
        errors = self.check(f"description: {text}", text)
        self.assertTrue(any("wrap it in double quotes" in error for error in errors))


class AgentRoleRuleTests(unittest.TestCase):
    def test_read_only_agent_must_end_with_read_only(self) -> None:
        self.assertEqual(vc.validate_agent_role("Reviews diffs. Read-only.", "Read, Grep, Glob, Bash"), [])
        self.assertTrue(vc.validate_agent_role("Reviews diffs.", "Read, Grep, Glob, Bash"))

    def test_write_tools_require_write_scoped_ending(self) -> None:
        tools = "Read, Grep, Glob, Edit, Write, Bash"
        self.assertEqual(vc.validate_agent_role("Builds slices. Edits only assigned paths.", tools), [])
        self.assertTrue(vc.validate_agent_role("Builds slices. Read-only.", tools))

    def test_is_write_scoped_is_case_insensitive(self) -> None:
        self.assertTrue(vc.is_write_scoped("Read, edit"))
        self.assertFalse(vc.is_write_scoped("Read, Grep, Glob, Bash, WebFetch"))


class ReferenceRuleTests(unittest.TestCase):
    def test_known_references_pass(self) -> None:
        text = "Use the `review-change` skill, or delegate to the `reviewer` subagent."
        self.assertEqual(vc.validate_references(text, SKILLS, AGENTS), [])

    def test_unknown_and_wrong_kind_references_fail(self) -> None:
        text = "Use the `missing-skill` skill.\nUse the `review-change` subagent.\n"
        errors = vc.validate_references(text, SKILLS, AGENTS)
        self.assertEqual(len(errors), 2)
        self.assertIn("line 1", errors[0])
        self.assertIn("line 2", errors[1])

    def test_references_wrapped_across_lines_are_checked(self) -> None:
        errors = vc.validate_references("route this to the\n`ghost` subagent.", SKILLS, AGENTS)
        self.assertTrue(errors)

    def test_internal_items_cannot_be_referenced(self) -> None:
        internal = next(iter(vc.INTERNAL_ITEMS))
        errors = vc.validate_references(f"Use the `{internal}` skill.", SKILLS | {internal}, AGENTS)
        self.assertTrue(any("internal" in error for error in errors))

    def test_code_blocks_and_non_kind_code_spans_are_ignored(self) -> None:
        text = "Use `api-contract` headings and `Bash`.\n" + fence("echo `ghost` skill")
        self.assertEqual(vc.validate_references(text, SKILLS, AGENTS), [])


class ScriptReferenceRuleTests(unittest.TestCase):
    def test_repository_scripts_and_handoff_templates_are_rejected(self) -> None:
        text = "Run `python scripts/validate_handoff.py` and copy templates/handoffs/api-contract.md."
        errors = vc.validate_script_references(text, {"validate_handoff.py"}, None)
        self.assertEqual(len(errors), 2)

    def test_consumer_example_scripts_are_allowed(self) -> None:
        text = "For example `./scripts/reconcile.sh` if the project has one."
        self.assertEqual(vc.validate_script_references(text, {"validate_handoff.py"}, None), [])

    def test_bundled_scripts_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            skill_dir = Path(temporary_directory)
            (skill_dir / "scripts").mkdir()
            (skill_dir / "scripts" / "check.py").write_text("", encoding="utf-8")
            text = "Run scripts/check.py, then scripts/missing.py."
            errors = vc.validate_script_references(text, set(), skill_dir)
            self.assertEqual(errors, ["bundled script is missing: scripts/missing.py"])


class DestructiveCommandRuleTests(unittest.TestCase):
    def test_flags_destructive_commands_in_code_blocks(self) -> None:
        commands = [
            "git checkout -- src/",
            "git reset --hard HEAD",
            "rm -rf ${CREATED_FILES}",
            "npx prisma migrate reset --force",
            "pkill -f k6",
            "git push --force origin main",
            "pnpm test || pytest || cargo test",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(vc.validate_destructive_commands(fence(command)))

    def test_allows_prose_guardrails_and_safe_commands(self) -> None:
        text = "Never run `git reset --hard`.\n" + fence(
            "git checkout --theirs -- package-lock.json",
            "rm -rf node_modules",
            'for i in $(seq 1 10); do npm test || echo "FAIL $i"; done',
        )
        self.assertEqual(vc.validate_destructive_commands(text), [])

    def test_approval_comment_and_marker_exempt_commands(self) -> None:
        gated = fence("kubectl rollout undo deployment/api  # requires approval")
        marked = "<!-- agentkit-lint: allow-destructive -->\n" + fence("git reset --hard")
        self.assertEqual(vc.validate_destructive_commands(gated), [])
        self.assertEqual(vc.validate_destructive_commands(marked), [])


class HandoffRuleTests(unittest.TestCase):
    LABELS = "\n".join(
        [
            "**Changed contract:** x",
            "**Files / systems affected:** x",
            "**Evidence and tests:** x",
            "**Risks / rollback:** x",
            "**What the next agent needs:** x",
        ]
    )

    def handoff(self, headings: list[str]) -> str:
        body = ["# Verification report", *[f"## {heading}" for heading in headings], self.LABELS]
        return "<!-- handoff: verification-report -->\n" + fence(*body, info="markdown")

    def test_complete_handoff_passes(self) -> None:
        text = self.handoff(["Scope", "Commands and results", "Evidence", "Limitations", "Handoff"])
        self.assertEqual(vc.validate_handoffs(text), [])

    def test_missing_heading_is_reported(self) -> None:
        errors = vc.validate_handoffs(self.handoff(["Scope", "Evidence", "Limitations", "Handoff"]))
        self.assertEqual(len(errors), 1)
        self.assertIn("commands and results", errors[0])

    def test_marker_quoted_in_prose_is_ignored(self) -> None:
        self.assertEqual(vc.validate_handoffs("Add `<!-- handoff: api-contract -->` before the block."), [])

    def test_unknown_kind_and_missing_block_are_reported(self) -> None:
        self.assertTrue(vc.validate_handoffs("<!-- handoff: not-a-kind -->\n"))
        self.assertTrue(vc.validate_handoffs("<!-- handoff: verification-report -->\nNo block here.\n"))


class MarkdownSplitTests(unittest.TestCase):
    def test_links_inside_code_are_not_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = root / "doc.md"
            document.write_text(
                "Inline `[x](missing.md)` and a block:\n" + fence("[y](also-missing.md)", info="markdown")
                + "\n[real](gone.md)\n",
                encoding="utf-8",
            )
            errors = vc.validate_local_links(root, document)
            self.assertEqual(errors, ["broken local link: gone.md"])

    def test_tilde_fences_and_previous_line_are_tracked(self) -> None:
        prose, blocks = vc.split_markdown("intro\n~~~\ncode\n~~~\nafter\n")
        self.assertEqual(prose, ["intro", "", "", "", "after"])
        self.assertEqual(blocks, [(2, [(3, "code")], "intro")])


if __name__ == "__main__":
    unittest.main()
