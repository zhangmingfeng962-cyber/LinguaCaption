# 验收方法与性能目标

需求中的「延迟 ≤500 ms」「准确率 ≥95%」是产品验收目标。当前开发版**尚未完成该验收**。默认首次上下文 640 ms，仅此就可能超过 500 ms 首字目标；把更新间隔改为 200 ms 也不能消除推理与译文生成时间。

## 指标必须分开

| 指标 | 定义 |
|---|---|
| 首字延迟 | 从语句首个可听语音样本到首条有效 partial 实际绘制 |
| 原文滚动滞后 | 从当前识别覆盖的最后语音样本到原文实际绘制 |
| 稳定终稿延迟 | 从语句最后语音样本到最终原文绘制，包含端点确认 |
| 双语延迟 | 从对应最后语音样本到匹配当前原文修订的译文绘制 |
| ASR / MT 耗时 | 对应一次模型调用的计算时间，不能代替端到端延迟 |
| 准确率 | 约定为 `1 - WER`（按词）或 `1 - CER`（按字）；分别报告各语言与场景 |

Whisper 语言检测概率是语言置信度，不能当作词准确率。识别准确率也不能替代翻译质量。对中文、日语、韩语建议至少同时报告 CER；逐条人工标注切分、数字、专有名词与标点归一化规则。

界面的「字幕滞后 · 估算」基于应用采样时钟，未精确包含声卡、系统合成器和屏幕刷新延迟。`benchmark.py` 在无声卡的本地音频重放中统计同类软件滞后，**不测 GUI 绘制和真实系统内录**。需要真正的声到屏测量时，使用对齐时间标记的音视频素材与屏幕录制或外部高帧率摄像，测量可见字形出现的帧。

## 可重复的本地重放

使用有人工参考文本的录音：

```bash
python scripts/benchmark.py --audio fixture.wav --asr-model models/asr \
  --translation-model models/translation --language en --target zh \
  --reference reference.txt --metric wer --output local/benchmark.json
```

省略 `--translation-model` 可单独测 ASR。中文等可用 `--metric cer`。工具按照播放速度推送 50 ms 块，通过真实重采样后端以外的 16 kHz 夹具、VAD、分段、ASR、翻译和并发邮箱，统计首条字幕/原文/双语滞后的 P50/P95、CPU、峰值 RSS、错误、过载以及归一化 WER/CER。CPU 窗口包含加载、播放和等待收尾，不能作为稳态播放 CPU。

基准在音频结束后继续等待队列安静，以便记录最终译文。没有参考文本时不输出准确率。一次英文短样本通过不能说明另外 11 种语言、长视频或其他机器通过。

## 建议正式测试矩阵

- Windows 10/11 + macOS 13/14/更新稳定版；Intel、Apple Silicon；1080p/4K，100%/150%/200% DPI；双屏含负坐标、屏幕拔插。
- 12 种源语言均含至少 30 分钟人工核对语料，清晰语音为主，另列背景音乐、口音、多人、快速说话、静音与噪声。固定源语言和自动语言检测分别测试。
- 分别检查首字、原文、终稿与双语延迟；在测量前约定 500 ms 指哪一项、P95 还是最大值、是否计入端点确认；不可只报告平均值。
- 播放器、浏览器、直播分别测试；默认扬声器、耳机、切换输出设备；Mac 允许/拒绝/撤销录制权限；Windows 无设备与远程会话。
- 拖拽、四种预设、短长行、中日韩/RTL、三种背景、不同字体、穿透恢复、快捷键冲突、全屏 Spaces、保护区域完全覆盖。
- 至少 60 分钟稳态运行，记录系统/进程 CPU、内存、视频掉帧、队列丢弃、音画同步与输出质量，检查资源不随时间增长。

建议默认性能验收条件包含：模型/量化固定、目标机器规格固定、12 语言分别达标、P95 和最大值单列、过载为零、主视频掉帧不劣于约定阈值。CPU 阈值应基于总逻辑处理器容量定义，不能以一个线程百分比混用。

## 本版未完成项

目标设备上的全套音频内录与屏幕叠加联调、Mac 原生编译/权限实测、长时间压力测试、12 语言准确率、译文人工评分、500 ms 全链路目标、正式签名/公证和安装包发布均未验收。没有集成人脸检测或移动人物跟踪。

接口选择依据：[Microsoft WASAPI loopback](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording)、[Apple ScreenCaptureKit](https://developer.apple.com/documentation/screencapturekit/capturing-screen-content-in-macos)、[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[CTranslate2 Transformers 转换说明](https://opennmt.net/CTranslate2/guides/transformers.html)。
