# Contributing / 参与开发

欢迎通过 GitHub Issues 报告问题，或提交 Pull Request。提交缺陷时请提供系统版本、Python 版本、模型名称与量化方式、是否为演示模式、复现步骤及错误信息。不要在公开 Issue 中上传私人音频、账号信息、令牌或完整本机配置。

Issues and pull requests are welcome in Chinese or English. Include your OS, Python version, model/quantization, demo mode state, reproduction steps, and relevant error messages. Avoid posting private audio or credentials.

## Local checks

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check .
```

CI runs model-free tests on Windows and macOS, renders Qt widget previews, and compiles the macOS system-audio helper. CI does not establish real-device capture, fullscreen composition, multilingual quality, or end-to-end latency. Real model tests use the separate preparation and benchmark scripts.

Keep changes focused and explain their behavior and validation. Preserve run/utterance/revision checks for asynchronous results, bounded queues, and the rule that protected screen areas take precedence over subtitle visibility.

模型、录音、缓存、构建产物及个人设置不应加入 Git。提交性能数字时请说明硬件、模型、语料、统计口径及是否包含真实采集和 UI 绘制。不要用更新间隔代替端到端延迟，也不要把单一英文样本的准确率外推到全部语言。
