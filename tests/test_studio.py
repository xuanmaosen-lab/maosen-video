# Copyright 2026 xuanmaosen-lab
# SPDX-License-Identifier: Apache-2.0
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('studio', Path(__file__).parents[1]/'scripts/studio.py')
studio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio)


def base():
    return {'version': 1, 'canvas': {'width': 320, 'height': 568, 'fps': 24},
            'choices': {'assets': 'yes', 'transitions': 'no'}, 'assets': {},
            'scenes': [{'kind': 'card', 'frames': 48, 'title': '测试主题', 'points': ['保留主要内容']}], 'captions': []}


class Validation(unittest.TestCase):
    def check_invalid(self, change):
        doc = base()
        change(doc)
        with self.assertRaises(studio.Invalid):
            studio.validate(doc, Path.cwd(), inspect_media=False)

    def test_valid(self):
        self.assertEqual(studio.validate(base(), Path.cwd()), 48)

    def test_pending_choice(self):
        self.check_invalid(lambda d: d['choices'].update(assets='pending'))

    def test_declined_graphic(self):
        self.check_invalid(lambda d: d['choices'].update(assets='no'))

    def test_odd_size(self):
        self.check_invalid(lambda d: d['canvas'].update(width=321))

    def test_nan(self):
        self.check_invalid(lambda d: d['canvas'].update(fps=float('nan')))

    def test_fractional_frames(self):
        self.check_invalid(lambda d: d['scenes'][0].update(frames=1.5))

    def test_float_fps(self):
        self.check_invalid(lambda d: d['canvas'].update(fps=24.0))

    def test_blank_title(self):
        self.check_invalid(lambda d: d['scenes'][0].update(title=''))

    def test_empty_scene_list(self):
        self.check_invalid(lambda d: d.update(scenes=[]))

    def test_zero_frames(self):
        self.check_invalid(lambda d: d['scenes'][0].update(frames=0))

    def test_unsupported_scene(self):
        self.check_invalid(lambda d: d['scenes'][0].update(kind='shell'))

    def test_remote_media(self):
        with self.assertRaises(studio.Invalid):
            studio.local_file('https://example.com/a.mp4', Path.cwd())

    def test_missing_file(self):
        with self.assertRaises(studio.Invalid):
            studio.local_file('/nonexistent-maosen-test.mp4', Path.cwd())

    def test_overlapping_captions(self):
        self.check_invalid(lambda d: d.update(captions=[{'from': 0, 'to': 24, 'text': '甲'}, {'from': 23, 'to': 40, 'text': '乙'}]))

    def test_out_of_range_caption(self):
        self.check_invalid(lambda d: d.update(captions=[{'from': 0, 'to': 49, 'text': '甲'}]))

    def test_first_scene_transition(self):
        self.check_invalid(lambda d: d['scenes'][0].update(transition={'type': 'dissolve', 'frames': 12}))

    def test_declined_transition(self):
        def change(d):
            d['scenes'].append({'kind': 'card', 'frames': 48, 'title': '乙', 'transition': {'type': 'dissolve', 'frames': 12}})
        self.check_invalid(change)

    def test_overlap_duration(self):
        d = base()
        d['choices']['transitions'] = 'yes'
        d['scenes'].append({'kind': 'card', 'frames': 48, 'title': '乙', 'transition': {'type': 'dissolve', 'frames': 12}})
        self.assertEqual(studio.validate(d, Path.cwd()), 84)

    def test_overwrite_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'a.json'
            studio.save_json(p, {'a': 1})
            with self.assertRaises(FileExistsError):
                studio.save_json(p, {'a': 2})
            self.assertEqual(json.loads(p.read_text()), {'a': 1})

    def test_srt_rounding(self):
        self.assertEqual(studio.timestamp(24, 24), '00:00:01,000')
        self.assertEqual(studio.timestamp(1, 24), '00:00:00,042')

    def test_generated_asset_without_choice(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'media.dat'
            p.touch()
            d = base()
            d['assets'] = {'a': {'path': str(p), 'origin': 'generated', 'source': 'synthetic', 'rights': 'test', 'generation_tool': 'test'}}
            with self.assertRaises(studio.Invalid):
                studio.validate(d, Path(folder), inspect_media=False)


if __name__ == '__main__':
    unittest.main()
