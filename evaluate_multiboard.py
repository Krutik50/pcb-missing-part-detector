"""
Comprehensive Multi-Board Physical PCB Benchmark (70:30 Split, 500 Boards)
Evaluates Cascaded Hybrid Engine across 5 diverse physical hardware architectures:
  1. Arduino Uno R3 DIP (Microcontroller, mixed SMT/THT)
  2. Phenolic Single-Sided Appliance Board (Consumer/HVAC)
  3. Industrial Weighing Controller PMS-63 (Industrial automation)
  4. Analog Instrumentation Board (Precision analog/sensors)
  5. Inverter Power Board (Power electronics/heavy copper)

Evaluates:
  - 7 Defect Modes: MISSING, TILTED, MISALIGNED, BRIDGED, POLARITY_REVERSED, TOMBSTONED, PRESENT
  - Component Presence / Absence (Zero-Escape Defect Policy)
  - Rotational Skew / Tilt Detection (|Delta theta| > 3.5 deg)
  - Positional Shift / Misalignment Detection (Delta > 5.0 px)
  - Solder Bridge / Solder Ball Detection
  - Polarity Inversion (180 deg orientation check)
  - Tombstoning / Lifted Lead Disparity
  - False Alarm Rate on Nominal Boards
  - Latency per Board (ms)
"""

import argparse
import json
import time
from pathlib import Path
from typing import Dict, Any, List
import numpy as np

from app.core.image_loader import load_image_with_exif, normalize_to_reference
from app.core.aligner import align_test_to_reference
from app.core.detector import inspect_component
from app.core.decision import classify_component, aggregate_board_status
from app.core.config import DetectionConfig
from app.core.dl_verifier import get_dl_verifier

DEFECT_TYPES = ["MISSING", "TILTED", "MISALIGNED", "BRIDGED", "POLARITY_REVERSED", "TOMBSTONED"]

def run_multiboard_benchmark(split_filter="test", board_filter="all", max_boards=None) -> Dict[str, Any]:
    root = Path(__file__).resolve().parent
    dataset_dir = root / "data" / "multiboard"
    gt_file = dataset_dir / "ground_truth_multiboard.json"

    # Auto-generate dataset variations if not present locally
    if not gt_file.exists() or not (dataset_dir / "test").exists():
        import subprocess, sys
        print("Dataset images not found. Auto-generating 500-board physical dataset via scripts/generate_physical_dataset_from_user_images.py...")
        subprocess.run([sys.executable, str(root / "scripts" / "generate_physical_dataset_from_user_images.py")], check=True)

    with open(gt_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    boards_meta = gt_data["boards"]
    images_dict = gt_data["images"]

    # Filter images by split
    if split_filter and split_filter != "all":
        images_to_eval = [
            (img_rel, meta) for img_rel, meta in images_dict.items()
            if meta.get("split") == split_filter
        ]
    else:
        images_to_eval = list(images_dict.items())

    # Filter by board architecture if requested
    if board_filter and board_filter != "all":
        images_to_eval = [
            (img_rel, meta) for img_rel, meta in images_to_eval
            if meta.get("board_id") == board_filter
        ]

    if max_boards:
        images_to_eval = images_to_eval[:max_boards]

    cfg = DetectionConfig(sensitivity="balanced")
    dl_verifier = get_dl_verifier()

    # Pre-cache reference images
    ref_cache = {}
    for b_type, b_info in boards_meta.items():
        ref_path = dataset_dir / b_info["reference_image"]
        ref_bgr, _, _ = load_image_with_exif(ref_path, max_dimension=1920)
        ref_cache[b_type] = ref_bgr

    split_title = "HELD-OUT TEST SPLIT (30% Unseen Verification - 150 Boards)" if split_filter == "test" else (
        "TRAINING / CALIBRATION SPLIT (70% - 350 Boards)" if split_filter == "train" else f"FULL DATASET ({len(images_to_eval)} Boards)"
    )
    print("=" * 80, flush=True)
    print(f"MULTI-BOARD BENCHMARK: {split_title}", flush=True)
    print(f"Total Boards to Inspect : {len(images_to_eval)}", flush=True)
    print(f"Board Types Represented : {len(boards_meta)} Physical Hardware Architectures", flush=True)
    print("=" * 80, flush=True)

    # State tracking for both modes in a single pass
    stats = {
        "rule_based_only": {
            "total_evals": 0, "correct_verdicts": 0, "false_alarms": 0,
            "missed_defects": 0, "uncertain_calls": 0, "board_correct": 0,
            "defects_actual": {dt: 0 for dt in DEFECT_TYPES},
            "defects_detected": {dt: 0 for dt in DEFECT_TYPES}
        },
        "cascaded_hybrid": {
            "total_evals": 0, "correct_verdicts": 0, "false_alarms": 0,
            "missed_defects": 0, "uncertain_calls": 0, "board_correct": 0,
            "defects_actual": {dt: 0 for dt in DEFECT_TYPES},
            "defects_detected": {dt: 0 for dt in DEFECT_TYPES}
        }
    }

    t0 = time.perf_counter()

    for idx, (img_rel, meta) in enumerate(images_to_eval, 1):
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

        comp_results_rule = []
        comp_results_hybrid = []

        for cname, cinfo in sorted(components.items()):
            px_box = cinfo["bbox"]
            x, y, w, h = px_box

            actual_defect = defects_meta.get(cname)
            actual_state = actual_defect["type"] if actual_defect else "PRESENT"

            s1 = inspect_component(ref_norm, aligned_test, px_box, search_margin_px=cfg.search_margin_px)
            dec_rule = classify_component(cname, s1, cfg)

            # Deep Learning verification for cascaded hybrid mode
            dec_hybrid = dict(dec_rule)
            ref_crop = ref_norm[y:y+h, x:x+w]
            test_crop = aligned_test[y:y+h, x:x+w]
            has_glare = dl_verifier.detect_glare_saturation(test_crop)
            core_check = dl_verifier.evaluate_package_mold_core(ref_crop, test_crop)
            is_empty_footprint = (dec_rule["status"] == "PRESENT" and core_check["core_delta_e"] > 30.0 and not has_glare)
            is_glare_fa = (dec_rule["status"] == "MISSING" and has_glare)

            if dec_rule["status"] == "UNCERTAIN" or is_empty_footprint or is_glare_fa:
                dl_res = dl_verifier.verify(ref_crop, test_crop, s1, component_type=cinfo.get("type", "GENERIC"))
                if dl_res["status"] != "UNCERTAIN":
                    dec_hybrid["status"] = dl_res["status"]
                    dec_hybrid["reason"] = dl_res["reason"]

            # Record stats for each mode
            for mode, dec in [("rule_based_only", dec_rule), ("cascaded_hybrid", dec_hybrid)]:
                st_data = stats[mode]
                st_data["total_evals"] += 1
                if actual_state in st_data["defects_actual"]:
                    st_data["defects_actual"][actual_state] += 1

                st = dec["status"]
                if actual_state == "PRESENT":
                    if st == "PRESENT":
                        st_data["correct_verdicts"] += 1
                    elif st in DEFECT_TYPES:
                        st_data["false_alarms"] += 1
                    else:
                        st_data["uncertain_calls"] += 1
                else:
                    is_detected = (st == actual_state) or (st in DEFECT_TYPES)
                    if is_detected:
                        st_data["correct_verdicts"] += 1
                        if actual_state in st_data["defects_detected"] and st == actual_state:
                            st_data["defects_detected"][actual_state] += 1
                    elif st == "PRESENT":
                        st_data["missed_defects"] += 1
                    else:
                        st_data["uncertain_calls"] += 1

            comp_results_rule.append(dec_rule)
            comp_results_hybrid.append(dec_hybrid)

        # Board level verification
        for mode, c_res in [("rule_based_only", comp_results_rule), ("cascaded_hybrid", comp_results_hybrid)]:
            b_eval = aggregate_board_status(c_res)
            act_b_status = b_eval["board_status"]
            is_b_correct = (expected_board_status == act_b_status) or (
                expected_board_status == "DEFECT" and act_b_status == "DEFECT"
            )
            if is_b_correct:
                stats[mode]["board_correct"] += 1

        if idx % 25 == 0 or idx == len(images_to_eval):
            print(f"  Processed [{idx:>3}/{len(images_to_eval)}] boards... ({time.perf_counter()-t0:.1f}s)", flush=True)

    elapsed = time.perf_counter() - t0
    per_board_ms = (elapsed / len(images_to_eval)) * 1000.0

    mode_results = {}
    for mode in ["rule_based_only", "cascaded_hybrid"]:
        st_data = stats[mode]
        board_correct = st_data["board_correct"]
        total_evals = st_data["total_evals"]
        correct_verdicts = st_data["correct_verdicts"]
        false_alarms = st_data["false_alarms"]
        missed_defects = st_data["missed_defects"]
        uncertain_calls = st_data["uncertain_calls"]

        title = "MODE 1: PURE RULE-BASED (Frozen Baseline)" if mode == "rule_based_only" else "MODE 2: CASCADED HYBRID (Rule Gate + Stage 2 DL)"
        print(f"\n{title}", flush=True)
        print("-" * 75, flush=True)
        print(f"  Boards Evaluated        : {len(images_to_eval)}", flush=True)
        print(f"  Board-Level Accuracy    : {board_correct}/{len(images_to_eval)} ({board_correct/len(images_to_eval)*100:.1f}%)", flush=True)
        print(f"  Total Part Inspections  : {total_evals}", flush=True)
        print(f"  Correct Verdicts        : {correct_verdicts}/{total_evals} ({correct_verdicts/total_evals*100:.1f}%)", flush=True)
        print(f"  False Alarms (FA)       : {false_alarms}", flush=True)
        print(f"  Missed Defects (FN)     : {missed_defects} (Zero Escapes Target)", flush=True)
        print(f"  Uncertain (Sign-Off)    : {uncertain_calls}", flush=True)
        print(f"  Defect Detection Rates (IPC-A-610 Classes):", flush=True)
        defect_breakdown = {}
        for dtype in DEFECT_TYPES:
            total_d = st_data["defects_actual"][dtype]
            det_d = st_data["defects_detected"][dtype]
            pct = (det_d / total_d * 100.0) if total_d > 0 else 100.0
            defect_breakdown[dtype] = {"actual": total_d, "detected": det_d, "rate_pct": round(pct, 2)}
            print(f"    - {dtype:<18}: {det_d}/{total_d} ({pct:.1f}%)", flush=True)
        print(f"  Avg Latency per Board   : {per_board_ms:.1f} ms", flush=True)

        mode_results[mode] = {
            "boards_evaluated": len(images_to_eval),
            "board_accuracy_pct": round(board_correct / len(images_to_eval) * 100.0, 2),
            "total_part_evals": total_evals,
            "part_accuracy_pct": round(correct_verdicts / total_evals * 100.0, 2),
            "false_alarms": false_alarms,
            "missed_defects": missed_defects,
            "uncertain_calls": uncertain_calls,
            "defect_breakdown": defect_breakdown,
            "avg_latency_ms": round(per_board_ms, 2)
        }

    return mode_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Board Physical PCB Benchmark across 5 hardware architectures.")
    parser.add_argument("--split", choices=["test", "train", "all"], default="test",
                        help="Dataset split to evaluate (default: test)")
    parser.add_argument("--board", choices=["all", "arduino_uno", "appliance_board", "scale_controller", "analog_sensor", "inverter_driver"],
                        default="all", help="Target board architecture filter (default: all)")
    parser.add_argument("--max-boards", type=int, default=None,
                        help="Limit evaluation to first N boards for rapid verification")
    parser.add_argument("--output", type=str, default=None,
                        help="Path to save benchmark JSON summary (default: results/multiboard_benchmark.json)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    results_dir = root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    if args.split == "all":
        print("\n>>> RUNNING TEST SET (HELD-OUT 30%) BENCHMARK")
        test_res = run_multiboard_benchmark(split_filter="test", board_filter=args.board, max_boards=args.max_boards)
        print("\n>>> RUNNING TRAINING SET (CALIBRATION 70%) BENCHMARK")
        train_res = run_multiboard_benchmark(split_filter="train", board_filter=args.board, max_boards=args.max_boards)
        summary = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "test_results": test_res, "train_results": train_res}
    else:
        print(f"\n>>> RUNNING {args.split.upper()} SET BENCHMARK (Board filter: {args.board})")
        res = run_multiboard_benchmark(split_filter=args.split, board_filter=args.board, max_boards=args.max_boards)
        summary = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "split": args.split, "board_filter": args.board, "results": res}

    out_file = Path(args.output) if args.output else results_dir / "multiboard_benchmark.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[OK] Benchmark metrics successfully saved to {out_file}")
