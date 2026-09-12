"""Run explicit product mutations; exit zero only when every oracle kills.

Usage: uv run python scripts/run_meeting_release_mutations.py --output <directory>
Logs and captured oracle failures go outside source control. No source is edited.
"""

import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    # Read case metadata without importing Qt before pytest's sandbox bootstrap.
    tree = ast.parse(
        (root / "tests/widgets/meeting_product_mutations.py").read_text(
            encoding="utf-8"
        )
    )
    cases = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "CASES"
            for target in node.targets
        )
    )
    args.output.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, scenario in cases.items():
        env = os.environ.copy()
        env["BUZZ_RELEASE_MUTATION"] = name
        xml = args.output.resolve() / f"{name}.xml"
        xml.unlink(missing_ok=True)
        evidence = args.output.resolve() / f"{name}.oracle.json"
        evidence.unlink(missing_ok=True)
        env["BUZZ_RELEASE_ORACLE"] = str(evidence)
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "tests.widgets.meeting_product_mutations",
            f"tests/widgets/meeting_product_e2e_test.py::test_product_{scenario}",
            "-q",
            "--tb=short",
            "-o",
            "log_cli=false",
            f"--junitxml={xml}",
        ]
        try:
            run = subprocess.run(
                command, cwd=root, env=env, capture_output=True, timeout=90
            )
            (args.output / f"{name}.log").write_bytes(run.stdout + run.stderr)
            observed = (
                json.loads(evidence.read_text(encoding="utf-8"))
                if evidence.exists()
                else None
            )
            # Only the named scenario's expected assertion/guard counts. An
            # unrelated failure, setup failure, crash or timeout never counts.
            status = (
                "KILLED"
                if run.returncode == 42
                and observed
                and observed["mutation"] == name
                and observed["nodeid"].endswith(f"::test_product_{scenario}")
                else "SURVIVES"
                if run.returncode == 0
                else "NOT TESTED"
            )
            results[name] = {
                "status": status,
                "exit": run.returncode,
                "oracle": observed["oracle"] if observed else None,
            }
        except subprocess.TimeoutExpired as exc:
            (args.output / f"{name}.log").write_bytes(
                (exc.stdout or b"") + (exc.stderr or b"")
            )
            results[name] = {"status": "NOT TESTED", "reason": "timeout"}
        print(name, results[name]["status"], flush=True)
    (args.output / "results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    return 0 if all(r["status"] == "KILLED" for r in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
