#!/usr/bin/env python3
import re
import sys
from pathlib import Path
from urllib.parse import unquote


LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
SKIPPED_PREFIXES = ("#", "http://", "https://", "mailto:")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    failures: list[str] = []
    for document in sorted(root.glob("*.md")):
        text = document.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            target = target.strip().strip("<>")
            if not target or target.startswith(SKIPPED_PREFIXES):
                continue
            path_text = unquote(target.split("#", 1)[0])
            if path_text and not (document.parent / path_text).exists():
                failures.append(f"{document.name}: missing local target {target}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("Local Markdown links are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
