#!/usr/bin/env python3
"""Generate CATALOG.md from skill and subagent frontmatter."""

from __future__ import annotations

import argparse
from pathlib import Path

from list_content import collect


HEADER = """\
# Content catalog

Generated from `SKILL.md` and subagent frontmatter with:

```bash
python scripts/list_content.py --format markdown
```

Items marked "internal" apply only to this repository. The `install` bundle
leaves them out; install one explicitly with `add <name>`.

"""


def generate_catalog(repo_root: Path) -> str:
    content = collect(repo_root)
    lines = [HEADER]
    lines.append("| Kind | Name | Description |")
    lines.append("| --- | --- | --- |")
    for item in content:
        description = item["description"].replace("|", "\\|")
        lines.append(f"| {item['kind']} | `{item['name']}` | {description} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate CATALOG.md from content frontmatter.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path (default: <repo-root>/CATALOG.md)",
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    output = (args.output or root / "CATALOG.md").resolve()
    catalog = generate_catalog(root)
    output.write_text(catalog, encoding="utf-8")
    print(f"generated {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
