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

51 项本地回归测试及 ruff 检查通过，包括原有分段/邮箱/重采样、中文模式跳过模型、旧结果丢弃、错配译文拒绝、设置迁移、白字简体和运行中拖拽。

已完成 169 段、1811.368 秒（30 分 11 秒）普通话语音的参考文本对比。来源为 FLEURS 开发集，不是用户视频的代表性抽样。CPU：Intel i5-14400F，16 逻辑处理器，约 32 GB 内存；本次模型均使用 CPU，未使用 RTX 显卡。

| 场景 | 段数 | 时长（秒） | Whisper tiny 分段终稿 CER | 中文流式 CER |
|---|---:|---:|---:|---:|
| 全部 | 169 | 1811.368 | 56.40% | 14.91% |
| 原始朗读 | 102 | 1081.020 | 70.17% | 14.22% |
| 1.25 倍加速 | 34 | 333.088 | 36.78% | 13.88% |
| 合成伴奏 | 33 | 397.260 | 38.84% | 17.75% |

逐段 CER 中位数：tiny 31.25%，流式 8.70%。整体按参考字符数加权；CER 包含插入，重复幻觉可能使单段 CER 超过 100%。tiny 的若干长重复输出明显抬高均值。各场景采用不同句子，不能据此比较场景难度。没有将阿拉伯数字与中文数字同义归一化。

对照使用旧版 tiny 的终稿分段及识别参数，省略反复计算的 partial，不包含旧版显示队列或完整并发调度，因此这是识别路径对比，不是整个旧版程序的时序回归。流式结果来自当前引擎；未根据参考文本修改识别输出。逐段结果及语料 revision/摘要见 [原始评分数据](benchmarks/mandarin-accuracy.json)。

这组原始朗读样本的 `1 - CER` 为约 85.78%，**未达到 95% 目标**。真实影视背景音乐、多人同时讲话、方言仍需独立语料验收。

Windows 冻结程序已执行真实中文文件识别、简体字典、白字路径、拖拽与模型加载自检；Mac ARM/Intel 的同类自检及 DMG 构建已通过 GitHub Actions。源码 [跨平台检查](https://github.com/zhangmingfeng962-cyber/LinguaCaption/actions/runs/40083016743)；[Mac 打包运行检查](https://github.com/zhangmingfeng962-cyber/LinguaCaption/actions/runs/40083025813)。这些测试没有打开系统音频内录，也不能替代真机视频、权限和全屏覆盖测试。

## 连续重放与显示延迟

169 段语音加句间静音共 2149.368 秒，实际运行 2155.672 秒（约 35 分 56 秒），经正式 Engine/UI、offscreen Qt：错误 0、告警 0、音频块丢弃 0；峰值 RSS 760.3 MB。录音未经过 WASAPI/ScreenCaptureKit，也没有测量物理屏幕帧。

另从同一素材前段抽取 615.632 秒语音，用 v0.3 源码（commit `da51d49ecb90b212b61d2a5c4c4940378199862a`）重放中文→中文、仅译文、固定停留 4 秒的原路径。记录识别事件与 UI 提交绘制的时刻，旧版显示层额外等待 P50 188 ms、P95 3039.4 ms。它与新版的测试时长、分句边界、样本数不同，不能视为逐句配对实验。

## CPU 等待优化及最终参数复测

长测最初使用 ORT 默认等待策略，整机总容量平均 CPU 23.26%。发布前增加 `assets/onnx-cpu.conf`，关闭 intra/inter-op 工作线程自旋，仍默认 4 线程。在 12 秒静音对照中，同样的等待策略测试由约 17.15% 降至 1.98%；这是短时本机检查。

最终参数再重放 31 段、300.156 秒语音，加静音共 362.156 秒，实际运行 369.5 秒：错误/告警/音频块丢弃均为 0，CPU 平均 2.21%（16 逻辑处理器总容量），峰值 RSS 445.8 MB。短测使用更少音频缓冲，内存值不能与长测直接比较。数据包括模型加载与收尾；测试期间存在构建及对照任务，未测视频掉帧。

| 程序内估算，毫秒 | 旧版子集 | 新版长测（优化前） | 最终参数短测 |
|---|---:|---:|---:|
| 首条非空字幕 P50 | 4446 | 1235 | 1328 |
| 首条非空字幕 P95 | 7770 | 2455 | 2747.6 |
| 终稿可见滞后 P50 | 942 | 624 | 834 |
| 终稿可见滞后 P95 | 5246.4 | 1132.5 | 1216.6 |

首条字幕从 VAD 检出的语音起点计时，终稿相对最后 VAD 语音估算；都是软件音频时钟/Qt 提交事件，不含真实系统内录、物理显示，也不等于逐字内容对齐。模型无逐字时间戳，原始 JSON 中相对最近输入音频的 rolling lag 会低估真实文字覆盖滞后，不能拿来宣传 500 ms。**首条与终稿均未达到 500 ms 目标。**

最终 CPU 参数又对全部 169 段、1811.368 秒语音执行输出一致性核对：与评分时文字逐段完全相同，差异 0，所以前述识别评分仍适用于最终模型参数。

原始数据：[长测](benchmarks/mandarin-realtime.json)、[旧版延迟对照](benchmarks/mandarin-v030-latency.json)、[最终参数短测](benchmarks/mandarin-cpu-tuned.json)、[全部语料输出一致性](benchmarks/mandarin-cpu-parity.json)。完整冻结程序、CI、安装包与模型校验记录见 [机器可读验证](mandarin-verification.json)。

复现：先准备本地 FLEURS cmn_hans_cn dev.tsv 与 audio/dev/，运行 `python scripts/benchmark_mandarin.py --dataset <目录> --models <三个模型的父目录> --seconds 1800 --mode batch --output local/accuracy.json`；`--mode realtime` 按播放速度经过正式 Engine/UI，输出单独的实时重放报告。

语料：[Google FLEURS](https://huggingface.co/datasets/google/fleurs)，CC-BY-4.0；保留原始参考文本，评分忽略大小写、标点、空白。快速场景为 1.25 倍加速，伴奏场景为合成和弦，不能外推为真实影视背景音乐质量。多位说话人为轮流讲话，未测试多人重叠讲话。
