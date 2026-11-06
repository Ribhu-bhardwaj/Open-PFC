"""Copy only dashboard inputs into dashboard/data for Community Cloud.

Run from any directory. Originals are opened for reading only. No extraction runs.
"""
import csv
import hashlib
import json
from pathlib import Path, PureWindowsPath

from data_access import read_catalog

DASHBOARD = Path(__file__).resolve().parent


def prepare():
    originals = DASHBOARD.parent / "outputs"
    catalog = read_catalog(originals)
    destination = DASHBOARD / "data"
    destination.mkdir(exist_ok=True)
    wanted = {source.path for source in catalog}
    with (originals / "flat-files-index.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = [*reader.fieldnames, "heading"]
        rows = [r for r in reader if originals.joinpath(*PureWindowsPath(r["file"]).parts).resolve() in wanted]
    hashes = {}
    for source in catalog:
        relative = source.path.relative_to(originals)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        content = source.path.read_bytes()
        target.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Copy verification failed: {relative}")
        hashes[relative.as_posix()] = digest
    # Publish paths with their actual case: the cloud host runs Linux. Keep the
    # heading exactly as printed in the original index for the filter label.
    disk_names = {p.relative_to(destination).as_posix().casefold():
                  p.relative_to(destination).as_posix() for p in destination.rglob("*.csv")}
    for row in rows:
        indexed = PureWindowsPath(row["file"])
        row["heading"] = indexed.parts[0]
        row["file"] = disk_names[indexed.as_posix().casefold()]
    with (destination / "flat-files-index.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (DASHBOARD / "cloud-data-integrity.json").write_text(
        json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(hashes)} byte-identical CSV copies in {destination}")


if __name__ == "__main__":
    prepare()
