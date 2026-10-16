"""Build an onedir desktop app on its target OS; model weights are external."""
from __future__ import annotations

import platform
import plistlib
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    native = root / "src/linguacaption/native/macos"
    if platform.system() == "Darwin":
        subprocess.run(["bash", str(root / "scripts/build_macos.sh")], cwd=root, check=True)
    command = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--onedir", "--windowed",
               "--name", "LinguaCaption", "--paths", str(root / "src")]
    for name in ("faster_whisper", "ctranslate2", "tokenizers", "av", "onnxruntime", "sentencepiece", "webrtcvad"):
        command += ["--collect-all", name]
    if platform.system() == "Windows":
        command += ["--collect-all", "soundcard"]
    elif platform.system() == "Darwin":
        command += ["--hidden-import", "pynput.keyboard._darwin", "--hidden-import", "AppKit",
                    "--hidden-import", "Foundation", "--hidden-import", "objc",
                    "--add-data", f"{native / 'AudioCapture.app'}:linguacaption/native/macos/AudioCapture.app",
                    "--osx-bundle-identifier", "local.linguacaption.desktop"]
    command.append(str(root / "scripts/desktop_entry.py"))
    subprocess.run(command, cwd=root, check=True)
    if platform.system() == "Darwin":
        bundle = root / "dist/LinguaCaption.app"
        info = bundle / "Contents/Info.plist"
        data = plistlib.loads(info.read_bytes())
        data["NSScreenCaptureUsageDescription"] = "Capture system audio for local subtitles."
        data["NSAudioCaptureUsageDescription"] = "Transcribe system audio locally without a microphone."
        info.write_bytes(plistlib.dumps(data))
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(bundle)], check=True)


if __name__ == "__main__":
    main()
