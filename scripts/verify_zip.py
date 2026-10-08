import hashlib
import json
import sys
import zipfile
from pathlib import PurePosixPath

from security_scan import DENIED_SUFFIXES, PATTERNS


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/verify_zip.py <archive>")
    manifest = json.loads((ROOT / "TEST_MANIFEST.json").read_text(encoding="utf-8"))
    audit = json.loads((ROOT / "PUBLIC_RELEASE_AUDIT.json").read_text(encoding="utf-8"))
    expected = {item["path"] for item in audit["files"]}
    hashes = {}
    for line in (ROOT / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        value, name = line.split("  ", 1)
        hashes[name] = value
    with zipfile.ZipFile(sys.argv[1], "r") as archive:
        names = set(archive.namelist())
        if names != expected:
            raise SystemExit(f"archive inventory mismatch; extra={sorted(names-expected)} missing={sorted(expected-names)}")
        if any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts for name in names):
            raise SystemExit("unsafe archive path")
        for name in sorted(names):
            data = archive.read(name)
            if name in hashes and hashlib.sha256(data).hexdigest() != hashes[name]:
                raise SystemExit(f"archive content hash mismatch: {name}")
            if name != "SHA256SUMS.txt":
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    raise SystemExit(f"non-UTF8 archive member: {name}")
                if PurePosixPath(name).suffix.casefold() in DENIED_SUFFIXES:
                    raise SystemExit(f"forbidden archive member: {name}")
                for pattern in PATTERNS:
                    if pattern.search(text):
                        raise SystemExit(f"sensitive pattern in archive member: {name}")
    print(f"ZIP_OK files={len(expected)} sha256={hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest()}")


if __name__ == "__main__":
    main()
