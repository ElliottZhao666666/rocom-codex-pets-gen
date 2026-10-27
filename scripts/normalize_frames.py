"""Normalize source-rendered cells with one shared crop, scale and registration."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from PIL import Image
from validate_input import require


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frames-dir', required=True)
    p.add_argument('--plan', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--cell-width', type=int, default=192)
    p.add_argument('--cell-height', type=int, default=208)
    p.add_argument('--max-width', type=int, default=174)
    p.add_argument('--max-height', type=int, default=186)
    p.add_argument('--source-padding', type=int, default=18)
    a = p.parse_args()
    source = Path(a.frames_dir).resolve()
    output = Path(a.output).resolve()
    require(not output.is_relative_to(source), 'Output must be outside native input frames')
    require(a.cell_width > a.max_width > 0 and a.cell_height > a.max_height > 0, 'Invalid safe-area dimensions')
    require(0 <= a.source_padding <= 256, 'Invalid padding')
    plan = json.loads(Path(a.plan).read_text(encoding='utf-8'))
    entries = plan['frames']
    require(entries, 'No planned frames')
    images, bounds, destinations = [], [], []
    for index, entry in enumerate(entries):
        state, frame = entry['state'], entry['frame']
        require(isinstance(state, str) and re.fullmatch(r'[a-z0-9-]+', state), 'Invalid state name')
        require(type(frame) is int and 0 <= frame < 128, 'Invalid frame index')
        key = (state, frame)
        require(key not in destinations, 'Duplicate state/frame')
        destinations.append(key)
        path = source/f'{index:03}.png'
        with Image.open(path) as opened:
            require('A' in opened.mode, f'Native frame lacks alpha: {path.name}')
            image = opened.convert('RGBA')
        bbox = image.getchannel('A').point(lambda value: 255 if value > 16 else 0).getbbox()
        require(bbox is not None, f'Empty native frame: {path.name}')
        require(not images or image.size == images[0].size, 'Native frame sizes differ')
        images.append(image)
        bounds.append(bbox)
    padding = a.source_padding
    box = (min(b[0] for b in bounds)-padding, min(b[1] for b in bounds)-padding,
           max(b[2] for b in bounds)+padding, max(b[3] for b in bounds)+padding)
    scale = min(a.max_width/(box[2]-box[0]), a.max_height/(box[3]-box[1]))
    require(scale <= 1, 'Refusing to upscale insufficient native pixels')
    size = (round((box[2]-box[0])*scale), round((box[3]-box[1])*scale))
    offset = ((a.cell_width-size[0])//2, (a.cell_height-size[1])//2)
    row_images = {}
    for entry, image in zip(entries, images):
        small = image.crop(box).convert('RGBa').resize(size, Image.Resampling.LANCZOS).convert('RGBA')
        cell = Image.new('RGBA', (a.cell_width, a.cell_height))
        cell.alpha_composite(small, offset)
        target = output/'frames'/entry['state']/f"{entry['frame']:02}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        cell.save(target)
        row_images.setdefault(entry['state'], {})[entry['frame']] = cell
    decoded = output/'decoded'
    decoded.mkdir(exist_ok=True)
    for state, frames in row_images.items():
        require(set(frames) == set(range(len(frames))), f'Nonconsecutive frames: {state}')
        strip = Image.new('RGBA', (a.cell_width*len(frames), a.cell_height))
        for index in range(len(frames)):
            strip.alpha_composite(frames[index], (index*a.cell_width, 0))
        strip.save(decoded/f'{state}.png')
    report = {'native_frame_size': images[0].size, 'common_source_crop': box, 'scale': scale,
              'resized_viewport': size, 'offset': offset, 'filter': 'premultiplied RGBA LANCZOS',
              'per_pose_scale': False, 'per_pose_recenter': False, 'preserves_source_motion': True,
              'frames_written': len(images), 'note': 'Registration facts only; official Pets validation and visual review remain required.'}
    (output/'registration.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
