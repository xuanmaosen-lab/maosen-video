# 时间轴约定 v1

Copyright 2026 xuanmaosen-lab. SPDX-License-Identifier: Apache-2.0

输入是 UTF-8 JSON。帧率为整数；片段长度与字幕边界使用整数帧，避免秒的小数累计误差。源码位置不影响工作目录；媒体相对路径以输入 JSON 的目录为基准。导出 JSON 将媒体与字体路径展开为绝对路径，便于在本机继续编辑；分享工程前需要将资产打包并替换路径，避免泄露个人目录信息。

## 最小例子

```json
{
  "version": 1,
  "canvas": {"width": 1080, "height": 1920, "fps": 24},
  "choices": {"assets": "no", "transitions": "no"},
  "assets": {
    "host": {"path": "input.mp4", "origin": "user", "source": "用户提供原片", "rights": "用户授权本次剪辑"}
  },
  "scenes": [
    {"kind": "video", "asset": "host", "start": 2, "frames": 120, "audio": {"asset": "host", "start": 2}}
  ],
  "captions": [{"from": 0, "to": 48, "text": "这里填写核对过的字幕"}]
}
```

`audio` 必须显式指定；没有此字段就输出静音，不会悄悄混入素材自带的音乐。视频也不会自动跟随外部配音伸缩。先根据原声或已生成音频时长确定片段。

## 素材与转场

`choices.assets` 和 `choices.transitions` 各取 `yes` 或 `no`，初始 `pending` 会阻止渲染。`choices.generation` 可取 `direct` 或 `specified`，后者还需要 `generation_location`。

每个资产必须有 `path / origin / source / rights`；origin 是 `user`、`generated` 或 `licensed`。生成资产还要登记 `generation_tool`。这些字段用于来源记录，不自动验证版权权属。

片段类型：

- `video`：等比放大填充并中心裁剪，`start` 为素材起始秒。
- `image`：循环静态本地图片。
- `card`：原创深蓝信息卡，`title`（最多 60 字符）和 `points`（最多四项）。实际排版放不下会报错，需缩短内容。概念示意标签不用于冒充真实行情。

在任何片段加 `pip` 即可显示圆形人物窗：

```json
{"asset":"host","start":2,"diameter":304,"x":704,"y":252,"center_x":0.5,"center_y":0.4,"crop_fraction":0.8}
```

中心坐标相对于输入画面宽高归一化至 0–1，裁剪边长为素材短边乘 `crop_fraction`，不拉伸；靠近边缘时裁剪框限制在素材内。此版没有自动面部跟踪或全屏到小窗的缩放形变，需人工设中心或拆分镜头。

`transition` 是进入该场景的效果：`{"type":"cut","frames":0}` 或 `{"type":"dissolve","frames":12}`。第一场景不能溶解入场。溶解会重叠画面和音频；总帧数为各片段帧数之和减去重叠帧。口播不宜重叠说话时使用直接切换。

字幕以成片全局帧计时，区间为 `[from,to)`，不能重叠。内置排版使用 Pillow 生成透明文字图层，不需要 FFmpeg 的 libass。可用 `font` 指定本地字体路径，中文字体需由使用者合法提供；不在仓库内分发系统字体。

## 输出与可复现性

每次选择新输出目录。输出包含 `final.mp4`、`audio.m4a`、`captions.srt`、`timeline.json`、分段视频、文字图层、`manifest.json`、`qa.json`。清单记录素材 SHA-256 与 FFmpeg 版本；跨 FFmpeg/字体版本不承诺逐字节一致。

格式：H.264、yuv420p、AAC、48kHz 双声道。结构检查覆盖解码、帧数、时长、分辨率、帧率与音轨存在性；无自动语义、口型或内容真实性认证。当前不支持背景音乐闪避、云配音、联网素材抓取、自动转写、变速、人脸追踪、图形关键帧或 GUI 时间轴。
