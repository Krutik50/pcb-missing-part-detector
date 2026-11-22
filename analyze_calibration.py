"""
Diagnostic Analysis Script for Calibration Set:
1. Identifies the 10 lowest-scoring PRESENT parts and 10 highest-scoring MISSING parts.
2. Measures plain substrate vs component body area ratio for each bounding box.
3. Performs 2-fold cross-validation on the calibration set (Fold 1: images 1-10, Fold 2: images 11-20).
4. Saves detailed diagnostic evidence to the results/ folder.
"""

import json
import sys
from pathlib import Path
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import DetectionConfig, DEFAULT_CONFIG
from app.core.image_loader import load_image_with_exif, normalize_to_reference
from app.core.aligner import align_test_to_reference
from app.core.detector import inspect_component
from app.core.decision import classify_component, aggregate_board_status


def analyze():
    sample_dir = Path("sample_data")
    gt_file = sample_dir / "ground_truth.json"
    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)

    with open(gt_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    ref_img, _, _ = load_image_with_exif(sample_dir / "reference.png")
    components_meta = gt_data["components"]

    # -------------------------------------------------------------
    # 1. Bounding Box Fill Ratio Analysis (Substrate vs Component)
    # -------------------------------------------------------------
    box_analysis = []
    # Base green solder mask has Hue ~ 65-85, Saturation > 50 in HSV
    ref_hsv = cv2.cvtColor(ref_img, cv2.COLOR_BGR2HSV)
    lower_green = np.array([35, 40, 20])
    upper_green = np.array([85, 255, 120])
    substrate_mask = cv2.inRange(ref_hsv, lower_green, upper_green)

    for cid, cinfo in components_meta.items():
        x, y, w, h = cinfo["pixel_bbox"]
        total_pixels = w * h
        sub_crop = substrate_mask[y:y + h, x:x + w]
        substrate_pixels = int(np.count_nonzero(sub_crop))
        component_pixels = total_pixels - substrate_pixels
        substrate_pct = (substrate_pixels / total_pixels) * 100.0
        comp_pct = (component_pixels / total_pixels) * 100.0

        box_analysis.append({
            "name": cid,
            "type": cinfo["type"],
            "bbox": [x, y, w, h],
            "total_px": total_pixels,
            "substrate_pct": substrate_pct,
            "component_pct": comp_pct,
        })

    # -------------------------------------------------------------
    # 2. Inspect All 20 Calibration Images
    # -------------------------------------------------------------
    calib_images = []
    for k, v in gt_data["images"].items():
        if v.get("split") == "calibration":
            calib_images.append((k, v))

    all_present_instances = []
    all_missing_instances = []
    per_image_results = {}

    for img_key, meta in calib_images:
        img_path = sample_dir / meta["relative_path"]
        test_raw, _, _ = load_image_with_exif(img_path)
        ref_norm, test_norm, mask, _ = normalize_to_reference(ref_img, test_raw)
        aligned, _, align_info = align_test_to_reference(ref_norm, test_norm, mask=mask)

        expected_missing = set(meta["missing_parts"])
        per_image_results[img_key] = []

        for cid, cinfo in components_meta.items():
            bbox = cinfo["pixel_bbox"]
            insp = inspect_component(ref_norm, aligned, bbox)
            is_truly_missing = cid in expected_missing

            record = {
                "image": Path(img_key).name,
                "part": cid,
                "type": cinfo["type"],
                "zncc": insp["zncc_score"],
                "diff": insp["patch_diff"],
                "shift": insp["shift_px"],
                "is_missing": is_truly_missing,
            }

            per_image_results[img_key].append(record)
            if is_truly_missing:
                all_missing_instances.append(record)
            else:
                all_present_instances.append(record)

    # Sort to find extremes
    # Lowest ZNCC among PRESENT parts
    present_sorted_by_zncc = sorted(all_present_instances, key=lambda r: r["zncc"])
    # Highest ZNCC among MISSING parts
    missing_sorted_by_zncc = sorted(all_missing_instances, key=lambda r: r["zncc"], reverse=True)

    # -------------------------------------------------------------
    # Write Box Fill Analysis to results/
    # -------------------------------------------------------------
    box_file = results_dir / "bounding_box_fill_analysis.txt"
    with open(box_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("  BOUNDING BOX COMPOSITION ANALYSIS (Substrate vs Component Body)\n")
        f.write("=" * 80 + "\n")
        f.write(f"{'Component Name':<16} | {'Type':<12} | {'BBox [w x h]':<14} | {'Comp Area %':<12} | {'Substrate Area %'}\n")
        f.write("-" * 80 + "\n")
        for b in sorted(box_analysis, key=lambda x: x["substrate_pct"], reverse=True):
            dims = f"{b['bbox'][2]}x{b['bbox'][3]}"
            f.write(f"{b['name']:<16} | {b['type']:<12} | {dims:<14} | {b['component_pct']:>10.1f}% | {b['substrate_pct']:>14.1f}%\n")
        f.write("=" * 80 + "\n")

    # -------------------------------------------------------------
    # Write Top Difficult Parts to results/
    # -------------------------------------------------------------
    extremes_file = results_dir / "top_difficult_parts.txt"
    with open(extremes_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("  10 LOWEST-SCORING PRESENT PARTS (Hardest populated parts)\n")
        f.write("=" * 80 + "\n")
        f.write(f"{'Image':<32} | {'Part':<14} | {'ZNCC':<8} | {'Diff MAE':<10} | {'Shift (dx, dy)'}\n")
        f.write("-" * 80 + "\n")
        for r in present_sorted_by_zncc[:10]:
            shift_str = f"({r['shift'][0]}, {r['shift'][1]})"
            f.write(f"{r['image']:<32} | {r['part']:<14} | {r['zncc']:<8.4f} | {r['diff']:<10.4f} | {shift_str}\n")

        f.write("\n" + "=" * 80 + "\n")
        f.write("  10 HIGHEST-SCORING MISSING PARTS (Hardest absent parts to flag)\n")
        f.write("=" * 80 + "\n")
        f.write(f"{'Image':<32} | {'Part':<14} | {'ZNCC':<8} | {'Diff MAE':<10} | {'Shift (dx, dy)'}\n")
        f.write("-" * 80 + "\n")
        for r in missing_sorted_by_zncc[:10]:
            shift_str = f"({r['shift'][0]}, {r['shift'][1]})"
            f.write(f"{r['image']:<32} | {r['part']:<14} | {r['zncc']:<8.4f} | {r['diff']:<10.4f} | {shift_str}\n")
        f.write("=" * 80 + "\n")

    # -------------------------------------------------------------
    # 3. Two-Fold Cross-Validation on Calibration Set
    # -------------------------------------------------------------
    fold1_images = calib_images[:10]  # calib_01 to calib_10
    fold2_images = calib_images[10:]  # calib_11 to calib_20

    def get_fold_stats(img_subset):
        pres_z, pres_d, miss_z, miss_d = [], [], [], []
        for k, meta in img_subset:
            exp_missing = set(meta["missing_parts"])
            for rec in per_image_results[k]:
                if rec["part"] in exp_missing:
                    miss_z.append(rec["zncc"])
                    miss_d.append(rec["diff"])
                else:
                    pres_z.append(rec["zncc"])
                    pres_d.append(rec["diff"])
        return {
            "min_pres_zncc": min(pres_z) if pres_z else 1.0,
            "max_miss_zncc": max(miss_z) if miss_z else 0.0,
            "max_pres_diff": max(pres_d) if pres_d else 0.0,
            "min_miss_diff": min(miss_d) if miss_d else 1.0,
        }

    stats_f1 = get_fold_stats(fold1_images)
    stats_f2 = get_fold_stats(fold2_images)

    # Fold 1 picks thresholds at the midpoints of its separation gap
    f1_mid_zncc = (stats_f1["min_pres_zncc"] + stats_f1["max_miss_zncc"]) / 2.0
    f1_mid_diff = (stats_f1["max_pres_diff"] + stats_f1["min_miss_diff"]) / 2.0

    # Fold 2 picks thresholds at the midpoints of its separation gap
    f2_mid_zncc = (stats_f2["min_pres_zncc"] + stats_f2["max_miss_zncc"]) / 2.0
    f2_mid_diff = (stats_f2["max_pres_diff"] + stats_f2["min_miss_diff"]) / 2.0

    def evaluate_fold_with_thresholds(test_subset, z_high, z_low, d_low, d_high):
        cfg = DetectionConfig(
            zncc_high_thresh=z_high,
            zncc_low_thresh=z_low,
            patch_diff_low_thresh=d_low,
            patch_diff_high_thresh=d_high,
            sensitivity="balanced",
        )
        total_exp_missing = 0
        total_det_missing = 0
        false_alarms = 0
        misses = 0
        uncertain = 0
        boards_correct = 0

        for k, meta in test_subset:
            exp_missing = set(meta["missing_parts"])
            part_verdicts = []
            for rec in per_image_results[k]:
                insp = {"zncc_score": rec["zncc"], "patch_diff": rec["diff"], "shift_px": rec["shift"]}
                verdict = classify_component(rec["part"], insp, cfg)
                part_verdicts.append(verdict)

                cid = rec["part"]
                det = verdict["status"]
                if cid in exp_missing and det == "PRESENT":
                    misses += 1
                elif cid not in exp_missing and det == "MISSING":
                    false_alarms += 1
                elif det == "UNCERTAIN":
                    uncertain += 1

            board_v = aggregate_board_status(part_verdicts)
            exp_status = meta["expected_board_status"]
            act_status = board_v["board_status"]
            if exp_status == act_status or (exp_status == "DEFECT" and act_status == "DEFECT"):
                boards_correct += 1

            total_exp_missing += len(exp_missing)
            total_det_missing += len(board_v["missing_components"])

        return {
            "boards_total": len(test_subset),
            "boards_correct": boards_correct,
            "exp_missing": total_exp_missing,
            "det_missing": total_det_missing,
            "false_alarms": false_alarms,
            "misses": misses,
            "uncertain": uncertain,
        }

    # Run Cross-Validation:
    # Model A: Trained on Fold 1, Tested on Fold 2
    res_f1_on_f2 = evaluate_fold_with_thresholds(
        fold2_images,
        z_high=f1_mid_zncc + 0.015,
        z_low=f1_mid_zncc - 0.015,
        d_low=f1_mid_diff - 0.015,
        d_high=f1_mid_diff + 0.015,
    )

    # Model B: Trained on Fold 2, Tested on Fold 1
    res_f2_on_f1 = evaluate_fold_with_thresholds(
        fold1_images,
        z_high=f2_mid_zncc + 0.015,
        z_low=f2_mid_zncc - 0.015,
        d_low=f2_mid_diff - 0.015,
        d_high=f2_mid_diff + 0.015,
    )

    cv_file = results_dir / "calibration_cv_split.txt"
    with open(cv_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("  CALIBRATION SET 2-FOLD CROSS-VALIDATION (Out-of-Fold Generalization)\n")
        f.write("=" * 80 + "\n")
        f.write("SPLIT DEFINITION:\n")
        f.write("  Fold 1: calib_01 to calib_10 (10 images: 6 complete, 4 defective)\n")
        f.write("  Fold 2: calib_11 to calib_20 (10 images: 1 complete, 9 defective)\n")
        f.write("-" * 80 + "\n")
        f.write("TRAIN ON FOLD 1 -> TEST ON FOLD 2:\n")
        f.write(f"  Fold 1 Separation: Min Present ZNCC = {stats_f1['min_pres_zncc']:.3f}, Max Missing ZNCC = {stats_f1['max_miss_zncc']:.3f}\n")
        f.write(f"  Chosen Thresholds: ZNCC mid = {f1_mid_zncc:.3f}, Diff mid = {f1_mid_diff:.3f}\n")
        f.write(f"  Test Results on Fold 2:\n")
        f.write(f"    - Board-level Accuracy  : {res_f1_on_f2['boards_correct']} / {res_f1_on_f2['boards_total']} ({res_f1_on_f2['boards_correct']/res_f1_on_f2['boards_total']*100:.1f}%)\n")
        f.write(f"    - Expected Missing Parts: {res_f1_on_f2['exp_missing']}\n")
        f.write(f"    - Detected Missing Parts: {res_f1_on_f2['det_missing']}\n")
        f.write(f"    - False Alarms          : {res_f1_on_f2['false_alarms']}\n")
        f.write(f"    - Misses                : {res_f1_on_f2['misses']}\n")
        f.write(f"    - Uncertain Calls       : {res_f1_on_f2['uncertain']}\n")
        f.write("-" * 80 + "\n")
        f.write("TRAIN ON FOLD 2 -> TEST ON FOLD 1:\n")
        f.write(f"  Fold 2 Separation: Min Present ZNCC = {stats_f2['min_pres_zncc']:.3f}, Max Missing ZNCC = {stats_f2['max_miss_zncc']:.3f}\n")
        f.write(f"  Chosen Thresholds: ZNCC mid = {f2_mid_zncc:.3f}, Diff mid = {f2_mid_diff:.3f}\n")
        f.write(f"  Test Results on Fold 1:\n")
        f.write(f"    - Board-level Accuracy  : {res_f2_on_f1['boards_correct']} / {res_f2_on_f1['boards_total']} ({res_f2_on_f1['boards_correct']/res_f2_on_f1['boards_total']*100:.1f}%)\n")
        f.write(f"    - Expected Missing Parts: {res_f2_on_f1['exp_missing']}\n")
        f.write(f"    - Detected Missing Parts: {res_f2_on_f1['det_missing']}\n")
        f.write(f"    - False Alarms          : {res_f2_on_f1['false_alarms']}\n")
        f.write(f"    - Misses                : {res_f2_on_f1['misses']}\n")
        f.write(f"    - Uncertain Calls       : {res_f2_on_f1['uncertain']}\n")
        f.write("=" * 80 + "\n")

    print("Completed diagnostic analysis and saved outputs to 'results/' folder:")
    print(f" - {box_file}")
    print(f" - {extremes_file}")
    print(f" - {cv_file}")


if __name__ == "__main__":
    analyze()
