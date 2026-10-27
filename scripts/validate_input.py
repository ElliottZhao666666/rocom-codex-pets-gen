"""Read-only validation for the documented single-entity directory contract."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import struct
import sys
import tomllib
from pathlib import Path, PurePosixPath


class InputError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InputError(message)


def resource(root: Path, value: str) -> Path:
    require(isinstance(value, str) and value, 'Resource path must be a nonempty string')
    require('\\' not in value and ':' not in value and not value.startswith('/'), f'Unsafe resource path: {value}')
    rel = PurePosixPath(value)
    require('..' not in rel.parts and '.' not in rel.parts, f'Unsafe resource path: {value}')
    path = root.joinpath(*rel.parts)
    require(path.resolve().is_relative_to(root.resolve()), f'Resource escapes input directory: {value}')
    require(path.is_file(), f'Missing resource: {value}')
    return path


def read_glb(path):
    data = path.read_bytes()
    require(len(data) >= 20, f'Truncated GLB: {path.name}')
    magic, version, length = struct.unpack_from('<4sII', data)
    require(magic == b'glTF' and version == 2 and length == len(data), f'Invalid glTF 2.0 GLB: {path.name}')
    pos, doc, binary = 12, None, b''
    while pos < length:
        require(pos + 8 <= length, 'Truncated GLB chunk header')
        size, kind = struct.unpack_from('<II', data, pos)
        pos += 8
        require(pos + size <= length, 'Truncated GLB chunk')
        chunk = data[pos:pos+size]
        if kind == 0x4E4F534A:
            doc = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = chunk
        pos += size
    require(isinstance(doc, dict), 'GLB JSON chunk is missing')
    return doc, binary


def json_file(path):
    return json.loads(path.read_text(encoding='utf-8'))


def validate_input(directory, verify_hashes=True):
    root = Path(directory).expanduser().resolve()
    require(root.is_dir(), 'Input must be one existing standard directory')
    for path in root.rglob('*'):
        require(path.resolve().is_relative_to(root), f'Linked path escapes input directory: {path.name}')
    required = ['entity.json', 'model.glb', 'manifest.toml'] + [f'metadata/{n}.json' for n in ['materials', 'face_curves', 'morph_targets', 'animations', 'source-files']]
    for name in required:
        resource(root, name)
    require(len(list(root.rglob('entity.json'))) == 1, 'Nested or multiple entity.json files are not allowed')
    entity = json_file(root/'entity.json')
    require(entity.get('schema') == 'rkpet2.entity.v1', 'Unsupported entity schema')
    ident, asset, palette = entity.get('entity_id'), entity.get('asset'), entity.get('appearance')
    require(type(ident) is int and ident > 0, 'entity_id must be a positive integer')
    require(isinstance(entity.get('name'), str) and entity['name'].strip(), 'name is required')
    require(type(entity.get('stage')) is int, 'stage must be an integer')
    require(isinstance(asset, str) and re.fullmatch(r'[A-Za-z0-9_\-]+', asset), 'Invalid asset identifier')
    require(palette in ('normal', 'shiny'), 'appearance must be normal or shiny')
    require(entity.get('identity') == {'entity_id': ident, 'form_asset': asset, 'palette': palette}, 'identity does not match entity/form/palette')
    require(entity.get('model') == 'model.glb' and entity.get('runtime_manifest') == 'manifest.toml', 'Invalid standard entry paths')
    require(entity.get('animation_cache') == f'forms/{asset}/anim.rka', 'animation_cache must belong to the one selected form')
    resource(root, entity['animation_cache'])
    manifest = tomllib.loads((root/'manifest.toml').read_text(encoding='utf-8'))
    require(manifest.get('schema') == 1 and manifest.get('runtime_abi') == 22, 'Unsupported manifest schema/runtime ABI')
    species = manifest.get('species', {})
    require(species.get('id') == ident and species.get('chain') == [ident], 'species must contain only the selected entity')
    require(isinstance(manifest.get('forms'), list) and len(manifest['forms']) == 1, 'Exactly one form is required')
    form = manifest['forms'][0]
    require(form.get('id') == ident and form.get('asset') == asset, 'Manifest identity does not match entity.json')
    require(form.get('stage') == entity['stage'], 'Manifest stage does not match entity.json')
    require(form.get('model') == f'forms/{asset}/model.glb', 'Raw model must belong to selected form')
    require(not form.get('shiny_materials'), 'Alternate palette materials are not allowed')
    form_dirs = [p.name for p in (root/'forms').iterdir() if p.is_dir()]
    require(form_dirs == [asset], 'Exactly one forms/<asset> directory is allowed')
    raw, _ = read_glb(resource(root, form['model']))
    animated, _ = read_glb(root/'model.glb')
    names = [a.get('name') for a in animated.get('animations', [])]
    require(names and len(names) == len(set(names)) and all(names), 'GLB animations must have unique nonempty names')
    clips = form.get('clips', {})
    require(clips and set(names) == {c['clip'] for c in clips.values()}, 'Manifest and GLB animation names differ')
    require(entity.get('animation_count') == len(names), 'animation_count does not match GLB')
    summaries = json_file(root/'metadata/animations.json')
    require(isinstance(summaries, list) and {a.get('name') for a in summaries} == set(names), 'animations.json does not match GLB')
    for filename, field in [('materials', 'materials'), ('face_curves', 'face'), ('morph_targets', 'morph')]:
        require(json_file(root/f'metadata/{filename}.json') == form.get(field, {}), f'{filename}.json does not match manifest')
    for name, clip in clips.items():
        require(isinstance(clip.get('ms'), (int, float)) and clip['ms'] > 0, f'Invalid clip duration: {name}')
    for clip, channels in form.get('face', {}).items():
        require(clip in clips, f'Unknown face animation: {clip}')
        for channel, points in channels.items():
            require(isinstance(points, list) and points, f'Empty face curve: {clip}/{channel}')
            previous = -1
            for point in points:
                require(isinstance(point, list) and len(point) == 2, 'Face point must be [milliseconds, index]')
                time, value = point
                require(isinstance(time, (int, float)) and time >= 0 and time > previous, 'Face times must increase')
                require(type(value) is int and 1 <= value <= 8, 'Face atlas index must be 1..8')
                previous = time
    # All known resource fields are resolved from this directory, never from the current working directory.
    def scan(value):
        if isinstance(value, dict):
            for v in value.values():
                scan(v)
        elif isinstance(value, list):
            for v in value:
                scan(v)
        elif isinstance(value, str) and re.search(r'\.(png|webp|glb|rka|wav|wem|dds)$', value, re.I):
            resource(root, value)
    scan(form)
    for model in (raw, animated):
        for collection in ('images', 'buffers'):
            for obj in model.get(collection, []):
                if 'uri' in obj:
                    resource(root, obj['uri'])
    for audio in entity.get('audio', []):
        resource(root, audio['path'])
    records = json_file(root/'metadata/source-files.json')
    require(isinstance(records, list) and records, 'source-files.json must be a nonempty list')
    seen = set()
    for record in records:
        path = resource(root, record['path'])
        require(record['path'] not in seen, 'Duplicate source-file record')
        seen.add(record['path'])
        require(path.stat().st_size == record['size'], f'File size mismatch: {record["path"]}')
        require(re.fullmatch(r'[0-9a-fA-F]{64}', record['sha256']), 'Invalid SHA-256 value')
        if verify_hashes:
            require(hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256'].lower(), f'SHA-256 mismatch: {record["path"]}')
    # This optional extension contains shared effect data, not another entity or palette.
    if (root/'effects.json').exists():
        from color_appearance import validate_effect_resources
        validate_effect_resources(root)
    result = {'ok': True, 'input': str(root), 'identity': entity['identity'], 'name': entity['name'], 'animation_count': len(names), 'verified_source_files': len(records), 'hashes_checked': verify_hashes}
    return result, entity, manifest


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--json-out')
    args = parser.parse_args()
    try:
        result, _, _ = validate_input(args.input)
    except (OSError, ValueError, KeyError, TypeError, struct.error) as exc:
        result = {'ok': False, 'input': str(args.input), 'errors': [str(exc)]}
    if args.json_out:
        output = Path(args.json_out).resolve()
        require(not output.is_relative_to(Path(args.input).resolve()), 'Output must be outside input')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
