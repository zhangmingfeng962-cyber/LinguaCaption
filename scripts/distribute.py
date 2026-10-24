from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

from linguacaption import __version__


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iscc", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    version = __version__
    if platform.system() == "Windows":
        application = args.dist_dir.resolve() / "LinguaCaption"
        if not (application / "LinguaCaption.exe").is_file():
            parser.error("Packaged application was not found")
        archive = output / f"LinguaCaption-{version}-windows-x64-portable.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as target:
            for path in application.rglob("*"):
                if path.is_file():
                    target.write(path, "LinguaCaption/" + path.relative_to(application).as_posix())
        compiler = args.iscc or shutil.which("ISCC")
        if not compiler:
            for candidate in (Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
                              Path("C:/Program Files/Inno Setup 7/ISCC.exe")):
                if candidate.is_file():
                    compiler = candidate
                    break
        if not compiler:
            parser.error("Inno Setup compiler is required for the Windows installer; pass --iscc")
        subprocess.run([str(compiler), f"/DAppVersion={version}", f"/DSourceDir={application}",
                        f"/DPackageDir={output}", str(root / "packaging/windows.iss")], check=True)
    else:
        application = args.dist_dir.resolve() / "LinguaCaption.app"
        if not application.is_dir():
            parser.error("Packaged .app was not found")
        stage = args.dist_dir.resolve() / "dmg-stage"
        stage.mkdir(exist_ok=True)
        subprocess.run(["ditto", str(application), str(stage / "LinguaCaption.app")], check=True)
        applications_link = stage / "Applications"
        if not applications_link.exists():
            applications_link.symlink_to("/Applications", target_is_directory=True)
        architecture = "arm64" if platform.machine() == "arm64" else "x64"
        archive = output / f"LinguaCaption-{version}-macos-{architecture}.dmg"
        for attempt in range(3):
            result = subprocess.run(["hdiutil", "create", "-ov", "-volname", "LinguaCaption", "-srcfolder", str(stage),
                                     "-format", "UDZO", str(archive)])
            if result.returncode == 0:
                break
            if attempt == 2:
                result.check_returncode()
            time.sleep(5)
    checksums = {}
    for path in output.iterdir():
        if path.is_file() and path.suffix in {".exe", ".zip", ".dmg"}:
            with path.open("rb") as handle:
                checksums[path.name] = hashlib.file_digest(handle, "sha256").hexdigest()
    (output / f"SHA256-{platform.system().lower()}-{platform.machine()}.json").write_text(
        json.dumps(checksums, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
