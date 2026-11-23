import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.config import DetectionConfig
from app.core.image_loader import load_image_with_exif, normalize_to_reference
from app.core.aligner import align_test_to_reference
from app.core.detector import inspect_component
from app.core.decision import classify_component, aggregate_board_status

def main():
    with open('sample_data/ground_truth.json', 'r', encoding='utf-8') as f:
        gt = json.load(f)

    ref_img, _, _ = load_image_with_exif('sample_data/reference.png')
    cfg = DetectionConfig()

    anomalies = []
    board_summaries = []

    for img_key, meta in sorted(gt['images'].items()):
        if meta.get('split') != 'test_heldout':
            continue
        raw_img, _, _ = load_image_with_exif(Path('sample_data') / meta['relative_path'])
        ref_norm, test_norm, mask, _ = normalize_to_reference(ref_img, raw_img)
        aligned, _, align_meta = align_test_to_reference(ref_norm, test_norm, mask=mask)
        missing_set = set(meta['missing_parts'])

        parts = []
        for cid, cinfo in sorted(gt['components'].items()):
            insp = inspect_component(ref_img, aligned, cinfo['pixel_bbox'])
            v = classify_component(cid, insp, cfg)
            parts.append(v)
            is_missing = cid in missing_set

            if is_missing and v['status'] == 'PRESENT':
                anomalies.append({
                    'type': 'MISS (False Negative)',
                    'image': Path(img_key).name,
                    'part': cid,
                    'zncc': insp['zncc_score'],
                    'diff': insp['patch_diff'],
                    'reason': v['reason']
                })
            elif not is_missing and v['status'] == 'MISSING':
                anomalies.append({
                    'type': 'FALSE ALARM (False Positive)',
                    'image': Path(img_key).name,
                    'part': cid,
                    'zncc': insp['zncc_score'],
                    'diff': insp['patch_diff'],
                    'reason': v['reason']
                })
            elif v['status'] == 'UNCERTAIN':
                anomalies.append({
                    'type': 'UNCERTAIN (Manual Review)',
                    'image': Path(img_key).name,
                    'part': cid,
                    'ground_truth': 'MISSING' if is_missing else 'PRESENT',
                    'zncc': insp['zncc_score'],
                    'diff': insp['patch_diff'],
                    'reason': v['reason']
                })

        b_dec = aggregate_board_status(parts)
        board_summaries.append((Path(img_key).name, meta['expected_board_status'], b_dec['board_status'], b_dec['missing_components'], b_dec['uncertain_components']))

    print("=" * 80)
    print("DETAILED HELDOUT EVALUATION ANOMALY BREAKDOWN")
    print("=" * 80)
    for a in anomalies:
        gt_info = f" [GT: {a['ground_truth']}]" if 'ground_truth' in a else ""
        print(f"{a['type']:30s}{gt_info} | {a['image']:36s} | {a['part']:12s} | ZNCC: {a['zncc']:.4f} | Diff: {a['diff']:.4f}")

    # Append this to results/heldout_once.txt
    with open('results/heldout_once.txt', 'a', encoding='utf-8') as f:
        f.write("\n" + "=" * 82 + "\n")
        f.write("  DETAILED PER-PART OUTCOME ANOMALIES ON HELD-OUT TEST SET\n")
        f.write("=" * 82 + "\n")
        for a in anomalies:
            gt_info = f" [GT: {a['ground_truth']}]" if 'ground_truth' in a else ""
            f.write(f"{a['type']:30s}{gt_info} | {a['image']:36s} | {a['part']:12s} | ZNCC: {a['zncc']:.4f} | Diff: {a['diff']:.4f}\n")

if __name__ == "__main__":
    main()
