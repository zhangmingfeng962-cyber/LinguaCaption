"""Create and verify the versioned offline model pack used by desktop builds."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def create(source: Path, archive: Path) -> str:
    files = sorted(path for directory in ("asr", "translation")
                   for path in (source / directory).rglob("*")
                   if path.is_file() and ".cache" not in path.parts)
    if not all((source / name / "model.bin").is_file() for name in ("asr", "translation")):
        raise ValueError("Both complete model directories are required")
    licenses = Path(__file__).resolve().parents[1] / "packaging/licenses"
    entries = [(path, path.relative_to(source).as_posix()) for path in files]
    entries += [(path, "licenses/" + path.name) for path in sorted(licenses.iterdir()) if path.is_file()]
    manifest = {name: {"sha256": digest(path), "size": path.stat().st_size} for path, name in entries}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as target:
        for path, name in entries:
            target.write(path, name)
        target.writestr("MODEL-SHA256.json", json.dumps(manifest, indent=2))
    return digest(archive)


def extract(archive: Path, destination: Path, expected_sha256: str) -> None:
    if digest(archive) != expected_sha256.lower():
        raise ValueError("Model archive SHA-256 did not match")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Extraction directory must be empty")
    with zipfile.ZipFile(archive) as source:
        infos = source.infolist()
        names = [entry.filename for entry in infos]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate archive entries")
        for entry in infos:
            path = PurePosixPath(entry.filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in entry.filename
                    or ":" in entry.filename or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError("Unsafe archive path")
        if sum(entry.file_size for entry in infos) > 2_000_000_000:
            raise ValueError("Unexpected model archive size")
        manifest = json.loads(source.read("MODEL-SHA256.json"))
        if set(names) != set(manifest) | {"MODEL-SHA256.json"}:
            raise ValueError("Model inventory does not match archive")
        destination.mkdir(parents=True, exist_ok=True)
        for name, expected in manifest.items():
            target = destination.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(name) as reader, target.open("wb") as writer:
                shutil.copyfileobj(reader, writer)
            if target.stat().st_size != expected["size"] or digest(target) != expected["sha256"]:
                raise ValueError(f"Model file failed integrity verification: {name}")
        (destination / "MODEL-SHA256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("create")
    pack.add_argument("source", type=Path)
    pack.add_argument("archive", type=Path)
    unpack = commands.add_parser("extract")
    unpack.add_argument("archive", type=Path)
    unpack.add_argument("destination", type=Path)
    unpack.add_argument("--sha256", required=True)
    args = parser.parse_args()
    if args.command == "create":
        print(json.dumps({"archive": str(args.archive), "sha256": create(args.source, args.archive)}))
    else:
        extract(args.archive, args.destination, args.sha256)
        print("Offline model pack verified and extracted")


if __name__ == "__main__":
    main()
