import json

with open('sample_data/ground_truth.json') as f:
    gt = json.load(f)

for k, v in sorted(gt['images'].items()):
    if 'calib' in k:
        rel = v.get('relative_path')
        miss = v.get('missing_parts')
        light = v.get('lighting')
        shift = v.get('camera_shift')
        glare = v.get('has_glare')
        print(f"{k:45s} | miss={len(miss)} {miss} | light={light} | shift={shift} | glare={glare}")
