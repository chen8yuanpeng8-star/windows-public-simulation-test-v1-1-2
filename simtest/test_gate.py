from dataclasses import dataclass


@dataclass(frozen=True)
class GateResult:
    full_pass: bool
    passed: int
    skipped: int
    failed: int
    reasons: tuple[str, ...]


def evaluate_python_counts(*, run, failures, errors, skipped, minimum):
    if min(run, failures, errors, skipped, minimum) < 0:
        raise ValueError("test counts and minimum must be non-negative")
    failed = failures + errors
    passed = max(0, run - failed - skipped)
    reasons = []
    if run < minimum:
        reasons.append(f"Python tests below minimum: {run} < {minimum}")
    if failed:
        reasons.append(f"Python failures/errors: {failed}")
    if skipped:
        reasons.append(f"Python skips prevent full pass: {skipped}")
    return GateResult(not reasons, passed, skipped, failed, tuple(reasons))


def evaluate_powershell_counts(*, passed, failed, minimum):
    if min(passed, failed, minimum) < 0:
        raise ValueError("test counts and minimum must be non-negative")
    reasons = []
    if passed < minimum:
        reasons.append(f"PowerShell assertions below minimum: {passed} < {minimum}")
    if failed:
        reasons.append(f"PowerShell failures: {failed}")
    return GateResult(not reasons, passed, 0, failed, tuple(reasons))
