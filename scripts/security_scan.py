import json
import os
import re
import stat
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
REPARSE_POINT = 0x400
DENIED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".pfx", ".key", ".env", ".log", ".csv"}
PATTERNS = [
    re.compile(r"(?i)\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"\s$]{8,}['\"]"),
    re.compile(r"(?i)\b[A-Z]:" + re.escape(chr(92))),
    re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"),
    re.compile(r"(?i)https?" + r"://[^/\s]+"),
]


def safe_relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise SystemExit(f"unsafe audit path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise SystemExit(f"unsafe audit path: {value!r}")
    if path.parts[0] == ".git":
        raise SystemExit(f"unsafe audit path: {value!r}")
    return path


def is_reparse_point(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & REPARSE_POINT)


def files_on_disk():
    found = []
    stack = [(ROOT, "")]
    while stack:
        directory, relative = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise SystemExit(f"cannot inspect package directory {relative or '. '}: {exc}") from exc
        for entry in entries:
            rel = f"{relative}/{entry.name}" if relative else entry.name
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise SystemExit(f"cannot inspect package entry {rel}: {exc}") from exc
            if not relative and entry.name == ".git":
                if is_reparse_point(info):
                    raise SystemExit("root .git metadata must not be a symlink or reparse point")
                continue
            if is_reparse_point(info):
                raise SystemExit(f"unsafe symlink or reparse point: {rel}")
            if stat.S_ISDIR(info.st_mode):
                stack.append((Path(entry.path), rel))
            elif stat.S_ISREG(info.st_mode):
                found.append((rel, Path(entry.path)))
            else:
                raise SystemExit(f"unsafe non-regular package entry: {rel}")
    return found


def main():
    audit = json.loads((ROOT / "PUBLIC_RELEASE_AUDIT.json").read_text(encoding="utf-8"))
    audit_files = audit.get("files")
    if not isinstance(audit_files, list):
        raise SystemExit("invalid audit file inventory")
    expected_names = [safe_relative_path(item.get("path") if isinstance(item, dict) else None).as_posix() for item in audit_files]
    if len(set(expected_names)) != len(expected_names):
        raise SystemExit("duplicate audit path")

    actual_files = files_on_disk()
    actual = {name for name, _ in actual_files}
    expected = set(expected_names)
    if actual != expected:
        raise SystemExit(f"file allowlist failed; extra={sorted(actual-expected)} missing={sorted(expected-actual)}")

    findings = []
    for relative, path in actual_files:
        name = path.name.casefold()
        if path.suffix.casefold() in DENIED_SUFFIXES or name.startswith(".env"):
            findings.append(f"forbidden filename: {relative}")
            continue
        data = path.read_bytes()
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(f"non-UTF8 file: {relative}")
            continue
        for pattern in PATTERNS:
            if pattern.search(content):
                findings.append(f"sensitive-pattern match: {relative} / {pattern.pattern}")
    if findings:
        raise SystemExit("\n".join(findings))
    print(f"SENSITIVE_SCAN_OK files={len(actual)}")


if __name__ == "__main__":
    main()
