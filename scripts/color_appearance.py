"""Resolve explicit color choices against one input's own effect catalog."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

from validate_input import InputError, require, resource


TYPES = {
    'normal': ('常规', 'normal', 'none'),
    'normal_glassy': ('常规炫彩', 'normal', 'regular'),
    'normal_black_white': ('黑白炫彩', 'normal', 'black_white'),
    'normal_seasonal': ('赛季限定炫彩', 'normal', 'seasonal'),
    'pollution': ('污染', 'normal', 'pollution'),
    'shiny': ('异色', 'shiny', 'none'),
    'shiny_glassy': ('异色炫彩', 'shiny', 'regular'),
    'shiny_seasonal': ('异色赛季炫彩', 'shiny', 'seasonal'),
    'shiny_black_white': ('异色黑白炫彩', 'shiny', 'black_white'),
}
ALIASES = {label: key for key, (label, _, _) in TYPES.items()}
ALIASES.update({'普通': 'normal', '常规异色炫彩': 'shiny_glassy', '异色常规炫彩': 'shiny_glassy',
                '赛季炫彩': 'normal_seasonal', '异色赛季限定炫彩': 'shiny_seasonal'})
DEFAULT_MAIN = 'Tex_PetGlassy_007_D'
POLLUTION_TEXTURES = ('T_EMeng002', 'T_EMeng003')


class ChoiceRequired(InputError):
    def __init__(self, questions):
        self.questions = questions
        super().__init__('User color choice is incomplete; ask only the listed questions')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def validate_effect_resources(directory):
    """Optional extension of entity.v1; never searches outside the entity root."""
    root = Path(directory).resolve()
    if not (root/'effects.json').exists():
        return None
    definition = read_json(resource(root, 'effects.json'))
    require(definition.get('schema') == 'rocom.pet-effects.v1', 'Unsupported effects schema')
    relative = definition.get('glassy_directory')
    require(isinstance(relative, str) and relative, 'glassy_directory is required')
    catalog_path = resource(root, relative.rstrip('/')+'/glassy.json')
    directory = catalog_path.parent
    require(directory.name == 'glassy', 'Renderer requires a directory named glassy')
    records = definition.get('files')
    require(isinstance(records, list) and records, 'effects.files must contain file sizes and SHA-256 hashes')
    indexed = {}
    for record in records:
        require(isinstance(record, dict), 'Effect hash record must be an object')
        path = resource(root, record.get('path'))
        require(path.resolve().is_relative_to(directory.resolve()), 'Effect file must stay in glassy_directory')
        require(record['path'] not in indexed, 'Duplicate effect hash record')
        digest = record.get('sha256')
        require(type(record.get('size')) is int and record['size'] >= 0, 'Invalid effect file size')
        require(isinstance(digest, str) and re.fullmatch(r'[a-fA-F0-9]{64}', digest), 'Invalid effect SHA-256')
        require(path.stat().st_size == record['size'], 'Effect size mismatch: '+record['path'])
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest.lower(), 'Effect SHA-256 mismatch: '+record['path'])
        indexed[record['path']] = {'path': record['path'], 'size': record['size'], 'sha256': digest.lower()}
    catalog_relative = catalog_path.relative_to(root).as_posix()
    require(catalog_relative in indexed, 'glassy.json must be covered by effects.files')
    catalog = read_json(catalog_path)
    require(isinstance(catalog, dict), 'Effect catalog must be an object')
    for field in ('colors', 'particles', 'hidden'):
        rows = catalog.get(field, [])
        require(isinstance(rows, list), 'Catalog '+field+' must be a list')
        seen = set()
        for row in rows:
            require(isinstance(row, dict), 'Catalog row must be an object')
            require(type(row.get('id')) is int and row['id'] > 0, 'Catalog IDs must be positive integers')
            require(row['id'] not in seen, 'Duplicate catalog ID in '+field)
            require(isinstance(row.get('name'), str) and row['name'].strip(), 'Catalog name is required')
            seen.add(row['id'])
            if field == 'hidden':
                require(type(row.get('season', False)) is bool, 'hidden.season must be a boolean')
                if 'season_no' in row:
                    require(type(row['season_no']) is int and row['season_no'] >= 0, 'Invalid season number')
            if field in ('colors', 'hidden'):
                for channel in ('red_channel', 'green_channel'):
                    value = row.get(channel)
                    require(isinstance(value, list) and len(value) in (3, 4) and all(finite(v) for v in value), 'Invalid '+channel)
    return {'root': root, 'directory': directory, 'catalog_path': catalog_path,
            'catalog': catalog, 'index': indexed}


def texture_path(effects, name):
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_\-]+(?:\.png)?', name), 'Invalid catalog texture name')
    file_name = name if name.endswith('.png') else name+'.png'
    return (effects['directory']/file_name).relative_to(effects['root']).as_posix()


def texture_set(effects, effect, preset=None):
    if effect == 'regular':
        names = [DEFAULT_MAIN, preset['tex']]
    elif effect in ('seasonal', 'black_white'):
        names = [preset['main_tex'], preset['star_tex']]
    else:
        names = list(POLLUTION_TEXTURES)
    paths = [texture_path(effects, name) for name in names]
    missing = []
    for path in paths:
        if path not in effects['index'] or not (effects['root']/path).is_file():
            missing.append(path)
    return paths, missing


def inspect_appearances(directory, entity=None, effects=None):
    root = Path(directory).resolve()
    entity = entity or read_json(resource(root, 'entity.json'))
    effects = effects if effects is not None else validate_effect_resources(root)
    result = {'identity': entity['identity'], 'color_types': [
        {'id': key, 'name': label, 'base_palette': palette, 'effect': effect,
         'input_palette_matches': palette == entity['appearance']}
        for key, (label, palette, effect) in TYPES.items()],
        'colors': [], 'particles': [], 'seasons': [], 'black_white': [],
        'pollution': {'available': False}, 'effects_present': effects is not None}
    if effects is None:
        result['resource_note'] = 'No effects.json; effect choices require this input extension. No external catalog was searched.'
        return result
    catalog = effects['catalog']
    result['catalog_sha256'] = hashlib.sha256(effects['catalog_path'].read_bytes()).hexdigest()
    result['colors'] = [{'id': r['id'], 'name': r['name']} for r in catalog.get('colors', [])]
    for row in catalog.get('particles', []):
        _, missing = texture_set(effects, 'regular', row)
        result['particles'].append({'id': row['id'], 'name': row['name'], 'available': not missing, 'missing_resources': missing})
    # Discover the current seasons from data; neither season IDs nor their count are fixed.
    for row in catalog.get('hidden', []):
        if row.get('season') is True:
            field, effect = 'seasons', 'seasonal'
        elif row['name'] == '黑白':
            field, effect = 'black_white', 'black_white'
        else:
            continue
        _, missing = texture_set(effects, effect, row)
        result[field].append({'id': row['id'], 'name': row['name'], 'season_no': row.get('season_no'),
                              'available': not missing, 'missing_resources': missing,
                              'associated_special_forms': row.get('season_pets', [])})
    if isinstance(catalog.get('pollution'), dict):
        _, missing = texture_set(effects, 'pollution')
        result['pollution'] = {'available': not missing, 'missing_resources': missing}
    return result


def choose_row(rows, choice, id_key, name_key, question, extra_key=None):
    selectors = [(id_key, 'id'), (name_key, 'name')]
    if extra_key:
        selectors.append((extra_key, extra_key))
    supplied = [(field, key) for field, key in selectors if field in choice]
    if not supplied:
        raise ChoiceRequired([{'field': id_key, 'title': question,
                               'options': [{'id': row['id'], 'name': row['name'], **({'season_no': row.get('season_no')} if extra_key else {})} for row in rows]}])
    for field, key in supplied:
        if key in ('id', 'season_no'):
            require(type(choice[field]) is int and choice[field] > 0, field+' must be a positive integer')
        else:
            require(isinstance(choice[field], str) and choice[field].strip(), field+' must be a nonempty name')
    matches = [row for row in rows if all(row.get(key) == choice[field] for field, key in supplied)]
    require(len(matches) == 1, 'Selection is absent, ambiguous or conflicting in the current catalog: '+question)
    return matches[0]


def resolve_appearance(directory, entity, form, choice):
    root = Path(directory).resolve()
    require(choice is None or isinstance(choice, dict), 'appearance selection must be an object')
    choice = choice or {}
    if choice.get('palette') == 'shiny' and (choice.get('effect') == 'pollution' or choice.get('color_type') in ('污染', 'pollution')):
        raise InputError('异色与污染不能叠加')
    requested = choice.get('color_type')
    if requested is None:
        raise ChoiceRequired([{'field': 'color_type', 'title': '请选择颜色类型；形态与颜色分别确定。',
                               'options': [{'id': k, 'name': v[0]} for k, v in TYPES.items()]}])
    require(isinstance(requested, str), 'color_type must be a string')
    if '异色' in requested and '污染' in requested:
        raise InputError('异色与污染不能叠加')
    key = ALIASES.get(requested, requested)
    require(key in TYPES, 'Unknown color_type; do not infer a color from 正常 or a model-form name')
    label, palette, effect = TYPES[key]
    if palette == 'shiny' and choice.get('effect') == 'pollution':
        raise InputError('异色与污染不能叠加')
    require('effect' not in choice or choice['effect'] == effect, 'Conflicting effect and color_type')
    require('palette' not in choice or choice['palette'] == palette, 'Conflicting palette and color_type')
    require(palette == entity['appearance'], '所选颜色需要 '+palette+' 标准目录；当前输入为 '+entity['appearance']+'，不能改猜或混用另一配色')
    allowed = {'color_type', 'palette', 'effect'}
    if effect == 'regular':
        allowed.update(('color_id', 'color_name', 'particle_id', 'particle_name'))
    elif effect in ('seasonal', 'black_white'):
        allowed.update(('preset_id', 'preset_name'))
        if effect == 'seasonal':
            allowed.add('season_no')
    require(not set(choice)-allowed, 'Unused or incompatible appearance fields: '+', '.join(sorted(set(choice)-allowed)))
    base = {'schema': 'rocom.pet-appearance.v1', 'color_type': key, 'label': label, 'palette': palette,
            'effect': effect, 'identity': entity['identity'], 'selection': {}, 'mutation': None,
            'packs_directory': None, 'resources': [], 'catalog_sha256': None}
    suffix = 'none'
    if effect != 'none':
        effects = validate_effect_resources(root)
        require(effects is not None, '所选颜色需要输入目录内的 effects.json 和共享资源')
        catalog = effects['catalog']
        require(any('glassy_id_tex' in mat or any(k.startswith('pollution_') or k.startswith('season_') for k in mat)
                    for mat in form.get('materials', {}).values()), '输入缺少原始炫彩区域/材质参数；不能对图片猜画')
        if effect == 'regular':
            questions = []
            for ik, nk, field, title in [('color_id', 'color_name', 'colors', '请选择当前资源中的配色'), ('particle_id', 'particle_name', 'particles', '请选择当前资源中的粒子/纹样')]:
                if ik not in choice and nk not in choice:
                    questions.append({'field': ik, 'title': title, 'options': [{'id': r['id'], 'name': r['name']} for r in catalog.get(field, [])]})
            if questions:
                raise ChoiceRequired(questions)
            color = choose_row(catalog.get('colors', []), choice, 'color_id', 'color_name', '常规配色')
            particle = choose_row(catalog.get('particles', []), choice, 'particle_id', 'particle_name', '粒子/纹样')
            paths, missing = texture_set(effects, effect, particle)
            base['selection'] = {'color_id': color['id'], 'color_name': color['name'], 'particle_id': particle['id'], 'particle_name': particle['name']}
            base['mutation'] = f"炫彩:{particle['id']}/{color['id']}"
            suffix = f"glassy-p{particle['id']}-c{color['id']}"
        elif effect in ('seasonal', 'black_white'):
            rows = [r for r in catalog.get('hidden', []) if r.get('season') is True] if effect == 'seasonal' else [r for r in catalog.get('hidden', []) if not r.get('season') and r['name'] == '黑白']
            require(rows, '当前资源清单没有所选类型；不使用历史赛季列表替代')
            if effect == 'black_white' and not any(k in choice for k in ('preset_id', 'preset_name')):
                require(len(rows) == 1, 'Multiple black/white entries require explicit selection')
                preset = rows[0]
            else:
                preset = choose_row(rows, choice, 'preset_id', 'preset_name', '请选择当前资源中的赛季' if effect == 'seasonal' else '黑白预设', 'season_no' if effect == 'seasonal' else None)
            require(sum(r['name'] == preset['name'] for r in catalog.get('hidden', [])) == 1, 'Renderer preset name is ambiguous in catalog')
            require(not any(c in preset['name'] for c in ('+', '\n', '\r', '\0')), 'Unsafe preset name')
            paths, missing = texture_set(effects, effect, preset)
            base['selection'] = {'preset_id': preset['id'], 'preset_name': preset['name'], 'season_no': preset.get('season_no')}
            base['mutation'] = '炫彩:'+preset['name']
            suffix = f"{effect}-id{preset['id']}"
        else:
            require(isinstance(catalog.get('pollution'), dict), 'Current catalog has no pollution definition')
            paths, missing = texture_set(effects, effect)
            base['mutation'] = '炫彩:污染'
            suffix = 'pollution'
        require(not missing, '所选外观缺少已校验资源: '+', '.join(missing))
        catalog_relative = effects['catalog_path'].relative_to(root).as_posix()
        base['resources'] = [effects['index'][p] for p in dict.fromkeys([catalog_relative, *paths])]
        base['catalog_sha256'] = hashlib.sha256(effects['catalog_path'].read_bytes()).hexdigest()
        base['packs_directory'] = str(effects['directory'].parent)
    base['variant_key'] = f"{entity['entity_id']}-{entity['asset']}-{palette}-{suffix}"
    return base


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    from validate_input import validate_input
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--selection', help='JSON containing the already resolved user choice; omitted = list choices')
    parser.add_argument('--json-out')
    args = parser.parse_args()
    code = 0
    try:
        _, entity, manifest = validate_input(args.input)
        result = {'ok': True, 'status': 'resolved' if args.selection else 'options',
                  'appearance': resolve_appearance(args.input, entity, manifest['forms'][0], read_json(Path(args.selection))) if args.selection else inspect_appearances(args.input, entity)}
    except ChoiceRequired as exc:
        result = {'ok': False, 'status': 'needs_input', 'questions': exc.questions}; code = 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'ok': False, 'status': 'error', 'errors': [str(exc)]}; code = 1
    if args.json_out:
        target = Path(args.json_out).resolve()
        require(not target.is_relative_to(Path(args.input).resolve()), 'Output must be outside input')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(code)


if __name__ == '__main__':
    main()
