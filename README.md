# LinguaCaption · 随声字幕

[![Desktop checks](https://github.com/zhangmingfeng962-cyber/LinguaCaption/actions/workflows/ci.yml/badge.svg)](https://github.com/zhangmingfeng962-cyber/LinguaCaption/actions/workflows/ci.yml)

Windows / macOS 桌面双语字幕软件。系统声音 → 本地识别 → 本地翻译 → 独立置顶字幕窗。

[English](README.en.md) · [下载安装包](https://github.com/zhangmingfeng962-cyber/LinguaCaption/releases/tag/v0.2.0) · [问题反馈](https://github.com/zhangmingfeng962-cyber/LinguaCaption/issues)

![工作台](docs/images/desktop-v0.2.0-windows.png)

v0.2.0 提供独立桌面程序，内置多语言 Whisper tiny 和 M2M100 418M INT8 离线模型，无需安装 Python 或单独下载模型。源码、构建脚本和模型来源也公开。**500 ms 延迟、95% 识别准确率尚未完成验收，不能作为本版承诺。** 当前使用窗口式 Whisper 增量推理，并非原生流式 ASR。

## 下载安装使用

在 [v0.2.0 下载页](https://github.com/zhangmingfeng962-cyber/LinguaCaption/releases/tag/v0.2.0) 选择对应系统：

| 系统 | 下载文件 | 使用方法 |
|---|---|---|
| Windows 10/11，64 位 Intel / AMD | `LinguaCaption-0.2.0-windows-x64-setup.exe` | 双击安装，在开始菜单打开；无需管理员权限 |
| Windows 免安装 | `LinguaCaption-0.2.0-windows-x64-portable.zip` | 完整解压后打开文件夹内的 `LinguaCaption.exe`，保留 `_internal` 文件夹 |
| macOS 14+，Apple 芯片 | `LinguaCaption-0.2.0-macos-arm64.dmg` | 打开磁盘映像，把程序拖入「应用程序」 |
| macOS 14+，Intel 芯片 | `LinguaCaption-0.2.0-macos-x64.dmg` | 打开磁盘映像，把程序拖入「应用程序」 |

打开软件 → 在播放器或浏览器播放视频 → 选择识别语言和目标语言 → 点击「开始捕获」。默认英语识别、中文翻译。可先用「演示」调整样式，实际使用时关闭演示。拖拽字幕到合适位置，或在「样式与位置」设置保护区。

软件包包含模型，下载体积较大；首次启动识别需要加载模型，运行期可断网。Mac 首次捕获需在系统设置允许屏幕与系统音频录制，快捷键另需辅助功能 / 输入监控权限。Mac 捕获与全屏覆盖仍需在真实设备验收。

本预览版 Windows 安装程序未使用商业代码签名；Mac 使用临时签名，未公证。系统可能提示未知开发者，请核对本仓库来源和发布页 SHA-256；Mac 可在「系统设置 → 隐私与安全性」按系统提示允许打开。安装与卸载说明见 [桌面发行指南](docs/DESKTOP.md)。

## 从源码启动（开发者）

项目采用 MIT 许可证，任何人都可以下载、使用和修改源码。可以从 Releases 下载源码包，也可以克隆公开仓库：

```bash
git clone https://github.com/zhangmingfeng962-cyber/LinguaCaption.git
cd LinguaCaption
```

需要 Python 3.11–3.13，建议 3.12。Windows 建议 Windows 10/11 64 位；macOS 原生系统音频需要 13+ 和 Xcode Command Line Tools。

在解压后的项目根目录运行：

```powershell
# Windows PowerShell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m linguacaption --demo
```

```bash
# macOS
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
bash scripts/build_macos.sh
.venv/bin/python -m linguacaption --demo
```

演示模式只播放明确标注的英中示例，不内录、不识别，不展示虚构延迟。没有模型也能调样式、拖拽字幕和框选保护区。退出演示后使用真实捕获。

## 准备本地模型

以下命令**需要联网**，仅用于准备模型。完成后运行期只读本地目录，不自动访问模型仓库。翻译转换会下载约 2 GB 的原始权重，需要额外磁盘及内存；运行期不需要 PyTorch/Transformers。

```bash
python -m pip install -e '.[prepare]'
python scripts/prepare_models.py asr --size base
python scripts/prepare_models.py translation
python -m linguacaption
```

这里的 `python` 指虚拟环境中的解释器；Windows 可用 `.venv\Scripts\python`，Mac 用 `.venv/bin/python`。在「模型与性能」选择 `models/asr` 和 `models/translation` 的完整目录，再点「开始捕获」。选择「仅原文」时可以不准备翻译模型。

识别可选 `tiny / base / small / medium / large-v3` 多语言模型，`.en` 英语专用模型会被拒绝。翻译使用 M2M100 418M，经 CTranslate2 INT8 转换；工程界面开放 **中文、英语、日语、韩语、西班牙语、法语、德语、俄语、葡萄牙语、意大利语、阿拉伯语、印地语** 12 种语言及互译。支持范围不等于各语言质量均已达标。

准备工具记录源仓库 commit、处理器 commit 及文件 SHA-256。若需要完全离线部署，在联网机器准备好目录后复制整个目录。输出目录已存在时准备工具会拒绝覆盖，可用 `--output 新目录`。默认配置保存在当前用户的系统配置目录中，也可通过 `--config 路径` 指定。

## 使用与功能

| 功能 | 本版行为 |
|---|---|
| Windows 系统内录 | SoundCard / WASAPI loopback；可选输出设备，无麦克风回退 |
| Mac 系统内录 | Swift ScreenCaptureKit 辅助程序，权限由系统控制，无虚拟声卡依赖 |
| 悬浮显示 | 无边框、置顶、不抢焦点；底部、顶部、左右侧栏及自由拖拽 |
| 背景 | 无背景、半透明黑底、系统磨砂；每行宽度独立跟随文字 |
| 文字 | 字体、字号、字重、原/译文颜色、描边粗细/颜色、阴影 |
| 双语模式 | 仅原文 / 仅译文 / 双语；翻译异步返回，旧版本译文不会覆盖新原文 |
| 阅读 | 按字素簇和实际像素宽度换行；每种语言显示最近 1–4 行；完整文字保留在最近 60 条会话中 |
| 避让 | 对每个屏幕框选最多 8 个保护区；字幕整体选择最近的可用位置，放不下则隐藏 |
| 观看控制 | 鼠标悬停才显示工具条；锁定后鼠标穿透，可用快捷键或主窗解锁 |
| 性能 | WebRTC VAD、INT8、线程数限制、有界队列、静音不触发识别；显示实测处理耗时与估算滞后 |
| 隐私 | 音频只在内存；文本不自动落盘，手动导出最近会话为 UTF-8 TXT |

保护区由用户框选，**没有人脸检测或自动跟踪视频区域**。视频、窗口或人物移动后需重新框选。安全区使用所选屏幕可用范围的归一化坐标，切换分辨率时按比例缩放。可在「样式与位置」预览字幕再选择区域。

| 全局快捷键 | 动作 |
|---|---|
| Ctrl + Alt + S | 显示 / 隐藏字幕，采集状态保持可见 |
| Ctrl + Alt + L | 交换源语言与目标语言，并重启会话 |
| Ctrl + Alt + ↑ / ↓ | 字号 +2 / −2；Windows 冲突时自动尝试 Ctrl + Alt + = / - |
| Ctrl + Alt + K | 切换锁定与鼠标穿透 |

Mac 的 Alt 对应 Option。全局键盘监听需要「辅助功能 / 输入监控」权限，未授权时仍可使用界面按钮。Windows 快捷键冲突会提示。语言、模型或性能设置变更会等待当前推理结束后重启会话；切换显示模式也会重启。停止可能需等待当前 C++ 模型计算完成。

## 项目结构与核心代码

```text
src/linguacaption/
  app.py                 # CLI / QApplication 入口
  ui.py                  # 工作台、样式、模型配置、会话记录
  overlay.py             # 逐行渲染、字形描边、置顶拖拽、保护区框选
  audio.py               # WASAPI / Mac PCM 管道、连续重采样
  inference.py           # 本地 Whisper / M2M100，模型完整性检查
  engine.py              # 会话生命周期、后台管线、版本隔离、过载处理
  domain.py              # 带时间戳和版本的音频/字幕数据
  config.py              # 12 语言、可验证配置、原子保存
  core/
    segmenter.py         # 20 ms VAD、预录、增量快照、停顿与强制分段
    mailbox.py           # 同语句更新合并及有界队列
    layout.py            # 确定性安全区避让算法，无法容纳则返回 None
    text.py              # Unicode 字素边界、字数/像素双重换行
  native/
    hotkeys.py           # Windows RegisterHotKey / Mac pynput
    window.py            # Windows 合成效果 / Mac NSVisualEffectView
    macos/               # ScreenCaptureKit Swift 源码与权限清单
scripts/
  prepare_models.py      # 显式下载、量化转换、模型来源清单
  benchmark.py           # 真实模型 + 本地音频按播放速度重放，WER/CER 与延迟
  render_preview.py      # 仅渲染本应用 Qt 控件到 PNG
  build_macos.sh         # 编译 Mac 原生系统音频辅助程序
  package.py             # 在目标系统打包桌面应用
tests/                   # 几何、分段、重采样、并发、界面与异常流程
docs/                    # 架构、验收口径、本次验证记录、预览图
.github/workflows/ci.yml # Windows/Mac 测试和 Mac Swift 编译
```

工程默认 CPU 识别 4 线程、翻译 2 线程。Mac 使用 CPU；本版未接入 Metal。NVIDIA 用户可手动选择 CUDA 及匹配的 compute type，并按照 [faster-whisper 的 GPU 要求](https://github.com/SYSTRAN/faster-whisper#gpu) 安装匹配的 CUDA/cuDNN。

参与开发可参考 [贡献说明](CONTRIBUTING.md)。

## 验证与打包

```bash
python -m pytest -q
python -m ruff check .
python scripts/benchmark.py --audio sample.wav --asr-model models/asr \
  --translation-model models/translation --language en --target zh \
  --reference reference.txt --metric wer --output local/benchmark.json
python scripts/package.py
```

PowerShell 中请将基准命令写为一行，或使用 PowerShell 的续行方式。安装 `.[build]` 后在目标 Windows/Mac 平台打包，模型默认随程序一起放入 `dist/`。使用 `scripts/distribute.py` 生成安装程序、免安装 ZIP 或 DMG；具体命令见 [桌面发行指南](docs/DESKTOP.md)。

请阅读 [架构说明](docs/ARCHITECTURE.md)、[验收方案](docs/ACCEPTANCE.md) 和 [本次验证结果](docs/VALIDATION.md)。截至本次验证，Windows 环境完成控件渲染与自动化测试、真实模型音频重放；系统内录、Mac 权限及全屏跨应用叠加需要目标设备联调。

## 平台边界

- 普通播放器、浏览器和直播声音均通过系统输出端点处理。受保护媒体、独占全屏、特殊音频路由或远程会话可能限制内录和叠加；建议无边框全屏/窗口模式。切换输出设备后请重新开始捕获。
- Mac 首次点击捕获会触发 ScreenCaptureKit 的系统授权；在「隐私与安全性 → 屏幕与系统音频录制」中允许相关应用，必要时完全退出后重启。程序只订阅音频输出，最小视频配置不生成或保存屏幕文件。
- Windows 磨砂使用可探测的系统合成接口，该接口没有稳定公开契约；系统版本、远程桌面、透明效果设置或辅助功能设置可能令其不可用。Mac 使用 NSVisualEffectView。不可用时保留可读的半透明背景；跨平台真机效果尚待验收。
- Whisper 采用滚动语句快照，短上下文可能改写前文，背景音乐可能误触发 VAD。模型选择、口音、混音和硬件直接影响延迟与准确度。

## 上游来源

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)：本地 Whisper 推理
- [CTranslate2](https://github.com/OpenNMT/CTranslate2) 与 [M2M100 模型卡](https://huggingface.co/facebook/m2m100_418M)：多语言本地翻译
- [SoundCard](https://github.com/bastibe/SoundCard) 与 [Microsoft WASAPI loopback](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording)：Windows 输出端点采集
- [Apple ScreenCaptureKit](https://developer.apple.com/documentation/screencapturekit/capturing-screen-content-in-macos)：Mac 原生采集
- [Qt for Python](https://doc.qt.io/qtforpython-6/)：桌面界面和透明窗口

项目原创代码采用 MIT，见 LICENSE。依赖、模型和重新分发的 Qt 组件仍受各自许可证约束；模型权重未随源码分发。
