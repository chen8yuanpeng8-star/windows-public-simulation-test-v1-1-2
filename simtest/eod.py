from dataclasses import dataclass


@dataclass(frozen=True)
class Checkpoint:
    name: str
    status: str


def close_day(checkpoints, process_exit_code):
    rows = tuple(checkpoints)
    failures = tuple(row.name for row in rows if row.status == "FAIL")
    missing = tuple(row.name for row in rows if row.status in {"MISSED", "NOT_EVALUATED"})
    if process_exit_code != 0:
        status = "FAILED_PROCESS_EXIT"
    elif not rows or failures or missing:
        status = "FAILED_INCOMPLETE"
    else:
        status = "COMPLETE"
    return {
        "status": status,
        "failure_checkpoints": failures,
        "missing_checkpoints": missing,
        "process_exit_code": process_exit_code,
    }
