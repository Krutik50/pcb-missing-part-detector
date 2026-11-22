"""
Evaluation & Calibration Harness for PCB Missing Component Detector.
Runs by default ONLY on the Calibration Set (sample_data/calibration/).
Runs on the Held-Out Test Set (sample_data/test_heldout/) ONLY when --test is passed.

Outputs:
1. Per-image results table (Expected vs Detected, Board Status, False Alarms, Misses).
2. Measured execution latency (per board and per component).
3. Score distribution ranges (Min, 25%, Median, 75%, Max) for populated vs missing components.
4. Separation gap analysis to guide threshold tuning.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
import numpy as np

# Ensure app package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import DetectionConfig, DEFAULT_CONFIG
from app.core.image_loader import load_image_with_exif, normalize_to_reference
from app.core.aligner import align_test_to_reference
from app.core.detector import inspect_component
from app.core.decision import classify_component, aggregate_board_status


def run_evaluation(target_split: str = "calibration", sensitivity: str = "balanced", custom_config: DetectionConfig = None):
    sample_dir = Path("sample_data")
    gt_file = sample_dir / "ground_truth.json"

    if not gt_file.exists():
        print(f"Error: Ground truth file '{gt_file}' not found. Run 'python generate_samples.py' first.")
        sys.exit(1)

    with open(gt_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    ref_rel = gt_data["images"]["reference.png"]["relative_path"]
    ref_path = sample_dir / ref_rel
    if not ref_path.exists():
        print(f"Error: Reference image '{ref_path}' not found.")
        sys.exit(1)

    # Load and cap reference image
    ref_img, orig_shape, scale = load_image_with_exif(ref_path, max_dimension=1920)
    components_meta = gt_data["components"]

    # Filter target images according to split
    images_to_evaluate = []
    for img_key, meta in gt_data["images"].items():
        if meta.get("split") == target_split:
            images_to_evaluate.append((img_key, meta))

    if not images_to_evaluate:
        print(f"No images found for split '{target_split}'.")
        sys.exit(1)

    config = custom_config or DEFAULT_CONFIG
    config.sensitivity = sensitivity
    thresholds = config.get_effective_thresholds()

    print("=" * 82)
    print(f"  PCB MISSING COMPONENT DETECTOR - EVALUATION HARNESS")
    print("=" * 82)
    print(f"Target Split      : {target_split.upper()} ({len(images_to_evaluate)} images)")
    print(f"Sensitivity Mode  : {sensitivity.upper()}")
    print(f"Active Thresholds : ZNCC [low: {thresholds['zncc_low']:.2f}, high: {thresholds['zncc_high']:.2f}] | Diff [low: {thresholds['diff_low']:.2f}, high: {thresholds['diff_high']:.2f}]")
    print(f"Search Slack      : ±{config.search_margin_px} pixels")
    print("-" * 82)

    total_components_evaluated = 0
    total_expected_missing = 0
    total_detected_missing = 0
    false_alarms = 0  # Present flagged as Missing
    misses = 0        # Missing flagged as Present
    uncertain_count = 0

    present_scores_zncc = []
    present_scores_diff = []
    missing_scores_zncc = []
    missing_scores_diff = []

    board_correct = 0
    per_board_times = []
    per_component_times = []

    print(f"{'Image Filename':<32} | {'Exp':<6} | {'Det':<6} | {'Status':<10} | {'FA':<4} | {'Miss':<4} | {'Time (ms)'}")
    print("-" * 82)

    for img_key, meta in images_to_evaluate:
        img_path = sample_dir / meta["relative_path"]
        if not img_path.exists():
            print(f"Warning: File not found {img_path}")
            continue

        t_start = time.perf_counter()

        # Step 1: Load and normalize
        test_raw, _, _ = load_image_with_exif(img_path, max_dimension=1920)
        ref_norm, test_norm, mask, _ = normalize_to_reference(ref_img, test_raw)

        # Step 2: Global ECC alignment with border mask & fallback
        aligned_test, warp_mat, align_info = align_test_to_reference(
            ref_norm, test_norm, mask=mask,
            motion_type=config.alignment_motion_type,
            downscale=config.alignment_downscale_factor,
            max_iterations=config.alignment_max_iterations,
            eps=config.alignment_eps,
        )

        # Step 3: Inspect each component
        comp_results = []
        expected_missing_set = set(meta["missing_parts"])

        for cid, cinfo in components_meta.items():
            t_comp_start = time.perf_counter()
            bbox = cinfo["pixel_bbox"]
            insp = inspect_component(ref_norm, aligned_test, bbox, search_margin_px=config.search_margin_px)
            t_comp_dt = (time.perf_counter() - t_comp_start) * 1000.0
            per_component_times.append(t_comp_dt)

            verdict = classify_component(cid, insp, config)
            comp_results.append(verdict)

            # Record score distributions based on ground truth
            if cid in expected_missing_set:
                missing_scores_zncc.append(insp["zncc_score"])
                missing_scores_diff.append(insp["patch_diff"])
            else:
                present_scores_zncc.append(insp["zncc_score"])
                present_scores_diff.append(insp["patch_diff"])

            # Component-level error tracking
            det_status = verdict["status"]
            if cid in expected_missing_set and det_status == "PRESENT":
                misses += 1
            elif cid not in expected_missing_set and det_status == "MISSING":
                false_alarms += 1
            elif det_status == "UNCERTAIN":
                uncertain_count += 1

        t_end = time.perf_counter()
        elapsed_ms = (t_end - t_start) * 1000.0
        per_board_times.append(elapsed_ms)

        board_verdict = aggregate_board_status(comp_results)
        expected_board_status = meta["expected_board_status"]
        actual_board_status = board_verdict["board_status"]

        is_board_correct = (expected_board_status == actual_board_status) or (
            expected_board_status == "DEFECT" and actual_board_status == "DEFECT"
        )
        if is_board_correct:
            board_correct += 1

        exp_count = len(expected_missing_set)
        det_count = len(board_verdict["missing_components"])
        total_expected_missing += exp_count
        total_detected_missing += det_count
        total_components_evaluated += len(components_meta)

        # Image-level false alarms/misses in this board
        board_fa = sum(1 for p in comp_results if p["status"] == "MISSING" and p["name"] not in expected_missing_set)
        board_miss = sum(1 for p in comp_results if p["status"] == "PRESENT" and p["name"] in expected_missing_set)

        img_short_name = Path(img_key).name
        status_display = f"{actual_board_status}" if is_board_correct else f"{actual_board_status}*{expected_board_status}"
        print(f"{img_short_name:<32} | {exp_count:<6} | {det_count:<6} | {status_display:<10} | {board_fa:<4} | {board_miss:<4} | {elapsed_ms:>8.1f} ms")

    # -------------------------------------------------------------
    # Summary & Metrics
    # -------------------------------------------------------------
    num_boards = len(images_to_evaluate)
    board_acc = (board_correct / num_boards) * 100.0 if num_boards else 0.0

    print("=" * 82)
    print("  EVALUATION SUMMARY")
    print("=" * 82)
    print(f"Total Boards Evaluated      : {num_boards}")
    print(f"Board-Level Correct Verdicts: {board_correct} / {num_boards} ({board_acc:.1f}%)")
    print(f"Total Components Tested     : {total_components_evaluated}")
    print(f"Expected Missing Components : {total_expected_missing}")
    print(f"Detected Missing Components : {total_detected_missing}")
    print(f"False Alarms (False Pos)    : {false_alarms} (Present marked as Missing)")
    print(f"Misses (False Negatives)    : {misses} (Missing marked as Present)")
    print(f"Uncertain / Borderline Calls: {uncertain_count} (Flagged for visual check)")
    print("-" * 82)

    # Timing metrics
    avg_board_time = np.mean(per_board_times) if per_board_times else 0.0
    avg_comp_time = np.mean(per_component_times) if per_component_times else 0.0
    print(f"Measured Speed (Wall-Clock Latency):")
    print(f" - Average per full 1080p board : {avg_board_time:.1f} ms  (Min: {np.min(per_board_times):.1f} ms, Max: {np.max(per_board_times):.1f} ms)")
    print(f" - Average per component crop   : {avg_comp_time:.2f} ms")
    print("-" * 82)

    # Score Distribution & Separation Analysis
    print("SCORE DISTRIBUTION & SEPARATION ANALYSIS")
    print("(Use this empirical gap to calibrate decision thresholds)")
    print("-" * 82)

    def stats_str(arr):
        if not arr:
            return "N/A"
        arr = np.array(arr)
        return (f"Min: {np.min(arr):.3f} | 25%: {np.percentile(arr, 25):.3f} | "
                f"Median: {np.median(arr):.3f} | 75%: {np.percentile(arr, 75):.3f} | Max: {np.max(arr):.3f}")

    print("1. ZNCC Appearance Correlation Score (Higher is more similar):")
    print(f"   - Components PRESENT (Good) : {stats_str(present_scores_zncc)}")
    print(f"   - Components MISSING (Empty): {stats_str(missing_scores_zncc)}")

    print("\n2. Normalized Patch Difference MAE (Lower is more similar):")
    print(f"   - Components PRESENT (Good) : {stats_str(present_scores_diff)}")
    print(f"   - Components MISSING (Empty): {stats_str(missing_scores_diff)}")

    # Calculate separation gap
    if present_scores_zncc and missing_scores_zncc:
        zncc_gap = np.min(present_scores_zncc) - np.max(missing_scores_zncc)
        diff_gap = np.min(missing_scores_diff) - np.max(present_scores_diff)
        print("-" * 82)
        print("Empirical Separation Gap:")
        print(f" - ZNCC Gap   : {zncc_gap:+.3f} (Positive indicates clean margin)")
        print(f" - Diff MAE Gap: {diff_gap:+.3f} (Positive indicates clean margin)")

    print("=" * 82)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate PCB Missing Component Detector on Calibration or Held-Out Test Set")
    parser.add_argument("--test", "--held-out", action="store_true", help="Explicitly evaluate on the held-out test set (Default: calibration set only)")
    parser.add_argument("--sensitivity", type=str, default="balanced", choices=["balanced", "strict", "lenient"], help="Sensitivity profile to evaluate")
    args = parser.parse_args()

    split = "test_heldout" if args.test else "calibration"
    run_evaluation(target_split=split, sensitivity=args.sensitivity)
