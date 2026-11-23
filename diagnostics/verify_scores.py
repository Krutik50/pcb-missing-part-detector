import json
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.config import DetectionConfig
from app.core.image_loader import load_image_with_exif, normalize_to_reference
from app.core.aligner import align_test_to_reference
from app.core.detector import inspect_component
from app.core.decision import classify_component, aggregate_board_status

def main():
    sample_dir = ROOT / "sample_data"
    gt_file = sample_dir / "ground_truth.json"
    with open(gt_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    ref_img, _, _ = load_image_with_exif(sample_dir / "reference.png")
    components_meta = gt_data["components"]

    cfg = DetectionConfig(sensitivity="balanced")
    print("=" * 80)
    print(f"BALANCED CONFIG THRESHOLDS:")
    print(f"  ZNCC High (present above this): {cfg.zncc_high_thresh}")
    print(f"  ZNCC Low (missing below this):  {cfg.zncc_low_thresh}")
    print(f"  Diff Low (present below this):  {cfg.patch_diff_low_thresh}")
    print(f"  Diff High (missing above this): {cfg.patch_diff_high_thresh}")
    print("=" * 80)

    # 1. Inspect every component in calib_04
    calib_04_meta = gt_data["images"]["calibration/calib_04_all_ok_bright.png"]
    raw_04, _, _ = load_image_with_exif(sample_dir / calib_04_meta["relative_path"])
    ref_norm, test_norm, mask, _ = normalize_to_reference(ref_img, raw_04)
    aligned_04, _, _ = align_test_to_reference(ref_norm, test_norm, mask=mask)

    print("\n--- EXACT SCORES FOR calib_04_all_ok_bright.png (Nominal Full Bbox) ---")
    for cid, cinfo in sorted(components_meta.items()):
        insp = inspect_component(ref_img, aligned_04, cinfo["pixel_bbox"])
        v = classify_component(cid, insp, cfg)
        print(f"  {cid:12s} | ZNCC: {insp['zncc_score']:.4f} | Diff: {insp['patch_diff']:.4f} | Status: {v['status']:9s} | Reason: {v['reason']}")

    # 2. Inspect every component across ALL 20 calibration images with BALANCED config
    print("\n" + "=" * 80)
    print("ALL 20 CALIBRATION IMAGES UNDER BALANCED CONFIG:")
    print("=" * 80)
    
    total_present = 0
    total_missing = 0
    all_scores_present = []
    all_scores_missing = []
    uncertain_list = []
    
    for img_key, meta in sorted(gt_data["images"].items()):
        if meta.get("split") != "calibration":
            continue
        raw_img, _, _ = load_image_with_exif(sample_dir / meta["relative_path"])
        ref_norm, test_norm, mask, _ = normalize_to_reference(ref_img, raw_img)
        aligned, _, _ = align_test_to_reference(ref_norm, test_norm, mask=mask)
        missing_set = set(meta["missing_parts"])

        parts = []
        for cid, cinfo in sorted(components_meta.items()):
            insp = inspect_component(ref_img, aligned, cinfo["pixel_bbox"])
            v = classify_component(cid, insp, cfg)
            parts.append(v)
            is_miss = cid in missing_set
            if is_miss:
                total_missing += 1
                all_scores_missing.append((insp["zncc_score"], insp["patch_diff"], Path(img_key).name, cid))
            else:
                total_present += 1
                all_scores_present.append((insp["zncc_score"], insp["patch_diff"], Path(img_key).name, cid))

            if v["status"] == "UNCERTAIN":
                uncertain_list.append((Path(img_key).name, cid, insp["zncc_score"], insp["patch_diff"], "MISSING" if is_miss else "PRESENT"))

        board_dec = aggregate_board_status(parts)
        exp_status = meta["expected_board_status"]
        act_status = board_dec["board_status"]
        mismatch = " [MISMATCH]" if exp_status != act_status else ""
        print(f"{Path(img_key).name:34s} | Exp: {exp_status:6s} | Act: {act_status:6s} | Missing: {len(board_dec['missing_components'])} | Uncertain: {len(board_dec['uncertain_components'])}{mismatch}")

    all_scores_present.sort(key=lambda x: x[0])
    all_scores_missing.sort(key=lambda x: x[0], reverse=True)

    print("\n--- 10 LOWEST PRESENT ZNCC (All 20 Calib Boards) ---")
    for z, d, img, cid in all_scores_present[:10]:
        print(f"  {img:34s} | {cid:12s} | ZNCC: {z:.4f} | Diff: {d:.4f}")

    print("\n--- 10 HIGHEST MISSING ZNCC (All 20 Calib Boards) ---")
    for z, d, img, cid in all_scores_missing[:10]:
        print(f"  {img:34s} | {cid:12s} | ZNCC: {z:.4f} | Diff: {d:.4f}")

    print(f"\nTOTAL UNCERTAIN CALLS UNDER BALANCED CONFIG: {len(uncertain_list)}")
    for img, cid, z, d, gt_s in uncertain_list:
        print(f"  {img:34s} | {cid:12s} | ZNCC: {z:.4f} | Diff: {d:.4f} | GT: {gt_s}")

    # 3. Analyze LOO on calib_04 to see why LOO flagged R1 and R2
    calib_images = [(k, v) for k, v in sorted(gt_data["images"].items()) if v.get("split") == "calibration"]
    
    # Pre-align
    aligned_boards = {}
    for img_key, meta in calib_images:
        raw_img, _, _ = load_image_with_exif(sample_dir / meta["relative_path"])
        ref_norm, test_norm, mask, _ = normalize_to_reference(ref_img, raw_img)
        aligned, _, _ = align_test_to_reference(ref_norm, test_norm, mask=mask)
        aligned_boards[img_key] = (aligned, set(meta["missing_parts"]), meta["expected_board_status"])

    def extract_split_scores(img_subset):
        pz, mz, pd, md = [], [], [], []
        for img_key, meta in img_subset:
            aligned, missing_set, _ = aligned_boards[img_key]
            for cid, cinfo in components_meta.items():
                insp = inspect_component(ref_img, aligned, cinfo["pixel_bbox"])
                if cid in missing_set:
                    mz.append(insp["zncc_score"])
                    md.append(insp["patch_diff"])
                else:
                    pz.append(insp["zncc_score"])
                    pd.append(insp["patch_diff"])
        return {
            "min_pz": min(pz), "max_mz": max(mz),
            "max_pd": max(pd), "min_md": min(md),
            "mid_z": (min(pz) + max(mz)) / 2.0,
            "mid_d": (max(pd) + min(md)) / 2.0,
        }

    for i, (img_key, meta) in enumerate(calib_images):
        if "calib_04" in img_key:
            train_set = [calib_images[j] for j in range(len(calib_images)) if j != i]
            train_stats = extract_split_scores(train_set)
            z_mid = train_stats["mid_z"]
            d_mid = train_stats["mid_d"]
            loo_cfg = DetectionConfig(
                zncc_high_thresh=z_mid + 0.015,
                zncc_low_thresh=z_mid - 0.015,
                patch_diff_low_thresh=d_mid - 0.015,
                patch_diff_high_thresh=d_mid + 0.015,
                sensitivity="balanced",
            )
            print("\n" + "=" * 80)
            print("LOO CROSS-VALIDATION ON calib_04:")
            print(f"  Training (19 boards) min_pz: {train_stats['min_pz']:.4f}, max_mz: {train_stats['max_mz']:.4f} -> mid_z: {z_mid:.4f}")
            print(f"  Training (19 boards) max_pd: {train_stats['max_pd']:.4f}, min_md: {train_stats['min_md']:.4f} -> mid_d: {d_mid:.4f}")
            print(f"  Dynamic LOO Thresholds: ZNCC [{loo_cfg.zncc_low_thresh:.4f}, {loo_cfg.zncc_high_thresh:.4f}] | Diff [{loo_cfg.patch_diff_low_thresh:.4f}, {loo_cfg.patch_diff_high_thresh:.4f}]")
            print("=" * 80)
            aligned, missing_set, exp_b_status = aligned_boards[img_key]
            for cid in ["R1_PULLUP", "R2_PULLUP"]:
                cinfo = components_meta[cid]
                insp = inspect_component(ref_img, aligned, cinfo["pixel_bbox"])
                v = classify_component(cid, insp, loo_cfg)
                print(f"  {cid:12s} | ZNCC: {insp['zncc_score']:.4f} | Diff: {insp['patch_diff']:.4f} | LOO Status: {v['status']} | LOO Reason: {v['reason']}")

if __name__ == "__main__":
    main()
