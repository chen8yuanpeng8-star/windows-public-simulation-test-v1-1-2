import hashlib
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
REPARSE_POINT = 0x400
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def safe_relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise SystemExit(f"unsafe manifest path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise SystemExit(f"unsafe manifest path: {value!r}")
    if path.parts[0] == ".git":
        raise SystemExit(f"unsafe manifest path: {value!r}")
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_reparse_point(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & REPARSE_POINT)


def files_on_disk():
    found = set()
    stack = [(ROOT, "")]
    while stack:
        directory, relative = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise SystemExit(f"cannot inspect package directory {relative or '. '}: {exc}") from exc
        for entry in entries:
            name = entry.name
            rel = f"{relative}/{name}" if relative else name
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise SystemExit(f"cannot inspect package entry {rel}: {exc}") from exc
            if not relative and name == ".git":
                if is_reparse_point(info):
                    raise SystemExit("root .git metadata must not be a symlink or reparse point")
                continue
            if is_reparse_point(info):
                raise SystemExit(f"unsafe symlink or reparse point: {rel}")
            if stat.S_ISDIR(info.st_mode):
                stack.append((Path(entry.path), rel))
            elif stat.S_ISREG(info.st_mode):
                found.add(rel)
            else:
                raise SystemExit(f"unsafe non-regular package entry: {rel}")
    return found


def main():
    manifest = json.loads((ROOT / "TEST_MANIFEST.json").read_text(encoding="utf-8"))
    audit = json.loads((ROOT / "PUBLIC_RELEASE_AUDIT.json").read_text(encoding="utf-8"))
    file_items = manifest.get("files")
    metadata_items = manifest.get("metadata_files")
    if not isinstance(file_items, list) or not isinstance(metadata_items, list):
        raise SystemExit("invalid manifest file inventory")

    expected_names = [safe_relative_path(item.get("path") if isinstance(item, dict) else None).as_posix() for item in file_items]
    metadata_names = [safe_relative_path(name).as_posix() for name in metadata_items]
    if len(set(expected_names)) != len(expected_names) or len(set(metadata_names)) != len(metadata_names):
        raise SystemExit("duplicate manifest path")
    if set(expected_names) & set(metadata_names):
        raise SystemExit("manifest payload and metadata paths overlap")
    expected = set(expected_names) | set(metadata_names)
    actual = files_on_disk()
    if actual != expected:
        raise SystemExit(f"file list mismatch; extra={sorted(actual-expected)} missing={sorted(expected-actual)}")

    for item, name in zip(file_items, expected_names):
        expected_hash = item.get("sha256")
        if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
            raise SystemExit(f"invalid manifest sha256: {name}")
        if sha(ROOT.joinpath(*PurePosixPath(name).parts)) != expected_hash:
            raise SystemExit(f"manifest hash mismatch: {name}")

    audit_files = audit.get("files")
    if not isinstance(audit_files, list):
        raise SystemExit("invalid audit file inventory")
    audit_names = [safe_relative_path(item.get("path") if isinstance(item, dict) else None).as_posix() for item in audit_files]
    if len(set(audit_names)) != len(audit_names) or set(audit_names) != expected:
        raise SystemExit("audit inventory mismatch")

    sums = {}
    for line in (ROOT / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise SystemExit(f"invalid checksum line: {line!r}") from exc
        safe_name = safe_relative_path(name).as_posix()
        if not SHA256_RE.fullmatch(digest) or safe_name in sums:
            raise SystemExit(f"invalid or duplicate checksum entry: {name}")
        sums[safe_name] = digest
    if set(sums) != expected - {"SHA256SUMS.txt"}:
        raise SystemExit("checksum inventory mismatch")
    for name, expected_hash in sums.items():
        if sha(ROOT.joinpath(*PurePosixPath(name).parts)) != expected_hash:
            raise SystemExit(f"checksum mismatch: {name}")
    print(f"MANIFEST_OK files={len(actual)} hashes={len(sums)}")


if __name__ == "__main__":
    main()
