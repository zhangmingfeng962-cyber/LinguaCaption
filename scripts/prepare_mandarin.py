"""Explicit network provisioning of the pinned, redistributable streaming model."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
from pathlib import Path

REPO = "csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en"
REVISION = "8e40c43232a1c5c66c82111efc5820d3accca11b"
EXPECTED = {
    "encoder.int8.onnx": "81a70226a8934e6ed92aa1d4fc486b428b5398e2f2619ed4897b7294cab90e9a",
    "decoder.int8.onnx": "f3cca9f77bb9d93c8fcbfb63ae617b6b1ee96818df3aa3b151c40658fe38594f",
    "tokens.txt": "59aba8873a2ed1e122c25fee421e25f283b63290efbde85c1f01a853d83cb6e6",
    "README.md": "16b56210f03531d00f5580b060ff6843461e618e5642c070a58df6f0a5c98875",
    "LICENSE.txt": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
}


def prepare(destination: Path) -> None:
    if destination.exists():
        raise ValueError("Output already exists; choose a new directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix="prepare-zh-") as temp:
        staging = Path(temp) / "model"
        staging.mkdir()
        names = ("encoder.int8.onnx", "decoder.int8.onnx", "tokens.txt", "README.md")
        for name in names:
            print(f"Downloading {name}", flush=True)
            urllib.request.urlretrieve(f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}", staging / name)
        shutil.copyfile(Path(__file__).resolve().parents[1] / "packaging/licenses/Paraformer-LICENSE.txt",
                        staging / "LICENSE.txt")
        manifest = {"format": "paraformer-online-int8-v1", "repo": REPO, "revision": REVISION,
                    "license": "Apache-2.0", "sample_rate": 16000, "sha256": {}}
        for name in (*names, "LICENSE.txt"):
            with (staging / name).open("rb") as handle:
                manifest["sha256"][name] = hashlib.file_digest(handle, "sha256").hexdigest()
            if manifest["sha256"][name] != EXPECTED[name]:
                raise ValueError(f"Downloaded model file failed SHA-256 verification: {name}")
        (staging / "linguacaption.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        shutil.move(staging, destination)
    print(f"Ready: {destination}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("models/asr-zh"))
    prepare(parser.parse_args().output.resolve())
