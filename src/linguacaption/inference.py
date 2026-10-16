from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from .config import LANGUAGES, Settings


def require_files(path: str, names: tuple[str, ...], purpose: str) -> Path:
    directory = Path(path).expanduser().resolve()
    missing = [name for name in names if not (directory / name).is_file()]
    if missing:
        raise RuntimeError(f"{purpose}模型不完整：{directory}\n缺少 {', '.join(missing)}。请运行 scripts/prepare_models.py。")
    return directory


class WhisperRecognizer:
    def __init__(self, settings: Settings) -> None:
        # Also require tokenizer.json: upstream may otherwise request a fallback
        # tokenizer even when local_files_only was passed to its model loader.
        path = require_files(settings.asr_model,
                             ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"), "识别")
        if not any((path / name).is_file() for name in ("vocabulary.json", "vocabulary.txt")):
            raise RuntimeError("识别模型缺少 vocabulary.json / vocabulary.txt")
        config = json.loads((path / "config.json").read_text(encoding="utf-8"))
        if config.get("is_multilingual") is False:
            raise RuntimeError("请选择多语言 Whisper 模型；.en 模型仅支持英语")
        # Runtime is offline. Provisioning is a separate, explicit command.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from faster_whisper import WhisperModel
        self.model = WhisperModel(str(path), device=settings.device, compute_type=settings.compute_type,
                                  cpu_threads=settings.asr_threads, num_workers=1, local_files_only=True)
        if not self.model.model.is_multilingual:
            raise RuntimeError("请选择多语言 Whisper 模型；当前加载的是仅英语模型")
        self.source = None if settings.source == "auto" else settings.source

    def transcribe(self, samples: np.ndarray) -> tuple[str, str]:
        segments, info = self.model.transcribe(
            samples, language=self.source, task="transcribe", beam_size=1,
            best_of=1, temperature=0, condition_on_previous_text=False,
            vad_filter=False, word_timestamps=False, no_speech_threshold=0.6,
            compression_ratio_threshold=2.4, log_prob_threshold=-1.0,
        )
        text = "".join(segment.text for segment in segments).strip()
        return text, info.language


class LocalTranslator:
    """M2M100 converted with CT2's Transformers converter, not Fairseq format."""

    def __init__(self, settings: Settings) -> None:
        path = require_files(settings.translation_model,
                             ("model.bin", "config.json", "sentencepiece.bpe.model", "linguacaption.json"), "翻译")
        manifest = json.loads((path / "linguacaption.json").read_text(encoding="utf-8"))
        if manifest.get("format") != "m2m100-transformers-v1":
            raise RuntimeError("翻译模型格式不匹配，请用 scripts/prepare_models.py translation 转换")
        import ctranslate2
        import sentencepiece
        self.tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(path / "sentencepiece.bpe.model"))
        self.model = ctranslate2.Translator(str(path), device="cpu", compute_type="int8",
                                          inter_threads=1, intra_threads=settings.translation_threads,
                                          max_queued_batches=1)

    def translate(self, text: str, source: str, target: str) -> str:
        if source == target:
            return text
        if source not in LANGUAGES or target not in LANGUAGES:
            raise RuntimeError(f"当前翻译界面暂未开放 {source} → {target}，请选择支持的 12 种语言")
        # Matches M2M100Tokenizer: [source language] + sentencepiece + EOS.
        tokens = [f"__{source}__", *self.tokenizer.encode(text, out_type=str), "</s>"]
        if len(tokens) > 256:
            raise RuntimeError("当前字幕超过 256 tokens，请缩短最长语句时长")
        result = self.model.translate_batch([tokens], target_prefix=[[f"__{target}__"]],
                                            beam_size=1, max_decoding_length=256,
                                            no_repeat_ngram_size=3)
        output = [t for t in result[0].hypotheses[0][1:] if t not in {"</s>", "<s>", "<pad>"}]
        return self.tokenizer.decode(output).strip()
