import sys
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generate_samples import build_board_image, apply_camera_perturbations, COMPONENTS
from app.core.detector import inspect_component

def compute_zncc_patch(t, p):
    res = cv2.matchTemplate(p.astype(np.float32), t.astype(np.float32), cv2.TM_CCOEFF_NORMED)
    return float(res[0, 0])

def main():
    np.random.seed(42)
    ref_bgr = build_board_image(missing_parts=[])

    # 1. Generate test board with U3 missing, perfectly neutral lighting (gain=1.00, bias=0, glare=None, shift=0)
    raw_u3_miss = build_board_image(missing_parts=["U3_EEPROM"])
    test_u3_neutral = apply_camera_perturbations(raw_u3_miss, dx=0.0, dy=0.0, angle_deg=0.0, gain=1.00, bias=0, glare_points=None, blur_sigma=0.0)

    # 2. Generate test board with U3 missing, extreme gain and bias (gain=1.25, bias=30, glare=None)
    test_u3_bright = apply_camera_perturbations(raw_u3_miss, dx=0.0, dy=0.0, angle_deg=0.0, gain=1.25, bias=30, glare_points=None, blur_sigma=0.0)

    # 3. Generate test board with U3 PRESENT, neutral vs bright
    raw_pres = build_board_image(missing_parts=[])
    test_u3_present_neutral = apply_camera_perturbations(raw_pres, dx=0.0, dy=0.0, angle_deg=0.0, gain=1.00, bias=0, glare_points=None, blur_sigma=0.0)
    test_u3_present_bright = apply_camera_perturbations(raw_pres, dx=0.0, dy=0.0, angle_deg=0.0, gain=1.25, bias=30, glare_points=None, blur_sigma=0.0)

    u3_box = COMPONENTS["U3_EEPROM"]["bbox"]
    print("=" * 80)
    print("PROOF OF ZNCC AFFINE SCALE & OFFSET INVARIANCE:")
    print("=" * 80)

    # Extract raw crops directly to evaluate mathematical ZNCC invariance
    ref_gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    x, y, w, h = u3_box
    t_ref = ref_gray[y:y+h, x:x+w]

    crop_miss_neutral = cv2.cvtColor(test_u3_neutral, cv2.COLOR_BGR2GRAY)[y:y+h, x:x+w]
    crop_miss_bright = cv2.cvtColor(test_u3_bright, cv2.COLOR_BGR2GRAY)[y:y+h, x:x+w]
    crop_pres_neutral = cv2.cvtColor(test_u3_present_neutral, cv2.COLOR_BGR2GRAY)[y:y+h, x:x+w]
    crop_pres_bright = cv2.cvtColor(test_u3_present_bright, cv2.COLOR_BGR2GRAY)[y:y+h, x:x+w]

    zncc_miss_neutral = compute_zncc_patch(t_ref, crop_miss_neutral)
    zncc_miss_bright = compute_zncc_patch(t_ref, crop_miss_bright)
    zncc_pres_neutral = compute_zncc_patch(t_ref, crop_pres_neutral)
    zncc_pres_bright = compute_zncc_patch(t_ref, crop_pres_bright)

    print(f"U3 PRESENT (Neutral 1.0x gain, 0 bias) : ZNCC = {zncc_pres_neutral:.6f}")
    print(f"U3 PRESENT (Bright  1.25x gain, 30 bias): ZNCC = {zncc_pres_bright:.6f}")
    print(f"Difference in Present ZNCC due to gain  : {abs(zncc_pres_neutral - zncc_pres_bright):.6e}")
    print()
    print(f"U3 MISSING (Neutral 1.0x gain, 0 bias) : ZNCC = {zncc_miss_neutral:.6f}")
    print(f"U3 MISSING (Bright  1.25x gain, 30 bias): ZNCC = {zncc_miss_bright:.6f}")
    print(f"Difference in Missing ZNCC due to gain  : {abs(zncc_miss_neutral - zncc_miss_bright):.6e}")

    # Inspect through the full detector pipeline
    print("\n" + "=" * 80)
    print("FULL DETECTOR PIPELINE INSPECTION (U3_EEPROM):")
    print("=" * 80)
    insp_miss_neutral = inspect_component(ref_bgr, test_u3_neutral, u3_box)
    insp_miss_bright = inspect_component(ref_bgr, test_u3_bright, u3_box)
    print(f"Detector Output - U3 MISSING Neutral: ZNCC = {insp_miss_neutral['zncc_score']:.4f}, Diff = {insp_miss_neutral['patch_diff']:.4f}")
    print(f"Detector Output - U3 MISSING Bright : ZNCC = {insp_miss_bright['zncc_score']:.4f}, Diff = {insp_miss_bright['patch_diff']:.4f}")

    # Also check all components when missing on neutral board
    print("\n" + "=" * 80)
    print("EMPTY FOOTPRINT ZNCC UNDER COMPLETELY NEUTRAL LIGHTING FOR ALL COMPONENTS:")
    print("=" * 80)
    for cid, cinfo in sorted(COMPONENTS.items()):
        raw_miss_single = build_board_image(missing_parts=[cid])
        test_missing_single = apply_camera_perturbations(raw_miss_single, dx=0.0, dy=0.0, angle_deg=0.0, gain=1.00, bias=0, glare_points=None, blur_sigma=0.0)
        insp = inspect_component(ref_bgr, test_missing_single, cinfo["bbox"])
        print(f"  {cid:12s} ({cinfo['type']:8s}) | Empty Footprint ZNCC: {insp['zncc_score']:.4f} | Diff: {insp['patch_diff']:.4f}")

if __name__ == "__main__":
    main()
