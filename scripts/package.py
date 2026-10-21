"""Build a standalone desktop app with optional bundled offline models."""
from __future__ import annotations

import argparse
import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path

from collect_licenses import collect_licenses
from make_icons import make_icons

from linguacaption import __version__


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--asr-model", type=Path, default=root / "models/asr")
    parser.add_argument("--translation-model", type=Path, default=root / "models/translation")
    parser.add_argument("--dist-dir", type=Path, default=root / "dist")
    parser.add_argument("--work-dir", type=Path, default=root / "build/pyinstaller")
    parser.add_argument("--without-models", action="store_true", help="Build a developer-only application")
    args = parser.parse_args()
    native = root / "src/linguacaption/native/macos"
    dist = args.dist_dir.resolve()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if not args.without_models:
        required = ((args.asr_model, ("model.bin", "tokenizer.json", "preprocessor_config.json")),
                    (args.translation_model, ("model.bin", "sentencepiece.bpe.model", "linguacaption.json")))
        for directory, names in required:
            if not all((directory / name).is_file() for name in names):
                parser.error(f"Model directory is incomplete: {directory}")
    assets = make_icons()
    notices = work / "third-party-licenses"
    collect_licenses(notices)
    if platform.system() == "Darwin":
        subprocess.run(["bash", str(root / "scripts/build_macos.sh")], cwd=root, check=True)
    icon = assets / ("app.icns" if platform.system() == "Darwin" else "app.ico")
    command = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--onedir", "--windowed",
               "--name", "LinguaCaption", "--paths", str(root / "src"),
               "--distpath", str(dist), "--workpath", str(work / "analysis"), "--specpath", str(work),
               "--icon", str(icon), "--add-data", f"{assets}:linguacaption/assets",
               "--add-data", f"{notices}:third-party-licenses",
               "--additional-hooks-dir", str(root / "scripts/hooks")]
    for name in ("faster_whisper", "ctranslate2", "tokenizers", "av", "onnxruntime", "sentencepiece", "opencc"):
        command += ["--collect-all", name]
    for name in ("torch", "transformers", "pytest", "IPython", "matplotlib", "scipy", "tkinter"):
        command += ["--exclude-module", name]
    if not args.without_models:
        command += ["--add-data", f"{args.asr_model.resolve()}:models/asr",
                    "--add-data", f"{args.translation_model.resolve()}:models/translation"]
    if platform.system() == "Windows":
        command += ["--collect-all", "soundcard"]
    elif platform.system() == "Darwin":
        command += ["--hidden-import", "pynput.keyboard._darwin", "--hidden-import", "AppKit",
                    "--hidden-import", "Foundation", "--hidden-import", "objc",
                    "--add-data", f"{native / 'AudioCapture.app'}:linguacaption/native/macos/AudioCapture.app",
                    "--osx-bundle-identifier", "local.linguacaption.desktop"]
    command.append(str(root / "scripts/desktop_entry.py"))
    environment = os.environ.copy()
    if platform.system() == "Windows":
        # Prevent unrelated tools on PATH from supplying incompatible ICU/UCRT DLLs.
        windows = Path(environment.get("SystemRoot", "C:/Windows"))
        environment["PATH"] = os.pathsep.join(map(str, (
            Path(sys.prefix) / "Scripts", Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs",
            windows / "System32", windows,
        )))
    subprocess.run(command, cwd=root, check=True, env=environment)
    if platform.system() == "Darwin":
        bundle = dist / "LinguaCaption.app"
        info = bundle / "Contents/Info.plist"
        data = plistlib.loads(info.read_bytes())
        data.update({"CFBundleShortVersionString": __version__, "CFBundleVersion": "3",
                     "LSMinimumSystemVersion": "14.0",
                     "NSScreenCaptureUsageDescription": "Capture system audio for local subtitles.",
                     "NSAudioCaptureUsageDescription": "Transcribe system audio locally without a microphone."})
        info.write_bytes(plistlib.dumps(data))
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(bundle)], check=True)


if __name__ == "__main__":
    main()
