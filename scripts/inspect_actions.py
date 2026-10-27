"""Enumerate every animation candidate without automatically picking suffix 1."""
import argparse
import json
import re
from pathlib import Path
from validate_input import validate_input, require


def action_family(name):
    # Group suffix variants, but preserve loop/start/end subtypes.
    value = re.sub(r'(?:[_\- ]?(?:v|ver)?\d+)$', '', name, flags=re.I)
    return value or name


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--json-out', required=True)
    a = p.parse_args()
    result, entity, manifest = validate_input(a.input)
    groups = {}
    form = manifest['forms'][0]
    for name, meta in form['clips'].items():
        groups.setdefault(action_family(name), []).append({'logical_name': name, 'animation_name': meta['clip'], 'milliseconds': meta['ms'], 'face_channels': list(form.get('face', {}).get(name, {}))})
    output = Path(a.json_out).resolve()
    require(not output.is_relative_to(Path(a.input).resolve()), 'Output must be outside input')
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {'identity': entity['identity'], 'selection': 'pending visual comparison; no candidate automatically selected', 'families': groups}
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Enumerated {sum(map(len, groups.values()))} animations in {len(groups)} candidate families')


if __name__ == '__main__':
    main()
