import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = json.loads((ROOT / "PUBLIC_RELEASE_AUDIT.json").read_text(encoding="utf-8"))
EXPECTED = {item["path"] for item in AUDIT["files"]}
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


def main():
    actual_files = [p for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    actual = {p.relative_to(ROOT).as_posix() for p in actual_files}
    if actual != EXPECTED:
        raise SystemExit(f"file allowlist failed; extra={sorted(actual-EXPECTED)} missing={sorted(EXPECTED-actual)}")
    findings = []
    for path in actual_files:
        name = path.name.casefold()
        if path.suffix.casefold() in DENIED_SUFFIXES or name.startswith(".env"):
            findings.append(f"forbidden filename: {path.relative_to(ROOT).as_posix()}")
            continue
        data = path.read_bytes()
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(f"non-UTF8 file: {path.relative_to(ROOT).as_posix()}")
            continue
        for pattern in PATTERNS:
            if pattern.search(content):
                findings.append(f"sensitive-pattern match: {path.relative_to(ROOT).as_posix()} / {pattern.pattern}")
    if findings:
        raise SystemExit("\n".join(findings))
    print(f"SENSITIVE_SCAN_OK files={len(actual)}")


if __name__ == "__main__":
    main()
