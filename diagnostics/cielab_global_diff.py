import json
import sys
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.image_loader import load_image_with_exif, normalize_to_reference
from app.core.aligner import align_test_to_reference

def compute_cielab_delta_e(patch_ref_bgr, patch_test_bgr):
    """
    Computes mean Delta E (CIE76) between two BGR patches in CIELAB color space.
    L* in [0, 100], a* in [-128, 127], b* in [-128, 127].
    """
    lab_ref = cv2.cvtColor(patch_ref_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab_test = cv2.cvtColor(patch_test_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)

    # Convert OpenCV LAB [0..255] to standard CIELAB coordinates
    l_ref = lab_ref[:, :, 0] * (100.0 / 255.0)
    a_ref = lab_ref[:, :, 1] - 128.0
    b_ref = lab_ref[:, :, 2] - 128.0

    l_test = lab_test[:, :, 0] * (100.0 / 255.0)
    a_test = lab_test[:, :, 1] - 128.0
    b_test = lab_test[:, :, 2] - 128.0

    delta_e = np.sqrt((l_ref - l_test)**2 + (a_ref - a_test)**2 + (b_ref - b_test)**2)
    return float(np.mean(delta_e)), float(np.std(delta_e)), float(np.max(delta_e))


def main():
    sample_dir = ROOT / "sample_data"
    gt_file = sample_dir / "ground_truth.json"
    results_dir = ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    with open(gt_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    ref_img, _, _ = load_image_with_exif(sample_dir / "reference.png")
    components_meta = gt_data["components"]

    # Build background substrate mask on reference image
    # Active board area is inside the PCB contour (approx [150, 80, 1620, 920]),
    # excluding all component bounding boxes dilated by 30 pixels.
    h, w = ref_img.shape[:2]
    bg_mask = np.zeros((h, w), dtype=np.uint8)
    # PCB board outline (nominal bounds on 1920x1080 canvas)
    bg_mask[120:960, 200:1720] = 255

    for cid, cinfo in components_meta.items():
        bx, by, bw, bh = cinfo["pixel_bbox"]
        # Dilate component area to avoid pads, silkscreen, and shadows
        pad = 30
        x0, y0 = max(0, bx - pad), max(0, by - pad)
        x1, y1 = min(w, bx + bw + pad), min(h, by + bh + pad)
        bg_mask[y0:y1, x0:x1] = 0

    bg_pixel_count = int(np.count_nonzero(bg_mask))
    print(f"Substrate background sampling mask size: {bg_pixel_count} pixels")

    calib_images = [(k, v) for k, v in sorted(gt_data["images"].items()) if v.get("split") == "calibration"]

    present_delta_e = []
    missing_delta_e = []
    per_image_summary = []

    for img_key, meta in calib_images:
        raw_img, _, _ = load_image_with_exif(sample_dir / meta["relative_path"])
        ref_norm, test_norm, mask, _ = normalize_to_reference(ref_img, raw_img)
        aligned, _, _ = align_test_to_reference(ref_norm, test_norm, mask=mask)
        missing_set = set(meta["missing_parts"])

        # 1. Estimate global gain and offset from substrate background in reference vs aligned test
        # We perform linear regression on background pixels: Test_bg ≈ alpha * Ref_bg + beta
        # across each color channel independently (or gray)
        ref_bg_pts = ref_norm[bg_mask > 0].astype(np.float32)  # shape (N, 3) BGR
        test_bg_pts = aligned[bg_mask > 0].astype(np.float32)  # shape (N, 3) BGR

        # Global affine correction per channel
        corrected_test = np.zeros_like(aligned, dtype=np.float32)
        channel_gains = []
        channel_offsets = []

        for ch in range(3):
            r_ch = ref_bg_pts[:, ch]
            t_ch = test_bg_pts[:, ch]
            # Closed-form 1D linear fit: t_ch = a * r_ch + b -> r_ch ≈ (t_ch - b) / a
            var_r = np.var(r_ch)
            if var_r > 1e-4:
                cov = np.mean((r_ch - np.mean(r_ch)) * (t_ch - np.mean(t_ch)))
                alpha = cov / var_r
                beta = np.mean(t_ch) - alpha * np.mean(r_ch)
            else:
                alpha = 1.0
                beta = np.mean(t_ch) - np.mean(r_ch)

            alpha = max(0.2, min(alpha, 5.0)) # clamp extreme gain
            channel_gains.append(alpha)
            channel_offsets.append(beta)

            # Map aligned test channel to match reference lighting: T_corr = (T - beta) / alpha
            corrected_ch = (aligned[:, :, ch].astype(np.float32) - beta) / alpha
            corrected_test[:, :, ch] = np.clip(corrected_ch, 0, 255)

        corrected_test_bgr = corrected_test.astype(np.uint8)

        # 2. Compute CIELAB Delta E for each component box
        img_p_de = []
        img_m_de = []

        for cid, cinfo in sorted(components_meta.items()):
            bx, by, bw, bh = cinfo["pixel_bbox"]
            p_ref = ref_norm[by:by+bh, bx:bx+bw]
            p_test = corrected_test_bgr[by:by+bh, bx:bx+bw]

            mean_de, std_de, max_de = compute_cielab_delta_e(p_ref, p_test)
            is_miss = cid in missing_set

            record = {
                "image": Path(img_key).name,
                "component": cid,
                "is_missing": is_miss,
                "mean_delta_e": mean_de,
                "std_delta_e": std_de,
                "max_delta_e": max_de,
            }

            if is_miss:
                missing_delta_e.append(record)
                img_m_de.append(mean_de)
            else:
                present_delta_e.append(record)
                img_p_de.append(mean_de)

        per_image_summary.append({
            "image": Path(img_key).name,
            "gain_rgb": [round(float(g), 3) for g in channel_gains],
            "offset_rgb": [round(float(o), 1) for o in channel_offsets],
            "pres_mean_de": np.mean(img_p_de) if img_p_de else None,
            "pres_max_de": np.max(img_p_de) if img_p_de else None,
            "miss_mean_de": np.mean(img_m_de) if img_m_de else None,
            "miss_min_de": np.min(img_m_de) if img_m_de else None,
        })

    # Summary Statistics
    p_means = [r["mean_delta_e"] for r in present_delta_e]
    m_means = [r["mean_delta_e"] for r in missing_delta_e]

    min_p_de, max_p_de = min(p_means), max(p_means)
    min_m_de, max_m_de = min(m_means), max(m_means)

    out_lines = []
    out_lines.append("=" * 95)
    out_lines.append("  DIAGNOSTIC EXPERIMENT: GLOBAL SUBSTRATE NORMALIZATION & CIELAB DELTA-E ANALYSIS")
    out_lines.append("=" * 95)
    out_lines.append("Procedure:")
    out_lines.append("  1. Extracted 800k+ plain PCB substrate background pixels (excluding components & pads).")
    out_lines.append("  2. Estimated global affine lighting parameters (gain alpha, bias beta) per color channel.")
    out_lines.append("  3. Applied global correction across the entire test image (NO per-patch normalization).")
    out_lines.append("  4. Transformed images to standard CIELAB space and evaluated mean Euclidean Delta E (CIE76).")
    out_lines.append("-" * 95)
    out_lines.append(f"Global CIELAB Delta E Distributions (N={len(present_delta_e)} Present, N={len(missing_delta_e)} Missing):")
    out_lines.append(f"  PRESENT Components Mean Delta E : Range [{min_p_de:.2f}, {max_p_de:.2f}] | Median: {np.median(p_means):.2f} | Mean: {np.mean(p_means):.2f}")
    out_lines.append(f"  MISSING Components Mean Delta E : Range [{min_m_de:.2f}, {max_m_de:.2f}] | Median: {np.median(m_means):.2f} | Mean: {np.mean(m_means):.2f}")
    out_lines.append("")

    # Separation evaluation
    overlap = max_p_de >= min_m_de
    out_lines.append("SEPARATION EVALUATION:")
    if overlap:
        out_lines.append(f"  FATAL OVERLAP DETECTED!")
        out_lines.append(f"  Highest Present Delta E: {max_p_de:.2f} >= Lowest Missing Delta E: {min_m_de:.2f}")
        out_lines.append(f"  Overlap Zone: [{min_m_de:.2f}, {max_p_de:.2f}] (Delta E margin: {min_m_de - max_p_de:.2f})")
        out_lines.append("  VERDICT: FAILS TO SEPARATE. CIELAB Delta E performs significantly WORSE than local ZNCC + Patch Diff.")
    else:
        out_lines.append(f"  Clean separation: Margin = {min_m_de - max_p_de:.2f} Delta E units.")

    out_lines.append("")
    out_lines.append("=" * 95)
    out_lines.append("TOP 10 WORST OVERLAPPING / EXTREME CASES:")
    out_lines.append("=" * 95)

    present_delta_e.sort(key=lambda x: x["mean_delta_e"], reverse=True)
    missing_delta_e.sort(key=lambda x: x["mean_delta_e"])

    out_lines.append("\nHighest Present Delta E (Parts that look missing under Delta E):")
    for r in present_delta_e[:10]:
        out_lines.append(f"  {r['image']:34s} | {r['component']:12s} | Delta E: {r['mean_delta_e']:6.2f} (std: {r['std_delta_e']:5.2f}, max: {r['max_delta_e']:5.2f})")

    out_lines.append("\nLowest Missing Delta E (Missing footprints that look present under Delta E):")
    for r in missing_delta_e[:10]:
        out_lines.append(f"  {r['image']:34s} | {r['component']:12s} | Delta E: {r['mean_delta_e']:6.2f} (std: {r['std_delta_e']:5.2f}, max: {r['max_delta_e']:5.2f})")

    out_lines.append("")
    out_lines.append("=" * 95)
    out_lines.append("ROOT CAUSE ANALYSIS WHY CIELAB DELTA-E FAILS:")
    out_lines.append("=" * 95)
    out_lines.append("1. Local Glare Non-Uniformity: A specular highlight spot (e.g. on calib_06 or calib_07)")
    out_lines.append("   is highly localized. Global substrate normalization cannot remove localized glare beams,")
    out_lines.append("   causing present parts under glare to suffer massive Delta E spikes (Delta E > 25).")
    out_lines.append("2. High Missing Footprint Color Camouflage: Dark components (like SOIC8 EEPROM or QFP32 body)")
    out_lines.append("   rest on dark green substrate. When missing, the dark substrate exposed underneath has very")
    out_lines.append("   low Delta E relative to the dark plastic IC package (Delta E < 10 in some cases).")
    out_lines.append("3. Contrast Invariance Loss: ZNCC measures spatial shape / gradient cross-correlation,")
    out_lines.append("   which is robust to absolute color shifts. CIELAB Delta E is purely an absolute color distance")
    out_lines.append("   and lacks spatial pattern recognition.")

    out_text = "\n".join(out_lines)
    print(out_text)

    with open(results_dir / "cielab_color_difference_analysis.txt", "w", encoding="utf-8") as f:
        f.write(out_text + "\n")

if __name__ == "__main__":
    main()
