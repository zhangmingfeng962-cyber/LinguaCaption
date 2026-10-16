"""Explicit network provisioning, separate from the offline desktop runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path


def checksums(directory: Path) -> dict[str, str]:
    result = {}
    for path in directory.rglob("*"):
        if path.is_file() and ".cache" not in path.parts:
            with path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            result[path.relative_to(directory).as_posix()] = digest
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Download/convert local models; this command uses the network")
    parser.add_argument("kind", choices=("asr", "translation"))
    parser.add_argument("--size", choices=("tiny", "base", "small", "medium", "large-v3"), default="base")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--revision", help="Optional immutable source model commit SHA")
    args = parser.parse_args()
    destination = (args.output or Path("models") / args.kind).resolve()
    if destination.exists():
        parser.error(f"Output already exists: {destination}. Choose a new --output directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    from huggingface_hub import HfApi, hf_hub_download
    api = HfApi()
    with tempfile.TemporaryDirectory(prefix="model-prepare-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "model"
        if args.kind == "asr":
            from faster_whisper import download_model
            repo = f"Systran/faster-whisper-{args.size}"
            revision = args.revision or api.model_info(repo).sha
            download_model(repo, output_dir=str(staging), revision=revision)
            # Older CT2 releases lack this file; copy the matching official
            # Whisper processor, including the correct 80/128 mel configuration.
            processor_repo = f"openai/whisper-{args.size}"
            processor_revision = api.model_info(processor_repo).sha
            processor = hf_hub_download(processor_repo, "preprocessor_config.json", revision=processor_revision)
            shutil.copy2(processor, staging / "preprocessor_config.json")
            manifest = {"format": "whisper-ct2-v1", "repo": repo, "revision": revision,
                        "processor_repo": processor_repo, "processor_revision": processor_revision}
        else:
            from ctranslate2.converters import TransformersConverter
            repo = "facebook/m2m100_418M"
            revision = args.revision or api.model_info(repo).sha
            converter = TransformersConverter(repo, revision=revision, trust_remote_code=False,
                                              copy_files=["sentencepiece.bpe.model", "vocab.json",
                                                          "tokenizer_config.json", "special_tokens_map.json"])
            converter.convert(str(staging), quantization="int8")
            manifest = {"format": "m2m100-transformers-v1", "repo": repo,
                        "revision": revision, "quantization": "int8", "license": "MIT"}
        manifest["sha256"] = checksums(staging)
        (staging / "linguacaption.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        shutil.move(str(staging), str(destination))
    print(f"Ready: {destination}")
    print("Configure this directory in LinguaCaption. Runtime does not download models.")


if __name__ == "__main__":
    main()
