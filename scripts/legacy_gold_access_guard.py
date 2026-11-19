"""Fail-closed guard for unsupported legacy scripts that touch SIH gold data.

These scripts are retained for historical reference. They must not be used for
current training, model selection, evaluation, dataset mutation, or auditing.
The guard intentionally has no opt-in environment variable: any future use
requires a reviewed replacement workflow and explicit code change.
"""

from __future__ import annotations

import sys
from pathlib import Path


def deny_legacy_gold_tool(script_path: str | Path) -> None:
    name = Path(script_path).name
    print(
        f"BLOCKED: legacy tool {name} is disabled because it reads or writes the "
        "sealed SIH gold set. Use a reviewed non-gold workflow instead.",
        file=sys.stderr,
    )
    raise SystemExit(2)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: legacy_gold_access_guard.py <legacy-script>", file=sys.stderr)
        raise SystemExit(2)
    deny_legacy_gold_tool(sys.argv[1])
