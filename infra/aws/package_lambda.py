"""Build the Lambda artifact from the same explicit manifest as Terraform."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("lambda_files.txt")


def package(output: Path) -> tuple[str, ...]:
    names = tuple(line.strip() for line in MANIFEST.read_text(encoding="utf-8").splitlines()
                  if line.strip())
    if len(names) != len(set(names)):
        raise ValueError("Duplicate Lambda package path")
    for name in names:
        path = Path(name)
        if (path.is_absolute() or ".." in path.parts or
            not (name.startswith("advisor/") or name == "plan/conversation_data/source_pack.md") or
            not (ROOT / path).is_file()):
            raise ValueError(f"Unsafe or missing Lambda package path: {name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name in sorted(names):
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, (ROOT / name).read_bytes())
    return names


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    files = package(args.output)
    print(f"Packaged {len(files)} tracked inputs; sha256={hashlib.sha256(args.output.read_bytes()).hexdigest()}")
