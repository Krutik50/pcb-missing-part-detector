"""
Local bounded template matching via ZNCC and Normalized Mean Absolute Patch Difference.
Derived strictly from the reference crop without hardcoded pad heuristics.
"""

from typing import Tuple, Dict, Any, List
import cv2
import numpy as np


def estimate_angular_tilt(
    template_gray: np.ndarray,
    search_region_gray: np.ndarray,
    angle_range: float = 12.0,
) -> Tuple[float, float]:
    """
    Estimates the angular tilt / rotation (in degrees) of the component within search_region_gray.
    Matches rotated versions of template_gray across search_region_gray to be invariant to both
    rotation and translation jitter.
    """
    th, tw = template_gray.shape[:2]
    sh, sw = search_region_gray.shape[:2]
    if th < 6 or tw < 6 or sh < th or sw < tw:
        return 0.0, 0.0

    center = (tw / 2.0, th / 2.0)
    best_angle = 0.0
    best_corr = -1.0

    # Coarse pass: 1.0 deg steps
    for a in np.arange(-angle_range, angle_range + 0.5, 1.0):
        M = cv2.getRotationMatrix2D(center, float(a), 1.0)
        rotated_t = cv2.warpAffine(template_gray, M, (tw, th), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        res = cv2.matchTemplate(search_region_gray, rotated_t, cv2.TM_CCOEFF_NORMED)
        min_v, max_v, min_l, max_l = cv2.minMaxLoc(res)
        c_val = float(max_v)
        if c_val > best_corr:
            best_corr = c_val
            best_angle = float(a)

    # Fine pass around best_angle: 0.25 deg steps
    for a in np.arange(best_angle - 1.0, best_angle + 1.25, 0.25):
        if abs(a) > angle_range:
            continue
        M = cv2.getRotationMatrix2D(center, float(a), 1.0)
        rotated_t = cv2.warpAffine(template_gray, M, (tw, th), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        res = cv2.matchTemplate(search_region_gray, rotated_t, cv2.TM_CCOEFF_NORMED)
        min_v, max_v, min_l, max_l = cv2.minMaxLoc(res)
        c_val = float(max_v)
        if c_val > best_corr:
            best_corr = c_val
            best_angle = float(a)

    return round(best_angle, 2), round(best_corr, 4)


def inspect_component(
    ref_img: np.ndarray,
    aligned_test_img: np.ndarray,
    bbox: List[int],
    search_margin_px: int = 16,
    polygon: Any = None,
) -> Dict[str, Any]:
    """
    Evaluates a single component site:
    1. Extracts reference template T_ref at bbox [x, y, w, h].
    2. Searches a localized window in aligned_test_img (x ± margin, y ± margin)
       using Zero-mean Normalized Cross-Correlation (cv2.TM_CCOEFF_NORMED).
    3. Finds best-matching candidate location and peak ZNCC correlation score.
    4. Computes Normalized Mean Absolute Difference (L1 patch residual) after
       local mean-illumination adjustment.

    Returns:
        Dictionary with zncc_score, patch_diff, best_bbox, displacement_px, and diagnostics.
    """
    ref_h, ref_w = ref_img.shape[:2]
    test_h, test_w = aligned_test_img.shape[:2]

    x, y, w, h = bbox
    # Ensure bounding box is within reference boundaries
    x = max(0, min(x, ref_w - 1))
    y = max(0, min(y, ref_h - 1))
    w = max(4, min(w, ref_w - x))
    h = max(4, min(h, ref_h - y))

    # Crop reference template
    template_bgr = ref_img[y:y + h, x:x + w]
    template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY) if template_bgr.ndim == 3 else template_bgr

    # Define localized search window in test image
    pad = search_margin_px
    x_min = max(0, x - pad)
    y_min = max(0, y - pad)
    x_max = min(test_w, x + w + pad)
    y_max = min(test_h, y + h + pad)

    search_region_bgr = aligned_test_img[y_min:y_max, x_min:x_max]
    search_region_gray = cv2.cvtColor(search_region_bgr, cv2.COLOR_BGR2GRAY) if search_region_bgr.ndim == 3 else search_region_bgr

    # Search window must be strictly larger than or equal to template
    s_h, s_w = search_region_gray.shape[:2]
    if s_h < h or s_w < w:
        # Boundary fallback: directly compare co-located patch
        candidate_gray = search_region_gray[:min(s_h, h), :min(s_w, w)]
        t_crop = template_gray[:candidate_gray.shape[0], :candidate_gray.shape[1]]
        diff = float(np.mean(np.abs(t_crop.astype(np.float32) - candidate_gray.astype(np.float32))) / 255.0)
        return {
            "zncc_score": 0.0,
            "patch_diff": diff,
            "best_bbox": [x, y, w, h],
            "shift_px": (0, 0),
            "template_shape": (w, h),
        }

    # Check for empty/flat ROI warning (standard deviation)
    std_t = float(np.std(template_gray))
    is_low_texture = std_t < 10.0

    # If template has virtually zero variance, ZNCC denominator is 0 (undefined in OpenCV)
    if std_t < 1.0:
        c_crop = search_region_gray[y - y_min:y - y_min + h, x - x_min:x - x_min + w]
        if c_crop.shape == template_gray.shape:
            diff = float(np.mean(np.abs(template_gray.astype(np.float32) - c_crop.astype(np.float32))) / 255.0)
        else:
            diff = 1.0
        return {
            "zncc_score": 0.0,
            "patch_diff": round(diff, 4),
            "best_bbox": [x, y, w, h],
            "shift_px": (0, 0),
            "is_low_texture": True,
            "template_std": round(std_t, 2),
        }

    # Step 1: Zero-mean Normalized Cross-Correlation (ZNCC)
    match_map = cv2.matchTemplate(search_region_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(match_map)

    peak_zncc = float(max_val)
    best_x_local, best_y_local = max_loc

    # Global coordinates of candidate match in aligned test image
    match_x = x_min + best_x_local
    match_y = y_min + best_y_local
    shift_x = match_x - x
    shift_y = match_y - y

    # Crop matched patch from test image
    candidate_gray = search_region_gray[best_y_local:best_y_local + h, best_x_local:best_x_local + w]

    # Step 2: Illumination-Compensated Mean Absolute Patch Difference
    # Cancels uniform lighting offset between reference crop and test patch
    t_f = template_gray.astype(np.float32)
    c_f = candidate_gray.astype(np.float32)

    # Adjust candidate to match template's mean intensity
    mean_t = float(np.mean(t_f))
    mean_c = float(np.mean(c_f))
    c_adjusted = c_f - mean_c + mean_t

    # L1 residual normalized to [0.0, 1.0] (masked if non-linear polygon provided)
    if polygon and len(polygon) >= 3:
        mask = np.zeros((h, w), dtype=np.uint8)
        local_pts = np.array([[int(round(p[0] - x)), int(round(p[1] - y))] for p in polygon], dtype=np.int32)
        cv2.fillPoly(mask, [local_pts], 255)
        if np.count_nonzero(mask) > 10:
            diff_map = np.abs(t_f - c_adjusted)
            patch_diff = float(np.mean(diff_map[mask > 0]) / 255.0)
        else:
            patch_diff = float(np.mean(np.abs(t_f - c_adjusted)) / 255.0)
    else:
        patch_diff = float(np.mean(np.abs(t_f - c_adjusted)) / 255.0)

    # Check for empty/flat ROI warning (standard deviation)
    std_t = float(np.std(t_f))
    is_low_texture = std_t < 10.0

    # Step 3: Sub-pixel Rotational Tilt & Placement Displacement Estimation
    tilt_deg = 0.0
    rot_zncc = peak_zncc
    if not is_low_texture and (peak_zncc >= 0.50 or s_h >= h):
        tilt_deg, rot_zncc = estimate_angular_tilt(template_gray, search_region_gray)

    shift_dist_px = round(float(np.sqrt(shift_x**2 + shift_y**2)), 2)

    # Step 4: Advanced SMT Defect Analyzers (Bridge, Polarity, Tombstone)
    is_bridged, bridge_score = check_solder_bridge(template_gray, candidate_gray)
    is_polarity_reversed, polarity_score = check_polarity_inversion(template_gray, search_region_gray, peak_zncc, tilt_deg)
    is_tombstoned, tombstone_score = check_tombstone(template_gray, candidate_gray, peak_zncc, patch_diff)

    return {
        "zncc_score": round(peak_zncc, 4),
        "patch_diff": round(patch_diff, 4),
        "best_bbox": [match_x, match_y, w, h],
        "shift_px": (shift_x, shift_y),
        "shift_dist_px": shift_dist_px,
        "tilt_deg": tilt_deg,
        "rot_zncc": rot_zncc,
        "is_bridged": is_bridged,
        "bridge_score": bridge_score,
        "is_polarity_reversed": is_polarity_reversed,
        "polarity_score": polarity_score,
        "is_tombstoned": is_tombstoned,
        "tombstone_score": tombstone_score,
        "is_low_texture": is_low_texture,
        "template_std": round(std_t, 2),
    }


def check_solder_bridge(template_gray: np.ndarray, candidate_gray: np.ndarray) -> Tuple[bool, float]:
    """
    Detects solder bridges (conductive shorts across adjacent IC pins or dual pads).
    Compares the interstitial lead gap intensities. In a bridged component, the normally
    dark substrate gap between pins is filled with high-reflectance tin/lead solder.
    """
    if template_gray.shape != candidate_gray.shape:
        candidate_gray = cv2.resize(candidate_gray, (template_gray.shape[1], template_gray.shape[0]))
    th, tw = template_gray.shape[:2]
    if th < 10 or tw < 10:
        return False, 0.0

    # Lead perimeter zone: check top 25% and bottom 25% rows (or left/right 25% cols)
    top_t = template_gray[:th // 4, :]
    top_c = candidate_gray[:th // 4, :]
    bot_t = template_gray[th - th // 4:, :]
    bot_c = candidate_gray[th - th // 4:, :]

    # Threshold for shiny solder in interstitial gap where template was dark
    bridge_mask_top = (top_c > 145) & (top_t < 90)
    bridge_mask_bot = (bot_c > 145) & (bot_t < 90)

    ratio_top = float(np.sum(bridge_mask_top)) / max(1, top_t.size)
    ratio_bot = float(np.sum(bridge_mask_bot)) / max(1, bot_t.size)
    max_bridge_ratio = max(ratio_top, ratio_bot)

    is_bridged = max_bridge_ratio >= 0.08
    return is_bridged, round(max_bridge_ratio, 3)


def check_polarity_inversion(
    template_gray: np.ndarray,
    search_region_gray: np.ndarray,
    peak_zncc: float,
    tilt_deg: float
) -> Tuple[bool, float]:
    """
    Detects 180° inverted placement for polarized parts (diodes, electrolytic caps, IC pin 1).
    Matches an inverted 180° template; if 180° correlation is significantly higher than
    unrotated 0° correlation on an asymmetric component, flags as POLARITY_REVERSED.
    """
    th, tw = template_gray.shape[:2]
    sh, sw = search_region_gray.shape[:2]
    if th < 8 or tw < 8 or sh < th or sw < tw:
        return False, 0.0

    t_180 = cv2.rotate(template_gray, cv2.ROTATE_180)
    res_180 = cv2.matchTemplate(search_region_gray, t_180, cv2.TM_CCOEFF_NORMED)
    _, max_val_180, _, _ = cv2.minMaxLoc(res_180)
    score_180 = float(max_val_180)

    # Inverted match must be strong AND higher than 0° match, within small rotation
    is_rev = (score_180 >= 0.78) and (score_180 > peak_zncc + 0.07) and (abs(tilt_deg) < 12.0)
    return is_rev, round(score_180, 4)


def check_tombstone(
    template_gray: np.ndarray,
    candidate_gray: np.ndarray,
    peak_zncc: float,
    patch_diff: float
) -> Tuple[bool, float]:
    """
    Detects tombstoning / billboarding on two-terminal passive chips (resistors, caps).
    Measures termination disparity: one termination pad is bare/detached (high difference),
    while the other end has the vertically lifted chip body.
    """
    if template_gray.shape != candidate_gray.shape:
        candidate_gray = cv2.resize(candidate_gray, (template_gray.shape[1], template_gray.shape[0]))
    th, tw = template_gray.shape[:2]
    if th < 6 or tw < 6:
        return False, 0.0

    # Split along major dimension
    if tw >= th:
        half = tw // 2
        t1, c1 = template_gray[:, :half], candidate_gray[:, :half]
        t2, c2 = template_gray[:, half:], candidate_gray[:, half:]
    else:
        half = th // 2
        t1, c1 = template_gray[:half, :], candidate_gray[:half, :]
        t2, c2 = template_gray[half:, :], candidate_gray[half:, :]

    d1 = float(np.mean(np.abs(t1.astype(np.float32) - c1.astype(np.float32))) / 255.0)
    d2 = float(np.mean(np.abs(t2.astype(np.float32) - c2.astype(np.float32))) / 255.0)
    disparity = abs(d1 - d2)

    # One side must have high bare pad residual, while the disparity is significant
    is_tomb = (disparity >= 0.12) and (max(d1, d2) >= 0.16) and (peak_zncc < 0.80) and (patch_diff > 0.08)
    return is_tomb, round(disparity, 3)
