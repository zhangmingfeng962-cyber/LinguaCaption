# LinguaCaption

Offline system-audio captions for Windows and macOS. v0.4 adds stateful Mandarin streaming ASR (Paraformer INT8 via sherpa-onnx). Other languages retain the Whisper path; translation uses local M2M100.

New speech replaces old captions immediately. Retention applies only while no new text arrives. Chinese-to-Chinese configurations migrate to original-only Mandarin captions and do not load the translation model. System fonts, white text with shadow, Simplified Chinese conversion and live dragging remain available.

Download the standalone applications from [v0.4.0 Releases](https://github.com/zhangmingfeng962-cyber/LinguaCaption/releases/tag/v0.4.0). Models and dependencies are bundled; no Python installation, API key, cloud service, or runtime download is required.

See the [Chinese guide](README.md), [streaming validation](docs/MANDARIN.md), and [desktop distribution guide](docs/DESKTOP.md). The 500 ms / 95% acceptance targets remain unverified or unmet; replay measurements are not physical screen/capture measurements. macOS system audio still needs testing on physical devices.

Development: Python 3.12, `python -m pip install -e '.[dev]'`, `python scripts/prepare_mandarin.py`, `python -m linguacaption`. Use `python scripts/prepare_models.py asr --size base` for other languages and `python scripts/prepare_models.py translation` for translation. These preparation commands use the network; subtitle sessions use local files.

Application code: MIT. Paraformer model: Apache-2.0. Bundles contain dependency licenses and model provenance/checksums.
