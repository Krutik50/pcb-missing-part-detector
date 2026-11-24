"""
Comprehensive Multi-Board Physical PCB Benchmark (70:30 Split)
Evaluates Cascaded Hybrid Engine across 5 diverse board types:
  1. LM2596 Buck Converter (Power, simple)
  2. MPU-6050 Motion Sensor (Sensors, simple)
  3. Arduino Uno R3 (Microcontroller, medium)
  4. ESP32-WROOM-32 IoT Module (Wireless/RF, medium)
  5. Industrial Sensor Controller (High density, complex)

Evaluates:
  - Component Presence / Absence (Zero-Escape Missing Part Detection)
  - Rotational Skew / Tilt Detection (|Delta theta| > 3.5 deg)
  - Positional Shift / Misalignment Detection (Delta > 5.0 px)
  - False Alarm Rate on Nominal Boards
  - Latency per Board (ms)
"""

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

def run_multiboard_benchmark(split_filter="test"):
    root = Path(__file__).resolve().parent
    dataset_dir = root / "data" / "multiboard"
    gt_file = dataset_dir / "ground_truth_multiboard.json"

    # Auto-generate dataset variations if not present locally
    if not gt_file.exists() or not (dataset_dir / "test").exists():
        import subprocess, sys
        print("Dataset images not found. Auto-generating 70-board physical dataset via scripts/generate_physical_multiboard_dataset.py...")
        subprocess.run([sys.executable, str(root / "scripts" / "generate_physical_multiboard_dataset.py")], check=True)

    with open(gt_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    boards_meta = gt_data["boards"]
    images_dict = gt_data["images"]

    # Filter images by split
    if split_filter:
        images_to_eval = [
            (img_rel, meta) for img_rel, meta in images_dict.items()
            if meta.get("split") == split_filter
        ]
    else:
        images_to_eval = list(images_dict.items())

    cfg = DetectionConfig(sensitivity="balanced")
    dl_verifier = get_dl_verifier()

    # Pre-cache reference images
    ref_cache = {}
    for b_type, b_info in boards_meta.items():
        ref_path = dataset_dir / b_info["reference_image"]
        ref_bgr, _, _ = load_image_with_exif(ref_path, max_dimension=1920)
        ref_cache[b_type] = ref_bgr

    split_title = "HELD-OUT TEST SPLIT (30% Unseen Verification)" if split_filter == "test" else (
        "TRAINING / CALIBRATION SPLIT (70%)" if split_filter == "train" else "FULL DATASET (70 Boards)"
    )
    print("=" * 80)
    print(f"MULTI-BOARD BENCHMARK: {split_title}")
    print(f"Total Boards to Inspect : {len(images_to_eval)}")
    print(f"Board Types Represented : {len(boards_meta)} (Simple, Medium, Complex)")
    print("=" * 80)

    for mode in ["rule_based_only", "cascaded_hybrid"]:
        total_evals = 0
        correct_verdicts = 0
        false_alarms = 0
        missed_defects = 0
        uncertain_calls = 0
        board_correct = 0

        # Detailed defect breakdowns
        defects_actual = {"MISSING": 0, "TILTED": 0, "MISALIGNED": 0}
        defects_detected = {"MISSING": 0, "TILTED": 0, "MISALIGNED": 0}

        t0 = time.perf_counter()

        for img_rel, meta in images_to_eval:
            b_type = meta["board_type"]
            b_info = boards_meta[b_type]
            components = b_info["components"]

            img_path = dataset_dir / img_rel
            expected_board_status = meta["expected_board_status"]
            defects_meta = meta.get("defects", {})

            ref_bgr = ref_cache[b_type]
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
                px_box = cinfo["bbox"]
                x, y, w, h = px_box

                actual_defect = defects_meta.get(cname)
                actual_state = actual_defect["type"] if actual_defect else "PRESENT"
                if actual_state in defects_actual:
                    defects_actual[actual_state] += 1

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

                # Evaluation against actual state
                if actual_state == "PRESENT":
                    if st == "PRESENT":
                        correct_verdicts += 1
                    elif st in ("MISSING", "TILTED", "MISALIGNED"):
                        false_alarms += 1
                    else:
                        uncertain_calls += 1
                else:
                    # Defective component
                    is_detected_as_defect = (st == actual_state) or (st in ("MISSING", "TILTED", "MISALIGNED"))
                    if is_detected_as_defect:
                        correct_verdicts += 1
                        if actual_state in defects_detected and st == actual_state:
                            defects_detected[actual_state] += 1
                    elif st == "PRESENT":
                        missed_defects += 1
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

        title = "MODE 1: PURE RULE-BASED (Frozen Baseline)" if mode == "rule_based_only" else "MODE 2: CASCADED HYBRID (Rule Gate + Stage 2 DL)"
        print(f"\n{title}")
        print("-" * 75)
        print(f"  Boards Evaluated        : {len(images_to_eval)}")
        print(f"  Board-Level Accuracy    : {board_correct}/{len(images_to_eval)} ({board_correct/len(images_to_eval)*100:.1f}%)")
        print(f"  Total Part Inspections  : {total_evals}")
        print(f"  Correct Verdicts        : {correct_verdicts}/{total_evals} ({correct_verdicts/total_evals*100:.1f}%)")
        print(f"  False Alarms (FA)       : {false_alarms}")
        print(f"  Missed Defects (FN)     : {missed_defects} (Zero Escapes Target)")
        print(f"  Uncertain (Sign-Off)    : {uncertain_calls}")
        print(f"  Defect Detection Rates:")
        for dtype in ["MISSING", "TILTED", "MISALIGNED"]:
            total_d = defects_actual[dtype]
            det_d = defects_detected[dtype]
            pct = (det_d / total_d * 100.0) if total_d > 0 else 100.0
            print(f"    - {dtype:<11}: {det_d}/{total_d} ({pct:.1f}%)")
        print(f"  Avg Latency per Board   : {per_board_ms:.1f} ms")

if __name__ == "__main__":
    print("\n>>> RUNNING TEST SET (HELD-OUT 30%) BENCHMARK")
    run_multiboard_benchmark(split_filter="test")

    print("\n\n>>> RUNNING TRAINING SET (CALIBRATION 70%) BENCHMARK")
    run_multiboard_benchmark(split_filter="train")
