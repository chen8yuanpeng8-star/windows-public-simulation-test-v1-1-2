from pathlib import Path


def run_with_failure_log(operation, log_path):
    path = Path(log_path)
    try:
        result = operation()
        return {"exit_code": 0, "result": result}
    except Exception as exc:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        return {"exit_code": 1, "result": None, "log_path": str(path)}

