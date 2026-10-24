from __future__ import annotations

import importlib.metadata
import json
import shutil
from pathlib import Path


def collect_licenses(output: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "LICENSE", output / "LinguaCaption-MIT.txt")
    for path in (root / "packaging/licenses").glob("*"):
        if path.is_file():
            shutil.copy2(path, output / path.name)
    packages = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name", "unknown")
        target = output / (name + "-" + distribution.version)
        copied = []
        for relative in distribution.files or []:
            filename = str(relative).lower()
            if not any(key in filename for key in ("license", "copying", "notice")):
                continue
            source = Path(distribution.locate_file(relative))
            if not source.is_file() or source.suffix.lower() in {".py", ".pyc", ".pyd", ".dll", ".so"}:
                continue
            target.mkdir(parents=True, exist_ok=True)
            safe_parts = [part for part in Path(relative).parts if part not in {"..", "."}]
            destination = target.joinpath(*safe_parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(destination.relative_to(output).as_posix())
        packages.append({"name": name, "version": distribution.version,
                         "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License"),
                         "urls": distribution.metadata.get_all("Project-URL", []), "included_files": copied})
    (output / "packages.json").write_text(json.dumps(packages, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "README.txt").write_text(
        "LinguaCaption redistributes unmodified third-party runtime components.\n"
        "See packages.json and the individual license files for attribution.\n\n"
        "Qt and PySide6 are dynamically linked under LGPLv3. The shared libraries\n"
        "remain separate and may be replaced with compatible modified versions.\n"
        "No restriction on reverse engineering is imposed by this application.\n"
        "Corresponding upstream sources: https://code.qt.io/cgit/qt/qtbase.git/\n"
        "https://code.qt.io/cgit/pyside/pyside-setup.git/\n"
        "https://download.qt.io/official_releases/qt/\n"
        "Select the version recorded in packages.json (the initial package uses Qt 6.12.0).\n\n"
        "Whisper model: https://github.com/openai/whisper (MIT).\n"
        "Paraformer streaming model: https://huggingface.co/csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en (Apache-2.0).\n"
        "M2M100 model: https://huggingface.co/facebook/m2m100_418M (MIT).\n"
        "Model provenance and file hashes accompany the bundled model directories.\n",
        encoding="utf-8")
