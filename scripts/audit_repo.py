"""Fail if private asset/run file types are found in this skill source tree."""
import json
import hashlib
from pathlib import Path

DOCUMENTATION_PREVIEWS = {
    'docs/images/codex-pets-preview.png': '98e7fdc75a7b4bed9253c917b3ece7375146d11775d7cf1312091afebcd80e2a',
    'docs/images/juhuali-colors.png': '9e13189e0e9989ba9bfa8f66f83d85afeea7f558ca6c2fd4d1a1721fe060fd63',
}


def main():
    root = Path(__file__).resolve().parents[1]
    forbidden = {'.glb', '.rka', '.wem', '.wav', '.png', '.webp', '.gif', '.mp4', '.exe', '.dll', '.rkpet2', '.zip'}
    names = {'entity.json', 'manifest.toml', 'installation.json', 'upload-session.json', '.env',
             'effects.json', 'glassy.json', 'render-provenance.json', 'appearance-selection.json', 'source-files.json'}
    private_paths = []
    approved_previews = []
    for path in root.rglob('*'):
        if not path.is_file() or '.git' in path.relative_to(root).parts or '__pycache__' in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        if relative in DOCUMENTATION_PREVIEWS:
            if hashlib.sha256(path.read_bytes()).hexdigest() == DOCUMENTATION_PREVIEWS[relative]:
                approved_previews.append(relative)
            else:
                private_paths.append(relative+' (unapproved image bytes)')
            continue
        if path.suffix.lower() in forbidden or path.name in names or path.name.startswith('.env.'):
            private_paths.append(path.relative_to(root).as_posix())
    missing = sorted(set(DOCUMENTATION_PREVIEWS)-set(approved_previews))
    report = {'ok': not private_paths and not missing, 'private_files_found': private_paths,
              'approved_documentation_previews': approved_previews, 'missing_or_changed_previews': missing,
              'scope': 'source-tree file types/names plus exact approved preview hashes; review tracked text before publishing'}
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
