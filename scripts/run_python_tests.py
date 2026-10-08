import json
from pathlib import Path
import sys
import unittest

from simtest.test_gate import evaluate_python_counts


MINIMUM_PYTHON_TESTS = 17


def main():
    root = Path(__file__).resolve().parents[1]
    suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    errors = len(result.errors)
    failures = len(result.failures)
    skipped = len(result.skipped)
    gate = evaluate_python_counts(
        run=result.testsRun,
        failures=failures,
        errors=errors,
        skipped=skipped,
        minimum=MINIMUM_PYTHON_TESTS,
    )
    payload = {
        "tests_run": result.testsRun,
        "passed": gate.passed,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "minimum": MINIMUM_PYTHON_TESTS,
        "full_pass": gate.full_pass,
        "reasons": list(gate.reasons),
        "exit_code": 0 if gate.full_pass else 1,
    }
    print("PYTHON_TEST_SUMMARY_JSON=" + json.dumps(payload, sort_keys=True))
    return payload["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
