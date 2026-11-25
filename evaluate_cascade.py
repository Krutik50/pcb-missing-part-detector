"""
Evaluation benchmark comparing:
1. Baseline Pure Rule-Based Engine (Frozen Thresholds)
2. Cascaded Hybrid Engine (Stage 1 Rule-Based Primary + Stage 2 Deep Learning Triage)
on the held-out test dataset.
"""

import argparse
import json
import time
from pathlib import Path
import numpy as np

from app.core.image_loader import load_image_with_exif, normalize_to_reference
from app.core.aligner import align_test_to_reference
from app.core.detector import inspect_component
from app.core.decision import classify_component, aggregate_board_status
from app.core.config import DetectionConfig
from app.core.dl_verifier import get_dl_verifier

def run_benchmark(mode_filter: str = "all", max_boards: int = None):
    root = Path(__file__).resolve().parent
    sample_dir = root / "sample_data"
    gt_file = sample_dir / "ground_truth.json"
    ref_file = sample_dir / "reference.png"

    with open(gt_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    ref_bgr, _, _ = load_image_with_exif(ref_file, max_dimension=1920)
    cfg = DetectionConfig(sensitivity="balanced")
    dl_verifier = get_dl_verifier()

    # Get heldout images from ground_truth.json
    images_to_eval = [
        (k, v) for k, v in gt_data["images"].items() if v.get("split") == "test_heldout"
    ]
    if max_boards:
        images_to_eval = images_to_eval[:max_boards]

    components = gt_data["components"]

    print("=" * 80)
    print("BENCHMARK: PURE RULE-BASED vs CASCADED HYBRID (RULE + DEEP LEARNING)")
    print("=" * 80)

    modes = ["rule_based_only", "cascaded_hybrid"] if mode_filter == "all" else [mode_filter]
    for mode in modes:
        total_evals = 0
        correct_calls = 0
        false_alarms = 0
        missed_defects = 0
        uncertain_calls = 0
        board_correct = 0

        t0 = time.perf_counter()

        for img_key, meta in images_to_eval:
            img_path = sample_dir / meta["relative_path"]
            expected_missing = set(meta.get("missing_parts", []))
            expected_board_status = meta.get("expected_board_status", "DEFECT" if expected_missing else "OK")

            test_bgr, _, _ = load_image_with_exif(img_path, max_dimension=1920)
            ref_norm, test_norm, mask, _ = normalize_to_reference(ref_bgr, test_bgr)
            aligned_test, _, _ = align_test_to_reference(
                ref_norm, test_norm, mask=mask,
                motion_type=cfg.alignment_motion_type,
                downscale=cfg.alignment_downscale_factor
            )

            comp_results = []
            for cname, cinfo in sorted(components.items()):
                total_evals += 1
                px_box = cinfo["pixel_bbox"]
                x, y, w, h = px_box
                is_actually_missing = cname in expected_missing

                s1 = inspect_component(ref_norm, aligned_test, px_box, search_margin_px=cfg.search_margin_px)
                dec = classify_component(cname, s1, cfg)

                if mode == "cascaded_hybrid":
                    ref_crop = ref_norm[y:y+h, x:x+w]
                    test_crop = aligned_test[y:y+h, x:x+w]
                    has_glare = dl_verifier.detect_glare_saturation(test_crop)
                    core_check = dl_verifier.evaluate_package_mold_core(ref_crop, test_crop)
                    is_empty_footprint = (dec["status"] == "PRESENT" and core_check["core_delta_e"] > 30.0 and not has_glare)
                    is_glare_fa = (dec["status"] == "MISSING" and has_glare)

                    if dec["status"] == "UNCERTAIN" or is_empty_footprint or is_glare_fa:
                        dl_res = dl_verifier.verify(ref_crop, test_crop, s1, component_type=cinfo.get("type", "GENERIC"))
                        if dl_res["status"] != "UNCERTAIN":
                            dec["status"] = dl_res["status"]
                            dec["reason"] = dl_res["reason"]

                st = dec["status"]
                if is_actually_missing:
                    if st == "MISSING":
                        correct_calls += 1
                    elif st == "PRESENT":
                        missed_defects += 1
                    else:
                        uncertain_calls += 1
                else:
                    if st == "PRESENT":
                        correct_calls += 1
                    elif st == "MISSING":
                        false_alarms += 1
                    else:
                        uncertain_calls += 1

                comp_results.append(dec)

            board_eval = aggregate_board_status(comp_results)
            actual_board_status = board_eval["board_status"]
            is_board_correct = (expected_board_status == actual_board_status) or (
                expected_board_status == "DEFECT" and actual_board_status == "DEFECT"
            )
            if is_board_correct:
                board_correct += 1

        elapsed = time.perf_counter() - t0
        per_board_ms = (elapsed / len(images_to_eval)) * 1000.0

        title = "MODE 1: PURE RULE-BASED (Frozen Baseline)" if mode == "rule_based_only" else "MODE 2: CASCADED HYBRID (Rule-Based Gate + Stage 2 DL)"
        print(f"\n{title}")
        print("-" * 70)
        print(f"  Boards Evaluated        : {len(images_to_eval)}")
        print(f"  Board-Level Accuracy    : {board_correct}/{len(images_to_eval)} ({board_correct/len(images_to_eval)*100:.1f}%)")
        print(f"  Total Part Evaluations  : {total_evals}")
        print(f"  Correct Verdicts        : {correct_calls}")
        print(f"  False Alarms (FA)       : {false_alarms}")
        print(f"  Missed Defects (FN)     : {missed_defects}")
        print(f"  Uncertain (Human Review): {uncertain_calls}")
        print(f"  Avg Latency per Board   : {per_board_ms:.1f} ms")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cascaded Hybrid Engine Benchmark on held-out test dataset.")
    parser.add_argument("--mode", choices=["all", "rule_based_only", "cascaded_hybrid"], default="all",
                        help="Operating mode to benchmark (default: all)")
    parser.add_argument("--max-boards", type=int, default=None,
                        help="Limit evaluation to first N boards for rapid testing")
    args = parser.parse_args()

    run_benchmark(mode_filter=args.mode, max_boards=args.max_boards)
