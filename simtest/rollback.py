import hashlib
from dataclasses import dataclass
from pathlib import Path
import tempfile


def _digest(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    files: dict
    existing_paths: frozenset


def snapshot_files(root, relative_paths):
    root = Path(root).resolve()
    if not root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError("rollback root must be inside the operating-system temporary directory")
    if not (root / ".simulation-only").is_file():
        raise ValueError("rollback is restricted to a marked simulation root")
    snapshot = {}
    existing_paths = frozenset(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )
    for relative in relative_paths:
        path = (root / relative).resolve()
        if root not in path.parents:
            raise ValueError("snapshot path escapes isolated root")
        if path.exists():
            data = path.read_bytes()
            snapshot[relative] = (True, data, _digest(data))
        else:
            snapshot[relative] = (False, b"", None)
    return Snapshot(snapshot, existing_paths)


def restore_snapshot(root, snapshot):
    root = Path(root).resolve()
    if not root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError("rollback root must be inside the operating-system temporary directory")
    if not (root / ".simulation-only").is_file():
        raise ValueError("rollback is restricted to a marked simulation root")
    for relative, (existed, data, expected_hash) in snapshot.files.items():
        path = (root / relative).resolve()
        if root not in path.parents:
            raise ValueError("restore path escapes isolated root")
        if existed:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            if _digest(path.read_bytes()) != expected_hash:
                raise IOError(f"restored hash mismatch: {relative}")
        elif path.exists():
            path.unlink()
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file() and path.relative_to(root).as_posix() not in snapshot.existing_paths:
            path.unlink()
