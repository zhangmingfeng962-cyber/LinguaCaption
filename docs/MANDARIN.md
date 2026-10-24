# v0.4 中文流式字幕

日期：2026-10-24，Asia/Shanghai。

## 行为

默认中文原文，Paraformer 流式 INT8，CPU 4 线程；运行时不联网、不加载翻译模型。其他源语言仍走 Whisper；选择「Whisper 多语言」可手动使用原路径。

显示层不再缓存旧句，不等待固定 4 秒。新原文及时显示并清除旧译文；双语译文必须匹配同一语句、修订、原文及源语言。仅译文模式在新译文到达前清空旧译文。停顿后才应用保留时长，新安装为 4 秒，升级保留既有无新内容隐藏时长。

流式引擎持续消费 16 kHz 单声道 PCM，保留模型缓存。端点重置保留未解码音频，断流则清除旧上下文。音频队列有界，过载时告警并重新同步，旧世代结果不能回到屏幕。停止和音源切换丢弃尚未显示的旧结果。

配置版本 4：新增 `asr_backend`（auto/whisper/paraformer）、`streaming_model`、`streaming_threads`。中文→中文配置迁移为 original/auto；样式、位置、安全区域和隐藏时长保留。旧 `subtitle_hold_ms` 不再生效。

## 模型与重现

模型来源：[Paraformer ONNX](https://huggingface.co/csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en)，固定 revision `8e40c43232a1c5c66c82111efc5820d3accca11b`，Apache-2.0。准备命令：`python scripts/prepare_mandarin.py`。脚本对固定文件校验 SHA-256；模型目录包含来源、摘要及许可文件。运行时在加载前检查完整性。

[官方运行说明](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-paraformer/paraformer-models.html)。此模型没有逐字时间戳，界面滞后使用采样时钟和 VAD 估算，不代表逐字对齐或真实声到屏延迟。

## 验证

50 项本地回归测试及 ruff 检查通过，包括原有分段/邮箱/重采样、中文模式跳过模型、旧结果丢弃、错配译文拒绝、设置迁移、白字简体和运行中拖拽。

30 分钟以上带参考文本语料对比、实时重放、Windows/Mac 冻结程序自检及发布检查正在运行，最终结果将在本文件与随附 JSON 中列出。尚不宣称 500 ms 或 95% 达标。

复现：先准备本地 FLEURS cmn_hans_cn dev.tsv 与 audio/dev/，运行 `python scripts/benchmark_mandarin.py --dataset <目录> --models <三个模型的父目录> --seconds 1800 --mode batch --output local/accuracy.json`；`--mode realtime` 按播放速度经过正式 Engine/UI，输出单独的实时重放报告。

语料：[Google FLEURS](https://huggingface.co/datasets/google/fleurs)，CC-BY-4.0；保留原始参考文本，评分忽略大小写、标点、空白。快速场景为 1.25 倍加速，伴奏场景为合成和弦，不能外推为真实影视背景音乐质量。多位说话人为轮流讲话，未测试多人重叠讲话。
