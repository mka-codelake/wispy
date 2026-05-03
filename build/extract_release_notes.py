"""Extract a release-notes section from CHANGELOG.md for a given tag/version.

Used by the release workflows so the GitHub Release body shows the curated
"## [X.Y.Z]" block from CHANGELOG.md instead of an auto-generated git
diff. Run with --help for usage.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional


def extract_section(changelog_text: str, version: str) -> Optional[str]:
    """Return the body of the `## [<version>]` section, or None if not found.

    The body excludes the heading line itself and is stripped of trailing
    whitespace. The link-reference table at the bottom of the changelog
    (`[X.Y.Z]: <url>`) is also excluded — it serves the in-repo doc, not
    the GitHub Release body.
    """
    escaped = re.escape(version)
    # Match the heading line plus everything until the next "## [" heading
    # OR until the link-reference table starts (`[X.Y.Z]: http`) OR EOF.
    pattern = re.compile(
        rf"(?ms)^## \[{escaped}\][^\r\n]*\r?\n(.*?)"
        rf"(?=^## \[|^\[\d+\.\d+\.\d+\]: |\Z)"
    )
    match = pattern.search(changelog_text)
    if not match:
        return None
    return match.group(1).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--tag",
        required=True,
        help="git tag (with or without leading 'v'), e.g. 'v0.4.3' or '0.4.3'",
    )
    parser.add_argument(
        "--changelog",
        default="CHANGELOG.md",
        help="path to CHANGELOG.md (default: CHANGELOG.md in cwd)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="where to write the extracted section (UTF-8, no BOM)",
    )
    args = parser.parse_args()

    version = args.tag.lstrip("v")
    changelog_path = Path(args.changelog)
    if not changelog_path.is_file():
        print(f"CHANGELOG not found: {changelog_path}", file=sys.stderr)
        return 1

    text = changelog_path.read_text(encoding="utf-8")
    section = extract_section(text, version)
    if section is None:
        print(
            f"No CHANGELOG entry for version {version} found in {changelog_path}",
            file=sys.stderr,
        )
        return 1

    Path(args.output).write_text(section + "\n", encoding="utf-8")
    # Use ASCII arrow rather than U+2192 — Python's stdout on Windows defaults
    # to cp1252, which cannot encode the Unicode arrow. Crashing the script
    # over a print() pretty-arrow was a real CI bug in v0.4.4 first attempt.
    print(f"Extracted release notes for v{version} -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
