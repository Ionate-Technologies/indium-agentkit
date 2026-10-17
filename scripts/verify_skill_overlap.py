#!/usr/bin/env python3
"""Report skill and subagent name collisions and near-duplicate triggers.

Name collisions are errors. Similar descriptions are advisory: they suggest two
items may trigger for the same request and should route to each other, but they
do not fail the run.
"""

from __future__ import annotations

import argparse
import re
import sys
from itertools import combinations
from pathlib import Path

from list_content import collect


STOPWORDS = frozenset(
    "a an and are as at be by for from in into is it its of on or that the this to use "
    "when with not before after their them they then than any each every".split()
)
DEFAULT_THRESHOLD = 0.35


def tokens(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.casefold()) if word not in STOPWORDS and len(word) > 2}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def find_overlaps(repo_root: Path, threshold: float = DEFAULT_THRESHOLD) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    content = collect(repo_root)
    errors: list[str] = []
    seen: set[str] = set()
    for item in content:
        if item["name"] in seen:
            errors.append(f"duplicate name: '{item['name']}'")
        seen.add(item["name"])

    warnings: list[str] = []
    for left, right in combinations(content, 2):
        if left["kind"].split()[0] != right["kind"].split()[0]:
            continue
        score = jaccard(tokens(left["description"]), tokens(right["description"]))
        if score >= threshold:
            warnings.append(
                f"similar descriptions ({score:.2f}): {left['kind']} '{left['name']}' "
                f"and '{right['name']}'; make their triggers distinct or route between them"
            )
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Report name collisions and near-duplicate triggers.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Description similarity that triggers a warning (default {DEFAULT_THRESHOLD})",
    )
    args = parser.parse_args()
    errors, warnings = find_overlaps(args.repo_root.resolve(), args.threshold)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"no name collisions; {len(warnings)} advisory similarity warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
