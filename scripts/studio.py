#!/usr/bin/env python3
# Copyright 2026 xuanmaosen-lab
# SPDX-License-Identifier: Apache-2.0
"""Local, explicit-timeline video editing. No cloud access or shell evaluation."""
import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path


class Invalid(ValueError):
    pass


def run(args, cwd=None):
    result = subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True)
    if result.returncode:
        raise Invalid(result.stderr.decode(errors='replace')[-6000:])
    return result.stdout


def probe(file):
    return json.loads(run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_format', '-show_streams', '-of', 'json', file]))


def local_file(value, root):
    if not isinstance(value, str) or not value or '://' in value:
        raise Invalid('Media must be a local file path')
    p = (root / value).resolve()
    if not p.is_file():
        raise Invalid(f'Missing file: {p}')
    return p


def number(value, label, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise Invalid(f'{label}: finite number required')
    if not low <= value <= high or (integer and not isinstance(value, int)):
        raise Invalid(f'{label}: out of range [{low}, {high}]')
    return value


def text(value, label, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise Invalid(f'{label}: nonempty text, max {maximum} characters')


def validate(doc, root, inspect_media=True):
    if doc.get('version') != 1:
        raise Invalid('Unsupported timeline version')
    canvas = doc['canvas']
    for key in ('width', 'height'):
        n = number(canvas[key], key, 160, 3840, True)
        if n % 2:
            raise Invalid('Canvas dimensions must be even')
    fps = number(canvas['fps'], 'fps', 12, 60, True)
    choices = doc['choices']
    for key in ('assets', 'transitions'):
        if choices.get(key) not in ('yes', 'no'):
            raise Invalid(f'Ask the user about {key} before rendering')
    assets = doc.get('assets', {})
    for key, item in assets.items():
        if not re.fullmatch(r'[A-Za-z0-9_-]+', key):
            raise Invalid('Asset IDs use letters, numbers, underscore or dash')
        local_file(item['path'], root)
        for field in ('source', 'rights'):
            text(item.get(field), f'{key}.{field}')
        if item.get('origin') not in ('user', 'generated', 'licensed'):
            raise Invalid(f'{key}: unknown asset origin')
        if item['origin'] == 'generated':
            text(item.get('generation_tool'), f'{key}.generation_tool')
            if choices.get('generation') not in ('direct', 'specified'):
                raise Invalid('Generated assets need explicit generation choice')
            if choices['generation'] == 'specified':
                text(choices.get('generation_location'), 'generation_location')
    scenes = doc.get('scenes')
    if not isinstance(scenes, list) or not scenes or len(scenes) > 200:
        raise Invalid('Provide 1 to 200 scenes')
    cache = {}

    def media(asset_id, stream, start, duration, still=False):
        if asset_id not in assets:
            raise Invalid(f'Unknown asset: {asset_id}')
        p = local_file(assets[asset_id]['path'], root)
        if not inspect_media:
            return
        if p not in cache:
            cache[p] = probe(p)
        info = cache[p]
        streams = [s for s in info['streams'] if s['codec_type'] == stream]
        if not streams:
            raise Invalid(f'{asset_id}: missing {stream} stream')
        if not still:
            length = float(streams[0].get('duration', info.get('format', {}).get('duration', 0)))
            if start + duration > length + 1 / fps:
                raise Invalid(f'{asset_id}: requested range exceeds duration {length}')

    for i, s in enumerate(scenes):
        frames = number(s['frames'], 'frames', 1, 216000, True)
        duration = frames / fps
        kind = s['kind']
        if kind not in ('video', 'image', 'card'):
            raise Invalid('Scene kind must be video, image or card')
        start = number(s.get('start', 0), 'start', 0, 86400)
        if kind != 'card':
            media(s['asset'], 'video', start, duration, kind == 'image')
            if kind == 'image' and choices['assets'] == 'no':
                raise Invalid('Supplementary images were declined')
        else:
            if choices['assets'] == 'no':
                raise Invalid('Supplementary cards were declined')
            text(s.get('title'), 'card title', 60)
            if not isinstance(s.get('points', []), list) or len(s.get('points', [])) > 4:
                raise Invalid('Cards support at most four points')
            for point in s.get('points', []):
                text(point, 'card point', 80)
        voice = s.get('audio')
        if voice:
            astart = number(voice.get('start', 0), 'audio.start', 0, 86400)
            media(voice['asset'], 'audio', astart, duration)
        pip = s.get('pip')
        if pip:
            if choices['assets'] == 'no':
                raise Invalid('PiP needs supplementary layout approval')
            media(pip['asset'], 'video', number(pip.get('start', 0), 'pip.start', 0, 86400), duration)
            for key in ('center_x', 'center_y'):
                number(pip.get(key, .5), key, 0, 1)
            size = number(pip['diameter'], 'diameter', 32, min(canvas['width'], canvas['height']), True)
            if size % 2:
                raise Invalid('Circle diameter must be even')
            number(pip.get('crop_fraction', 1), 'crop_fraction', .1, 1)
            number(pip['x'], 'pip.x', 0, canvas['width'] - size, True)
            number(pip['y'], 'pip.y', 0, canvas['height'] - size, True)
        fade = s.get('transition', {'type': 'cut', 'frames': 0})
        if fade['type'] not in ('cut', 'dissolve'):
            raise Invalid('Supported transitions: cut, dissolve')
        count = number(fade.get('frames', 0), 'transition.frames', 0, frames - 1, True)
        if fade['type'] == 'cut' and count:
            raise Invalid('Cut has zero overlap')
        if fade['type'] == 'dissolve':
            if i == 0 or choices['transitions'] == 'no' or count < 1 or count >= scenes[i-1]['frames']:
                raise Invalid('Invalid dissolve or transitions not approved')
            # Prevent three simultaneous scenes from overlapping.
            previous = scenes[i-1].get('transition', {}).get('frames', 0)
            if count + previous >= scenes[i-1]['frames']:
                raise Invalid('Adjacent overlaps leave no exclusive scene time')
    total = sum(s['frames'] - s.get('transition', {}).get('frames', 0) for s in scenes)
    previous = 0
    for c in doc.get('captions', []):
        a = number(c['from'], 'caption.from', previous, total - 1, True)
        b = number(c['to'], 'caption.to', a + 1, total, True)
        text(c['text'], 'caption.text', 120)
        previous = b
    return total


def save_json(path, value):
    with path.open('x', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def font_path(doc, root):
    supplied = doc.get('font')
    if supplied:
        return str(local_file(supplied, root))
    candidates = ['/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
                  '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                  'C:/Windows/Fonts/msyh.ttc']
    for value in candidates:
        if Path(value).is_file():
            return value
    raise Invalid('Set font to a local font that covers the script language')


def wrapped(draw, value, font, width):
    lines = []
    for paragraph in value.splitlines():
        line = ''
        for char in paragraph:
            if line and draw.textlength(line + char, font=font) > width:
                lines.append(line)
                line = char
            else:
                line += char
        lines.append(line)
    return '\n'.join(lines)


def graphic(path, doc, root, scene=None, caption=None):
    from PIL import Image, ImageDraw, ImageFont
    w, h = doc['canvas']['width'], doc['canvas']['height']
    im = Image.new('RGBA', (w, h), '#102A3B' if scene else (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    font = font_path(doc, root)
    if scene:
        margin = round(w * .07)
        title_font = ImageFont.truetype(font, max(16, round(w * .065)))
        body_font = ImageFont.truetype(font, max(12, round(w * .042)))
        max_width = w - 2 * margin
        if scene.get('pip') and scene['pip']['y'] < h*.3:
            max_width = min(max_width, scene['pip']['x'] - 2 * margin)
        if max_width < w*.2:
            raise Invalid('Move PiP to leave room for the card title')
        title = wrapped(draw, scene['title'], title_font, max_width)
        box = draw.multiline_textbbox((margin, h * .12), title, font=title_font, spacing=8)
        if box[3] > h * .38:
            raise Invalid('Card title too long for layout')
        draw.multiline_text((margin, h * .12), title, font=title_font, fill='#F4F3EA', spacing=8)
        for i, point in enumerate(scene.get('points', [])):
            top = int(h * (.40 + .095 * i))
            draw.rounded_rectangle((margin, top, w-margin, top+int(h*.078)), radius=8, fill='#1D3D50')
            draw.rectangle((margin, top, margin+4, top+int(h*.078)), fill='#CEBA7C')
            label = wrapped(draw, point, body_font, w - 2*margin - 28)
            bounds = draw.multiline_textbbox((margin+14, top+7), label, font=body_font, spacing=2)
            if bounds[3] > top+int(h*.078)-3:
                raise Invalid('Card point too long for layout')
            draw.multiline_text((margin+14, top+7), label, font=body_font, fill='white', spacing=2)
        draw.text((margin, h*.94), '概念示意 · 非实时数据', font=ImageFont.truetype(font, max(10, round(w*.022))), fill='#9BB0BE')
    if caption:
        f = ImageFont.truetype(font, max(14, round(w * .042)))
        label = wrapped(draw, caption, f, w*.86)
        bounds = draw.multiline_textbbox((0, 0), label, font=f, spacing=5, stroke_width=1)
        th = bounds[3]-bounds[1]
        if th > h*.18:
            raise Invalid('Caption exceeds safe height; split into shorter cues')
        x, y = (w-(bounds[2]-bounds[0]))/2, h*.86-th
        draw.rounded_rectangle((x-10, y-7, w-x+10, y+th+12), radius=8, fill=(0, 0, 0, 170))
        draw.multiline_text((x, y-bounds[1]), label, font=f, fill='white', stroke_width=1, stroke_fill='black', spacing=5, align='center')
    im.save(path)


def ffmpeg(args, out, cwd):
    local_args = []
    for arg in args:
        if arg == '-i':
            local_args += ['-protocol_whitelist', 'file,pipe']
        local_args.append(arg)
    run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-n',
         '-filter_complex_threads', '1', *local_args, out], cwd)


def encode():
    return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2', '-movflags', '+faststart']


def timestamp(frames, fps):
    ms = round(frames * 1000 / fps)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}'


def render(doc, root, out):
    total = validate(doc, root)
    out.mkdir(parents=True, exist_ok=False)
    snapshot = json.loads(json.dumps(doc))
    for item in snapshot.get('assets', {}).values():
        item['path'] = str(local_file(item['path'], root))
    if snapshot.get('font'):
        snapshot['font'] = str(local_file(snapshot['font'], root))
    save_json(out / 'timeline.json', snapshot)
    w, h, fps = (doc['canvas'][k] for k in ('width', 'height', 'fps'))
    asset = lambda key: str(local_file(doc['assets'][key]['path'], root))
    for i, s in enumerate(doc['scenes']):
        duration = s['frames']/fps
        args = []
        if s['kind'] == 'card':
            graphic(out / f'card-{i}.png', doc, root, scene=s)
            args += ['-loop', '1', '-framerate', fps, '-i', f'card-{i}.png']
        elif s['kind'] == 'image':
            args += ['-loop', '1', '-framerate', fps, '-i', asset(s['asset'])]
        else:
            args += ['-ss', s.get('start', 0), '-i', asset(s['asset'])]
        graph = [f'[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps},trim=end_frame={s["frames"]},setpts=PTS-STARTPTS,format=yuv420p[base]']
        index = 1
        video = 'base'
        if s.get('pip'):
            p = s['pip']
            d = p['diameter']
            args += ['-ss', p.get('start', 0), '-i', asset(p['asset'])]
            crop = p.get('crop_fraction', 1)
            cx, cy = p.get('center_x', .5), p.get('center_y', .5)
            side = f'trunc(min(iw,ih)*{crop}/2)*2'
            graph += [f"[{index}:v]fps={fps},setpts=PTS-STARTPTS,crop=w='{side}':h='{side}':x='max(0,min(iw-ow,iw*{cx}-ow/2))':y='max(0,min(ih-oh,ih*{cy}-oh/2))',scale={d}:{d},setsar=1,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(pow(X-(W-1)/2,2)+pow(Y-(H-1)/2,2),pow(min(W,H)/2-1,2)),255,0)'[circle]",
                      f'[base][circle]overlay={p["x"]}:{p["y"]}:eof_action=pass[composite]']
            video = 'composite'
            index += 1
        a = s.get('audio')
        if a:
            args += ['-ss', a.get('start', 0), '-i', asset(a['asset'])]
            graph += [f'[{index}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={duration},asetpts=PTS-STARTPTS[voice]']
        else:
            args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
            graph += [f'[{index}:a]atrim=duration={duration},asetpts=PTS-STARTPTS[voice]']
        ffmpeg(args + ['-filter_complex', ';'.join(graph), '-map', f'[{video}]', '-map', '[voice]', '-t', duration, *encode()], f'scene-{i:03}.mp4', out)
        print(f'Rendered scene {i+1}/{len(doc["scenes"])}', flush=True)
    args = []
    for i in range(len(doc['scenes'])):
        args += ['-i', f'scene-{i:03}.mp4']
    graph = []
    for i in range(len(doc['scenes'])):
        graph += [f'[{i}:v]settb=AVTB,setpts=PTS-STARTPTS[v{i}]', f'[{i}:a]asetpts=PTS-STARTPTS[a{i}]']
    v, a, length = 'v0', 'a0', doc['scenes'][0]['frames']
    for i, s in enumerate(doc['scenes'][1:], 1):
        overlap = s.get('transition', {}).get('frames', 0)
        nv, na = f'joinedv{i}', f'joineda{i}'
        if overlap:
            graph += [f'[{v}][v{i}]xfade=transition=fade:duration={overlap/fps}:offset={(length-overlap)/fps}[{nv}]',
                      f'[{a}][a{i}]acrossfade=d={overlap/fps}:c1=tri:c2=tri[{na}]']
        else:
            graph += [f'[{v}][{a}][v{i}][a{i}]concat=n=2:v=1:a=1[{nv}][{na}]']
        v, a = nv, na
        length += s['frames']-overlap
    ffmpeg(args + ['-filter_complex', ';'.join(graph), '-map', f'[{v}]', '-map', f'[{a}]', '-r', fps, '-t', total/fps, *encode()], 'picture.mp4', out)
    captions = doc.get('captions', [])
    if captions:
        args = ['-i', 'picture.mp4']
        graph, label = [], '0:v'
        for i, c in enumerate(captions):
            graphic(out/f'caption-{i:03}.png', doc, root, caption=c['text'])
            args += ['-loop', '1', '-framerate', fps, '-i', f'caption-{i:03}.png']
            next_label = f'captioned{i}'
            graph += [f"[{label}][{i+1}:v]overlay=0:0:enable='gte(n,{c['from']})*lt(n,{c['to']})'[{next_label}]"]
            label = next_label
        ffmpeg(args + ['-filter_complex', ';'.join(graph), '-map', f'[{label}]', '-map', '0:a', '-t', total/fps, *encode()], 'final.mp4', out)
    else:
        shutil.copyfile(out/'picture.mp4', out/'final.mp4')
    with (out/'captions.srt').open('x', encoding='utf8') as f:
        for i, c in enumerate(captions, 1):
            f.write(f"{i}\n{timestamp(c['from'], fps)} --> {timestamp(c['to'], fps)}\n{c['text']}\n\n")
    ffmpeg(['-i', 'final.mp4', '-vn', '-c:a', 'copy'], 'audio.m4a', out)
    report = qa(out/'final.mp4', total, fps, w, h)
    save_json(out/'qa.json', report)
    provenance = {key: {'sha256': digest(local_file(item['path'], root)), **item} for key, item in doc.get('assets', {}).items()}
    save_json(out/'manifest.json', {'version': 1, 'frames': total, 'assets': provenance, 'final_sha256': digest(out/'final.mp4'), 'qa': report, 'ffmpeg': run(['ffmpeg', '-version']).decode().splitlines()[0]})
    if not report['passed']:
        raise Invalid('Structural QA failed; inspect qa.json before delivery')
    return report


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def qa(file, frames=None, fps=None, width=None, height=None):
    info = probe(file)
    v = next(s for s in info['streams'] if s['codec_type'] == 'video')
    audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
    decode = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-i', str(file), '-f', 'null', '-'], capture_output=True)
    expected = frames/fps if frames is not None else None
    duration = float(info['format']['duration'])
    checks = {'decodes': decode.returncode == 0 and not decode.stderr.strip(), 'audio_present': audio is not None}
    if frames is not None:
        checks.update(frame_count=int(v.get('nb_frames', 0)) == frames,
                      duration=abs(duration-expected) <= 1/fps,
                      dimensions=v['width'] == width and v['height'] == height,
                      fps=v['avg_frame_rate'] == f'{fps}/1')
    return {'passed': all(checks.values()), 'checks': checks, 'duration': duration, 'width': v['width'], 'height': v['height'],
            'limits': 'Structural checks only; review captions, lip sync, visual framing and source claims separately.'}


def example():
    return {'version': 1, 'canvas': {'width': 1080, 'height': 1920, 'fps': 24},
            'choices': {'assets': 'pending', 'transitions': 'pending', 'generation': None},
            'assets': {}, 'scenes': [{'kind': 'card', 'frames': 120, 'title': '填写已确认主题', 'points': ['填写核心观点']}], 'captions': []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    for name in ('inspect', 'init', 'validate', 'qa', 'render'):
        p = sub.add_parser(name)
        p.add_argument('file', type=Path)
        if name == 'render':
            p.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'doctor':
            import PIL
            result = {'python': sys.version.split()[0], 'pillow': PIL.__version__, 'ffmpeg': shutil.which('ffmpeg'), 'ffprobe': shutil.which('ffprobe')}
        elif args.command == 'init':
            save_json(args.file, example())
            result = {'timeline': str(args.file), 'next': 'Confirm choices and edit timeline'}
        elif args.command == 'inspect':
            result = probe(local_file(str(args.file), Path.cwd()))
        elif args.command == 'qa':
            result = qa(args.file.resolve())
        else:
            doc = json.loads(args.file.read_text(encoding='utf8'))
            root = args.file.resolve().parent
            result = {'frames': validate(doc, root)} if args.command == 'validate' else render(doc, root, args.out.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (Invalid, KeyError, TypeError, OSError, StopIteration, ImportError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
