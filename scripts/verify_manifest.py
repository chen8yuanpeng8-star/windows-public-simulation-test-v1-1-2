import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((ROOT / "TEST_MANIFEST.json").read_text(encoding="utf-8"))
    audit = json.loads((ROOT / "PUBLIC_RELEASE_AUDIT.json").read_text(encoding="utf-8"))
    expected = {item["path"] for item in manifest["files"]} | set(manifest["metadata_files"])
    actual = {
        p.relative_to(ROOT).as_posix()
        for p in ROOT.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    if actual != expected:
        raise SystemExit(f"file list mismatch; extra={sorted(actual-expected)} missing={sorted(expected-actual)}")
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if sha(path) != item["sha256"]:
            raise SystemExit(f"manifest hash mismatch: {item['path']}")
    audit_paths = {item["path"] for item in audit["files"]}
    if audit_paths != expected:
        raise SystemExit("audit inventory mismatch")
    sums = {}
    for line in (ROOT / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    if set(sums) != expected - {"SHA256SUMS.txt"}:
        raise SystemExit("checksum inventory mismatch")
    for name, expected_hash in sums.items():
        if sha(ROOT / name) != expected_hash:
            raise SystemExit(f"checksum mismatch: {name}")
    print(f"MANIFEST_OK files={len(actual)} hashes={len(sums)}")


if __name__ == "__main__":
    main()
