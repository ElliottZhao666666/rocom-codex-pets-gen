"""Behavioral checks use temporary, synthetic data; no character assets are shipped."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from color_appearance import (ChoiceRequired, TYPES, inspect_appearances,
                              resolve_appearance, validate_effect_resources)
from validate_input import InputError


class ColorAppearanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.shared = self.root/'effects/glassy'
        self.shared.mkdir(parents=True)
        for name in ['Tex_PetGlassy_007_D', 'shape', 'season_main', 'season_star', 'T_EMeng002', 'T_EMeng003']:
            Image.new('RGBA', (1, 1), (127, 128, 0, 255)).save(self.shared/(name+'.png'))
        self.catalog = {
            'colors': [{'id': 101, 'name': '测试配色', 'red_channel': [1.6, .1, .2], 'green_channel': [.2, 1, .3]}],
            'particles': [{'id': 103, 'name': '测试纹样', 'tex': 'shape'}],
            'hidden': [
                {'id': 9999, 'name': '黑白', 'season': False, 'main_tex': 'season_main', 'star_tex': 'season_star', 'red_channel': [.6]*3, 'green_channel': [.01]*3},
                {'id': 71, 'name': '测试赛季甲', 'season': True, 'season_no': 1, 'main_tex': 'season_main', 'star_tex': 'season_star', 'red_channel': [1]*3, 'green_channel': [.1]*3},
            ],
            'pollution': {'ui_color_1': 123},
        }
        self.form = {'materials': {'Body': {'glassy_id_tex': 'forms/Example_001/tex/mask.png'}}}
        self.write_catalog()

    def tearDown(self):
        self.temp.cleanup()

    def entity(self, palette='normal'):
        return {'entity_id': 123, 'asset': 'Example_001', 'appearance': palette,
                'identity': {'entity_id': 123, 'form_asset': 'Example_001', 'palette': palette}}

    def write_catalog(self):
        (self.shared/'glassy.json').write_text(json.dumps(self.catalog), encoding='utf-8')
        records = [{'path': p.relative_to(self.root).as_posix(), 'size': p.stat().st_size,
                    'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(self.shared.iterdir())]
        (self.root/'effects.json').write_text(json.dumps({'schema': 'rocom.pet-effects.v1',
             'glassy_directory': 'effects/glassy', 'files': records}), encoding='utf-8')

    def resolve(self, selection, palette='normal'):
        return resolve_appearance(self.root, self.entity(palette), self.form, selection)

    def test_all_nine_types_keep_their_own_identity(self):
        variants = []
        for kind, (label, palette, effect) in TYPES.items():
            selection = {'color_type': label}
            if effect == 'regular':
                selection.update(color_id=101, particle_id=103)
            elif effect == 'seasonal':
                selection['preset_id'] = 71
            result = self.resolve(selection, palette)
            self.assertEqual(result['color_type'], kind)
            self.assertEqual(result['palette'], palette)
            variants.append(result['variant_key'])
        self.assertEqual(len(set(variants)), 9)

    def test_no_color_choice_requires_a_question(self):
        with self.assertRaises(ChoiceRequired) as ctx:
            self.resolve(None)
        self.assertEqual(ctx.exception.questions[0]['field'], 'color_type')
        self.assertEqual(len(ctx.exception.questions[0]['options']), 9)

    def test_only_the_missing_regular_detail_is_asked(self):
        with self.assertRaises(ChoiceRequired) as ctx:
            self.resolve({'color_type': '常规炫彩', 'color_id': 101})
        self.assertEqual([q['field'] for q in ctx.exception.questions], ['particle_id'])

    def test_new_seasons_are_discovered_from_changed_catalog(self):
        before = inspect_appearances(self.root, self.entity())
        for offset in range(5):
            new = dict(self.catalog['hidden'][1], id=907+offset, name='测试未来赛季'+str(offset), season_no=99+offset)
            self.catalog['hidden'].append(new)
        self.write_catalog()
        after = inspect_appearances(self.root, self.entity())
        self.assertEqual(len(after['seasons']), len(before['seasons'])+5)
        self.assertGreater(len(after['seasons']), 4)
        result = self.resolve({'color_type': '赛季限定炫彩', 'season_no': 99})
        self.assertEqual(result['mutation'], '炫彩:测试未来赛季0')
        self.assertNotEqual(before['catalog_sha256'], after['catalog_sha256'])

    def test_season_without_a_number_can_be_selected_by_id(self):
        del self.catalog['hidden'][1]['season_no']
        self.write_catalog()
        self.assertEqual(self.resolve({'color_type': '赛季限定炫彩', 'preset_id': 71})['selection']['preset_id'], 71)

    def test_season_conflicting_selectors_are_rejected(self):
        with self.assertRaises(InputError):
            self.resolve({'color_type': '赛季限定炫彩', 'preset_id': 71, 'preset_name': '不存在的名称'})

    def test_missing_season_is_not_replaced_by_existing_one(self):
        with self.assertRaises(InputError):
            self.resolve({'color_type': '赛季限定炫彩', 'season_no': 99})

    def test_black_white_does_not_assume_a_fixed_numeric_id(self):
        result = self.resolve({'color_type': '黑白炫彩'})
        self.assertEqual(result['selection']['preset_id'], 9999)
        self.assertEqual(result['mutation'], '炫彩:黑白')

    def test_shiny_source_is_not_switched_a_second_time(self):
        result = self.resolve({'color_type': '异色黑白炫彩'}, 'shiny')
        self.assertEqual(result['mutation'], '炫彩:黑白')
        self.assertNotIn('异色+', result['mutation'])

    def test_pollution_cannot_be_combined_with_shiny(self):
        for selection, palette in [
            ({'color_type': '异色+污染'}, 'shiny'),
            ({'color_type': '污染', 'palette': 'shiny'}, 'shiny'),
            ({'color_type': '异色', 'effect': 'pollution'}, 'shiny'),
            ({'color_type': '污染'}, 'shiny'),
        ]:
            with self.subTest(selection=selection), self.assertRaises(InputError):
                self.resolve(selection, palette)

    def test_pollution_uses_the_verified_native_entry(self):
        result = self.resolve({'color_type': '污染'})
        self.assertEqual(result['mutation'], '炫彩:污染')

    def test_wrong_base_palette_is_rejected(self):
        with self.assertRaises(InputError):
            self.resolve({'color_type': '异色'}, 'normal')

    def test_extra_effect_fields_are_not_silently_ignored(self):
        with self.assertRaises(InputError):
            self.resolve({'color_type': '常规', 'particle_id': 103})

    def test_hash_tampering_is_rejected(self):
        (self.shared/'shape.png').write_bytes(b'tampered')
        with self.assertRaises(InputError):
            self.resolve({'color_type': '常规炫彩', 'color_id': 101, 'particle_id': 103})

    def test_unindexed_selected_texture_is_rejected(self):
        entry = json.loads((self.root/'effects.json').read_text())
        entry['files'] = [r for r in entry['files'] if not r['path'].endswith('/shape.png')]
        (self.root/'effects.json').write_text(json.dumps(entry))
        with self.assertRaises(InputError):
            self.resolve({'color_type': '常规炫彩', 'color_id': 101, 'particle_id': 103})

    def test_directory_escape_is_rejected(self):
        entry = json.loads((self.root/'effects.json').read_text())
        entry['glassy_directory'] = '../outside/glassy'
        (self.root/'effects.json').write_text(json.dumps(entry))
        with self.assertRaises(InputError):
            validate_effect_resources(self.root)

    def test_duplicate_ids_are_rejected(self):
        self.catalog['hidden'].append(dict(self.catalog['hidden'][1]))
        self.write_catalog()
        with self.assertRaises(InputError):
            validate_effect_resources(self.root)

    def test_resolution_preserves_hdr_values_and_source_bytes(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.resolve({'color_type': '常规炫彩', 'color_name': '测试配色', 'particle_name': '测试纹样'})
        self.assertEqual({p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)
        self.assertEqual(json.loads((self.shared/'glassy.json').read_text())['colors'][0]['red_channel'][0], 1.6)


if __name__ == '__main__':
    unittest.main()
