"""Turn a pytest log into GitHub annotations naming the tests that went wrong.

A job's log can only be downloaded when signed in, even for a public
repository, but annotations show on the run page and through the public API.
So failures are raised there by name instead of staying buried in the log.

Usage: python scripts/ci_annotate.py pytest.log LABEL
The log must come from `pytest -v -rf` (-v names each test as it starts, which
is what identifies a crash; -rf lists the failures at the end).
"""

import re
import sys
from pathlib import Path

FAILED = re.compile(r"^FAILED (\S+?)(?: - (.*))?$")
# -v writes "path::test " when a test starts and the result when it ends, so
# after a crash the last such line is the test that was running.
STARTED = re.compile(r"^(tests/\S+::\S+)")


def escape(text: str) -> str:
    """Workflow commands end at a newline and treat % specially."""
    return text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def annotate(log: str, label: str) -> int:
    lines = log.splitlines()
    count = 0
    for line in lines:
        match = FAILED.match(line.strip())
        if match:
            test, reason = match.group(1), match.group(2) or ""
            print(f"::error title={escape(label)}: test failed::{escape(test)} {escape(reason)}")
            count += 1
    if "Fatal Python error" in log:
        running = [m.group(1) for line in lines if (m := STARTED.match(line.strip()))]
        where = running[-1] if running else "(before any test started)"
        # The error shares a line with the test name -v printed before it.
        crash = log[log.index("Fatal Python error") :].splitlines()[0]
        print(f"::error title={escape(label)}: test run crashed::{escape(where)} {escape(crash)}")
        count += 1
    return count


def main() -> None:
    log_path, label = sys.argv[1], sys.argv[2]
    path = Path(log_path)
    if not path.exists():
        print(f"::error title={escape(label)}::no pytest log at {escape(log_path)}")
        return
    if annotate(path.read_text(encoding="utf-8", errors="replace"), label) == 0:
        print("No failing tests.")


if __name__ == "__main__":
    main()
