import json
import sys
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.config import DetectionConfig
from app.core.image_loader import load_image_with_exif, normalize_to_reference
from app.core.aligner import align_test_to_reference
from app.core.detector import inspect_component
from app.core.decision import classify_component

def main():
    sample_dir = ROOT / "sample_data"
    gt_file = sample_dir / "ground_truth.json"
    results_dir = ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    with open(gt_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    ref_img, _, _ = load_image_with_exif(sample_dir / "reference.png")
    components_meta = gt_data["components"]

    calib_images = [(k, v) for k, v in sorted(gt_data["images"].items()) if v.get("split") == "calibration"]

    # Pre-align all calibration boards
    aligned_boards = {}
    for img_key, meta in calib_images:
        raw_img, _, _ = load_image_with_exif(sample_dir / meta["relative_path"])
        ref_norm, test_norm, mask, _ = normalize_to_reference(ref_img, raw_img)
        aligned, _, _ = align_test_to_reference(ref_norm, test_norm, mask=mask)
        aligned_boards[img_key] = (aligned, set(meta["missing_parts"]))

    cfg = DetectionConfig(sensitivity="balanced")

    # Define jitter transformations on bboxes
    def get_jittered_bbox(bbox, mode):
        x, y, w, h = bbox
        if mode == "nominal":
            return [x, y, w, h]
        elif mode == "shifted_pos":
            return [x + 3, y + 3, w, h]
        elif mode == "shifted_neg":
            return [x - 3, y - 3, w, h]
        elif mode == "expanded_20":
            nw, nh = int(round(w * 1.20)), int(round(h * 1.20))
            nx = x - (nw - w) // 2
            ny = y - (nh - h) // 2
            return [max(0, nx), max(0, ny), nw, nh]
        elif mode == "shrunk_20":
            nw, nh = max(4, int(round(w * 0.80))), max(4, int(round(h * 0.80)))
            nx = x + (w - nw) // 2
            ny = y + (h - nh) // 2
            return [nx, ny, nw, nh]
        else:
            raise ValueError(f"Unknown mode {mode}")

    modes = [
        ("Nominal (baseline)", "nominal"),
        ("Shifted (+3px X, +3px Y)", "shifted_pos"),
        ("Shifted (-3px X, -3px Y)", "shifted_neg"),
        ("Expanded (+20% width/height)", "expanded_20"),
        ("Shrunk (-20% width/height)", "shrunk_20"),
    ]

    summary_rows = []
    detailed_tables = {}

    for label, m_key in modes:
        counts = {
            "missing_as_missing": 0,
            "missing_as_uncertain": 0,
            "missing_as_present": 0,
            "present_as_present": 0,
            "present_as_uncertain": 0,
            "present_as_missing": 0,
        }
        breakdown = []

        for img_key, meta in calib_images:
            aligned, missing_set = aligned_boards[img_key]
            for cid, cinfo in sorted(components_meta.items()):
                orig_bbox = cinfo["pixel_bbox"]
                j_bbox = get_jittered_bbox(orig_bbox, m_key)
                insp = inspect_component(ref_img, aligned, j_bbox)
                v = classify_component(cid, insp, cfg)
                status = v["status"]
                is_missing = cid in missing_set

                if is_missing:
                    if status == "MISSING":
                        counts["missing_as_missing"] += 1
                    elif status == "UNCERTAIN":
                        counts["missing_as_uncertain"] += 1
                        breakdown.append((Path(img_key).name, cid, "MISSING_AS_UNCERTAIN", insp["zncc_score"], insp["patch_diff"]))
                    elif status == "PRESENT":
                        counts["missing_as_present"] += 1
                        breakdown.append((Path(img_key).name, cid, "MISSING_AS_PRESENT (MISS)", insp["zncc_score"], insp["patch_diff"]))
                else:
                    if status == "PRESENT":
                        counts["present_as_present"] += 1
                    elif status == "UNCERTAIN":
                        counts["present_as_uncertain"] += 1
                        breakdown.append((Path(img_key).name, cid, "PRESENT_AS_UNCERTAIN", insp["zncc_score"], insp["patch_diff"]))
                    elif status == "MISSING":
                        counts["present_as_missing"] += 1
                        breakdown.append((Path(img_key).name, cid, "PRESENT_AS_MISSING (FA)", insp["zncc_score"], insp["patch_diff"]))

        summary_rows.append((label, counts))
        detailed_tables[label] = breakdown

    # Print markdown table
    out_lines = []
    out_lines.append("=" * 95)
    out_lines.append("  JITTER ROBUSTNESS CONFUSION MATRIX ACROSS ALL 20 CALIBRATION BOARDS")
    out_lines.append(f"  Active Thresholds: ZNCC [{cfg.zncc_low_thresh}, {cfg.zncc_high_thresh}] | Diff [{cfg.patch_diff_low_thresh}, {cfg.patch_diff_high_thresh}]")
    out_lines.append(f"  Evaluated Instances: 20 Missing components, 260 Present components (280 total per mode)")
    out_lines.append("=" * 95)
    out_lines.append("")
    out_lines.append("| Bbox Perturbation Mode        | MISSING Components (N=20)          | PRESENT Components (N=260)        |")
    out_lines.append("|                               | MISSING (TP) | UNCERTAIN | PRESENT | PRESENT (TN) | UNCERTAIN | MISSING (FA) |")
    out_lines.append("|:------------------------------|:------------:|:---------:|:-------:|:------------:|:---------:|:------------:|")

    for label, counts in summary_rows:
        m_miss = counts["missing_as_missing"]
        m_unc = counts["missing_as_uncertain"]
        m_pres = counts["missing_as_present"]
        p_pres = counts["present_as_present"]
        p_unc = counts["present_as_uncertain"]
        p_miss = counts["present_as_missing"]
        out_lines.append(f"| {label:30s} | {m_miss:12d} | {m_unc:9d} | {m_pres:7d} | {p_pres:12d} | {p_unc:9d} | {p_miss:12d} |")

    out_lines.append("")
    out_lines.append("=" * 95)
    out_lines.append("DETAILED BREAKDOWN OF NON-NOMINAL VERDICTS PER MODE:")
    out_lines.append("=" * 95)
    for label, issues in detailed_tables.items():
        out_lines.append(f"\n--- Mode: {label} (Total Anomaly Instances: {len(issues)}) ---")
        if not issues:
            out_lines.append("  [Clean: 100% nominal verdicts (20/20 Missing, 260/260 Present)]")
        else:
            for img, cid, tag, z, d in issues:
                out_lines.append(f"  {img:34s} | {cid:12s} | Verdict: {tag:28s} | ZNCC: {z:.4f} | Diff: {d:.4f}")

    out_text = "\n".join(out_lines)
    print(out_text)

    with open(results_dir / "jitter_confusion_matrix.txt", "w", encoding="utf-8") as f:
        f.write(out_text + "\n")

if __name__ == "__main__":
    main()
