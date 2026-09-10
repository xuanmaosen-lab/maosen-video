# 茂森视频工作室 · Maosen Video

Copyright 2026 xuanmaosen-lab. Licensed under Apache-2.0; see LICENSE.

项目仓库：[xuanmaosen-lab/maosen-video](https://github.com/xuanmaosen-lab/maosen-video)。

一套从零编写的本地视频编辑 CLI 与 AI Agent skill。使用显式时间轴把视频、图卡、字幕和圆形人物小窗组合成成片；先确认素材来源和转场需求，再开始制作。

这是首个可运行版本，不是其他项目的换名发行，也不宣称已经实现参考项目的全部功能。技术路线是 Python、Pillow 和 FFmpeg，无 Node/Remotion 依赖，无内置云服务、账号或 API 密钥。

## 能力

- 精确到帧的顺序剪辑、视频／图片／原创文字卡；显式原声音轨。
- 等比裁剪的圆形小窗，可指定位置、直径与取景中心。
- 直接切换或画面／音频交叉溶解，自动计算重叠后的总时长。
- 中文字幕图层、SRT、可编辑 JSON、逐素材哈希与结构性检查报告。
- 生成素材须记录生成方式；不自动下载或上传内容，不覆盖输出目录。

脚本理解、分镜设计和素材生成由调用 skill 的 Agent 按用户授权完成。此 CLI 不会自行调用模型或假装已生成图片／语音。

## 运行

下载此 skill（目标目录已存在时不要重复克隆或覆盖）：

```bash
git clone https://github.com/xuanmaosen-lab/maosen-video.git ~/.claude/skills/maosen-video
cd ~/.claude/skills/maosen-video
```

用于 Codex 时，可将目标目录换成 `~/.codex/skills/maosen-video`。本项目使用 Python，不使用旧项目的 `npm install`。

需要 Python 3.10+、Pillow 10–12、FFmpeg/ffprobe（须支持 libx264、AAC、xfade、geq、overlay）。先在自己的环境准备依赖，再运行：

```bash
python scripts/studio.py doctor
python scripts/studio.py init timeline.json
# 按 references/timeline.md 填写媒体、选择和分镜
python scripts/studio.py validate timeline.json
python scripts/studio.py render timeline.json --out output-v01
```

CLI 不自动安装软件。FFmpeg 及系统字体不随项目分发。不同 FFmpeg 构建可能有不同许可证；Pillow、Python、字体和媒体仍遵守其各自许可。

## 测试

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python tests/smoke.py /absolute/path/to/new-smoke-directory
```

集成测试使用本地产生的色彩图与测试音，不使用私人视频。详细输入和已知限制见 [时间轴说明](references/timeline.md)。入口见 [SKILL.md](SKILL.md)。

## 实现来源与许可范围

本项目按用户提出的功能目标重新设计实现，没有复制参考项目的代码、图片、模板或文档。制作方曾阅读参考项目，因此不声称采用了严格隔离的 clean-room 流程，也不作绝对不侵权保证。Apache-2.0 只覆盖本项目原创文件，不把第三方依赖、字体或用户素材变成用户的专属版权。
