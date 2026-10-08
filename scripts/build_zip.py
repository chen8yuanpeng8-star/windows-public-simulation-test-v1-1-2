import json
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/build_zip.py <new-archive-path>")
    destination = Path(sys.argv[1]).resolve()
    if destination.exists():
        raise SystemExit("refusing to overwrite an existing archive")
    if destination.is_relative_to(ROOT):
        raise SystemExit("archive must be outside the source bundle directory")
    inventory = json.loads((ROOT / "PUBLIC_RELEASE_AUDIT.json").read_text(encoding="utf-8"))["files"]
    names = [entry["path"] for entry in inventory]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in names:
            archive.write(ROOT / name, arcname=name)
    print(f"ARCHIVE_CREATED members={len(names)} path={destination}")


if __name__ == "__main__":
    main()
