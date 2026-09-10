# Copyright 2026 xuanmaosen-lab
# SPDX-License-Identifier: Apache-2.0
"""Create an original synthetic fixture; exercise video, circle, audio, captions and fades."""
import argparse
import json
from pathlib import Path
from test_studio import studio, base

p = argparse.ArgumentParser()
p.add_argument('directory', type=Path)
args = p.parse_args()
folder = args.directory.resolve()
folder.mkdir(parents=True, exist_ok=False)
studio.run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-f', 'lavfi', '-i', 'testsrc2=size=320x568:rate=24',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '3',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', folder/'fixture.mp4'])
d = base()
d['choices'] = {'assets': 'yes', 'transitions': 'yes', 'generation': 'direct'}
d['assets'] = {'host': {'path': 'fixture.mp4', 'origin': 'generated', 'source': 'Local mathematical test pattern',
                        'rights': 'Synthetic test fixture; no personal media', 'generation_tool': 'FFmpeg lavfi'}}
d['scenes'] = [
    {'kind': 'video', 'asset': 'host', 'frames': 48, 'audio': {'asset': 'host', 'start': 0}},
    {'kind': 'card', 'frames': 48, 'title': '圆形小窗', 'points': ['人物居中裁剪', '素材来源先确认', '字幕与原声保留'],
     'audio': {'asset': 'host', 'start': .5},
     'pip': {'asset': 'host', 'start': .5, 'diameter': 80, 'x': 218, 'y': 32, 'center_x': .5, 'center_y': .5, 'crop_fraction': .8},
     'transition': {'type': 'dissolve', 'frames': 12}},
    {'kind': 'card', 'frames': 48, 'title': '原创实现', 'points': ['可编辑时间轴', '本地导出与检查'],
     'audio': {'asset': 'host', 'start': 0}, 'transition': {'type': 'cut', 'frames': 0}}
]
d['captions'] = [{'from': 0, 'to': 36, 'text': '这是本地生成的测试画面'},
                 {'from': 48, 'to': 80, 'text': '圆形裁剪与字幕测试'},
                 {'from': 84, 'to': 132, 'text': '茂森视频工作室'}]
studio.save_json(folder/'timeline.json', d)
report = studio.render(d, folder, folder/'output-v01')
for name, frame in [('opening', 12), ('transition', 42), ('circle', 60), ('ending', 108)]:
    studio.run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-i', folder/'output-v01/final.mp4',
                '-vf', f'select=eq(n\\,{frame})', '-frames:v', '1', folder/f'{name}.png'])
from PIL import Image
im = Image.open(folder/'circle.png').convert('RGB')
corner = im.getpixel((220, 34))
center = im.getpixel((258, 72))
navy = (16, 42, 59)
assert max(abs(a-b) for a,b in zip(corner, navy)) < 15, corner
assert sum(abs(a-b) for a,b in zip(center, navy)) > 40, center
assert report['passed']
assert len((folder/'output-v01/captions.srt').read_text().strip().split('\n\n')) == 3
snapshot = json.loads((folder/'output-v01/timeline.json').read_text())
assert studio.validate(snapshot, folder/'output-v01') == 132
still = base()
still['assets'] = {'still': {'path': 'circle.png', 'origin': 'generated', 'source': 'Own local smoke render',
                           'rights': 'Original test image', 'generation_tool': 'Maosen Video'}}
still['choices']['generation'] = 'direct'
still['scenes'] = [{'kind': 'image', 'asset': 'still', 'frames': 24}]
still_report = studio.render(still, folder, folder/'image-silent-v01')
assert still_report['passed']
for bad_scene in [dict(d['scenes'][0], start=2), dict(d['scenes'][1], pip=dict(d['scenes'][1]['pip'], x=319))]:
    invalid = dict(d, scenes=[bad_scene], captions=[])
    try:
        studio.validate(invalid, folder)
    except studio.Invalid:
        pass
    else:
        raise AssertionError('Expected invalid media range or geometry to be rejected')
try:
    studio.render(d, folder, folder/'output-v01')
except FileExistsError:
    pass
else:
    raise AssertionError('Existing render directory must not be overwritten')
pcm = studio.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', folder/'output-v01/final.mp4', '-vn', '-ac', '1', '-f', 's16le', '-'])
import array
samples = array.array('h', pcm)
assert max(abs(n) for n in samples) > 1000, 'Expected audible synthetic test tone'
print(json.dumps({'passed': True, 'circle_corner': corner, 'circle_center': center, 'report': report}, ensure_ascii=False))
