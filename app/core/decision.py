"""
Three-state classification logic, sensitivity adjustments, and explainable per-part diagnostics.
States: PRESENT (Green), MISSING (Red), UNCERTAIN (Amber / Review).
Board-level status: OK, DEFECT, REVIEW.
"""

from typing import Dict, Any, List
from app.core.config import DetectionConfig


def classify_component(
    component_name: str,
    inspection_result: Dict[str, Any],
    config: DetectionConfig,
) -> Dict[str, Any]:
    """
    Applies multi-metric 3-state decision rules to evaluate a component:
    - PRESENT: High ZNCC (surface pattern match) AND Low Patch Diff (low residual)
    - MISSING: Low ZNCC OR High Patch Diff (bare pad/silkscreen visible)
    - UNCERTAIN: Borderline scores requiring operator review

    Returns:
        Structured result with status, scores, and human-readable diagnostic reason.
    """
    zncc = inspection_result["zncc_score"]
    diff = inspection_result["patch_diff"]
    thresholds = config.get_effective_thresholds()

    z_high = thresholds["zncc_high"]
    z_low = thresholds["zncc_low"]
    d_low = thresholds["diff_low"]
    d_high = thresholds["diff_high"]
    max_tilt = thresholds.get("max_allowed_tilt_deg", 3.5)
    max_shift = thresholds.get("max_allowed_shift_px", 5.0)

    tilt_deg = inspection_result.get("tilt_deg", 0.0)
    rot_zncc = inspection_result.get("rot_zncc", zncc)
    shift_dist = inspection_result.get("shift_dist_px", 0.0)
    shift_x, shift_y = inspection_result.get("shift_px", (0, 0))

    # Decision Rule Logic (Presence verified by nominal or rotated pattern match)
    is_tilted_match = (abs(tilt_deg) > max_tilt) and (rot_zncc >= 0.75)
    effective_zncc = max(zncc, rot_zncc)
    is_present = ((effective_zncc >= z_high) and (diff <= d_low or rot_zncc >= z_high)) or is_tilted_match
    is_missing = (not is_tilted_match) and ((effective_zncc < z_low) or (diff > d_high and rot_zncc < z_high))

    if is_missing:
        status = "MISSING"
        if zncc < z_low and diff > d_high:
            reason = f"Surface mismatch & high pad residual (ZNCC: {zncc:.2f} < {z_low:.2f}, Diff: {diff:.2f} > {d_high:.2f})"
        elif zncc < z_low:
            reason = f"Low pattern correlation (ZNCC: {zncc:.2f} < {z_low:.2f})"
        else:
            reason = f"Significant structural deviation (Diff: {diff:.2f} > {d_high:.2f})"
    elif is_present:
        # Evaluate SMT placement tolerances (IPC-A-610 Class 2/3)
        if abs(tilt_deg) > max_tilt:
            status = "TILTED"
            reason = f"Component skewed/tilted by {tilt_deg:+.1f}° (Tolerance limit: ±{max_tilt:.1f}°)"
        elif shift_dist > max_shift:
            status = "MISALIGNED"
            reason = f"Component shifted by {shift_dist:.1f}px (Tolerance limit: {max_shift:.1f}px, dx={shift_x:+.1f}, dy={shift_y:+.1f})"
        else:
            status = "PRESENT"
            reason = f"Verified present & aligned (ZNCC: {zncc:.2f}, Tilt: {tilt_deg:+.1f}°, Shift: {shift_dist:.1f}px)"
    else:
        status = "UNCERTAIN"
        reason = f"Borderline scores (ZNCC: {zncc:.2f}, Diff: {diff:.2f}) - manual visual check recommended"

    return {
        "name": component_name,
        "status": status,
        "zncc_score": zncc,
        "patch_diff": diff,
        "shift_px": (shift_x, shift_y),
        "shift_dist_px": shift_dist,
        "tilt_deg": tilt_deg,
        "reason": reason,
        "best_bbox": inspection_result.get("best_bbox"),
        "is_low_texture": inspection_result.get("is_low_texture", False),
    }


def aggregate_board_status(component_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes overall board-level verdict:
    - "DEFECT": If at least one component is MISSING, TILTED, or MISALIGNED
    - "REVIEW": If no components are defective, but at least one is UNCERTAIN
    - "OK": If all components are PRESENT and aligned within tolerance
    """
    missing_parts = [p["name"] for p in component_results if p["status"] == "MISSING"]
    tilted_parts = [p["name"] for p in component_results if p["status"] == "TILTED"]
    misaligned_parts = [p["name"] for p in component_results if p["status"] == "MISALIGNED"]
    uncertain_parts = [p["name"] for p in component_results if p["status"] == "UNCERTAIN"]
    present_parts = [p["name"] for p in component_results if p["status"] == "PRESENT"]

    defect_parts = missing_parts + tilted_parts + misaligned_parts
    if len(defect_parts) > 0:
        board_status = "DEFECT"
        defect_details = []
        if missing_parts:
            defect_details.append(f"{len(missing_parts)} missing: {', '.join(missing_parts)}")
        if tilted_parts:
            defect_details.append(f"{len(tilted_parts)} tilted: {', '.join(tilted_parts)}")
        if misaligned_parts:
            defect_details.append(f"{len(misaligned_parts)} shifted: {', '.join(misaligned_parts)}")
        summary_message = f"Defect detected: {'; '.join(defect_details)}"
    elif len(uncertain_parts) > 0:
        board_status = "REVIEW"
        summary_message = f"Review needed: {len(uncertain_parts)} borderline part(s): {', '.join(uncertain_parts)}"
    else:
        board_status = "OK"
        summary_message = "All parts present and aligned within tolerance"

    return {
        "board_status": board_status,
        "summary": summary_message,
        "counts": {
            "total": len(component_results),
            "present": len(present_parts),
            "missing": len(missing_parts),
            "tilted": len(tilted_parts),
            "misaligned": len(misaligned_parts),
            "uncertain": len(uncertain_parts),
        },
        "missing_components": missing_parts,
        "tilted_components": tilted_parts,
        "misaligned_components": misaligned_parts,
        "uncertain_components": uncertain_parts,
        "present_components": present_parts,
        "parts": component_results,
    }
