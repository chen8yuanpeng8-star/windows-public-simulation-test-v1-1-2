import argparse
import json
import sys

from simtest.test_gate import evaluate_powershell_counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--passed", type=int, required=True)
    parser.add_argument("--failed", type=int, required=True)
    parser.add_argument("--minimum", type=int, default=5)
    args = parser.parse_args()
    gate = evaluate_powershell_counts(passed=args.passed, failed=args.failed, minimum=args.minimum)
    print(json.dumps({"full_pass": gate.full_pass, "passed": gate.passed, "failed": gate.failed, "minimum": args.minimum, "reasons": list(gate.reasons)}, sort_keys=True))
    return 0 if gate.full_pass else 1


if __name__ == "__main__":
    sys.exit(main())
