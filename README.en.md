# LinguaCaption

[中文说明](README.md) · [Releases](https://github.com/zhangmingfeng962-cyber/LinguaCaption/releases)

A local-first desktop prototype for bilingual captions over video on Windows and macOS. It captures system output audio, transcribes speech locally, translates locally, and renders an independent always-on-top caption window.

![Desktop workbench](docs/images/workbench.png)

## Current status

This is a **development preview**, distributed as source code under the MIT license. Model weights are downloaded separately. There are no prebuilt installers in the initial release.

- Windows: WASAPI loopback capture through SoundCard.
- macOS 13+: a native Swift ScreenCaptureKit helper; macOS compilation and permissions require validation on a target Mac.
- Offline multilingual Whisper recognition and M2M100 translation through CTranslate2.
- Twelve exposed languages: Chinese, English, Japanese, Korean, Spanish, French, German, Russian, Portuguese, Italian, Arabic, and Hindi.
- Original, translated, and bilingual modes; fonts, colors, outline, shadow, line limits, per-line adaptive backgrounds, draggable placement, and mouse passthrough.
- Manually selected protected screen regions with automatic caption repositioning. There is no face detection or subject tracking.

**The 500 ms latency and 95% accuracy targets have not been accepted.** One 11-second English fixture produced about 426 ms median bilingual software lag and 1,012 ms P95; this excludes actual system capture and GUI paint latency. The normalized final transcript had zero WER on that single fixture. These results do not establish multilingual quality or long-run performance. See [validation](docs/VALIDATION.md) and [acceptance criteria](docs/ACCEPTANCE.md).

## Quick start

Python 3.11–3.13 is required; 3.12 is recommended. Clone or download the source archive:

```bash
git clone https://github.com/zhangmingfeng962-cyber/LinguaCaption.git
cd LinguaCaption
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m linguacaption --demo
```

macOS, with Xcode Command Line Tools installed:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
bash scripts/build_macos.sh
.venv/bin/python -m linguacaption --demo
```

Demo mode uses labeled English/Chinese sample text without audio capture or models. The current desktop interface is in Chinese; the sidebar pages are the workbench, appearance/position, and models/performance.

## Prepare offline models

Using the virtual environment's Python, run these explicit **network-enabled preparation commands** from the project root:

```bash
python -m pip install -e '.[prepare]'
python scripts/prepare_models.py asr --size base
python scripts/prepare_models.py translation
python -m linguacaption
```

On Windows, replace `python` with `.venv\Scripts\python`; on macOS, use `.venv/bin/python`. In the models page, choose the complete `models/asr` and `models/translation` directories. Turn off demo mode and start capture. Original-only mode does not require a translation model.

Translation preparation downloads roughly 2 GB of original model weights and converts them to INT8; extra disk space and RAM are required for conversion. PyTorch and Transformers are preparation dependencies, not runtime requirements. The runtime loads complete local directories and does not automatically fetch missing models. Audio stays in memory; text is saved only through an explicit export.

macOS requires Screen & System Audio Recording permission. Global shortcuts require Accessibility/Input Monitoring permission. Background glass effects depend on the OS compositor and fall back to translucent black when unavailable. Protected media and exclusive fullscreen may restrict capture or overlays.

## Development

```bash
python -m pytest -q
python -m ruff check .
python scripts/package.py
```

Build desktop packages on their target OS. Model weights are external. macOS packaging currently uses an ad hoc development signature; distribution signing and notarization are separate work.

See the [project tree and full usage guide](README.md), [architecture](docs/ARCHITECTURE.md), and [contributing guide](CONTRIBUTING.md). Upstream dependencies and models retain their own licenses; the source release does not redistribute their weights or application binaries.
