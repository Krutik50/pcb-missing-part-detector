"""
Three-state classification logic, sensitivity adjustments, and explainable per-part diagnostics.
States: PRESENT (Green), MISSING (Red), UNCERTAIN (Amber / Review).
Board-level status: OK, DEFECT, REVIEW.
"""

from typing import Dict, Any, List, Optional
from app.core.config import DetectionConfig


def classify_component(
    component_name: str,
    inspection_result: Dict[str, Any],
    config: DetectionConfig,
    auto_calib: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Applies multi-metric 3-state decision rules to evaluate a component:
    - PRESENT: High ZNCC (surface pattern match) AND Low Patch Diff (low residual)
    - MISSING: Low ZNCC OR High Patch Diff (bare pad/silkscreen visible)
    - UNCERTAIN: Borderline scores or auto-calibrated variance crossing threshold, requiring human review
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
    auto_calibrated = False
    good_units = 100
    model_name = "Board Architecture"

    if auto_calib:
        max_tilt = auto_calib.get("learned_max_tilt", max_tilt)
        max_shift = auto_calib.get("learned_max_shift", max_shift)
        good_units = auto_calib.get("good_units_count", 100)
        model_name = auto_calib.get("name", "Board Architecture")
        auto_calibrated = auto_calib.get("auto_calibrated", True)

    tilt_deg = inspection_result.get("tilt_deg", 0.0)
    rot_zncc = inspection_result.get("rot_zncc", zncc)
    shift_dist = inspection_result.get("shift_dist_px", 0.0)
    shift_x, shift_y = inspection_result.get("shift_px", (0, 0))

    # Advanced Defect Modes
    is_bridged = inspection_result.get("is_bridged", False)
    is_polarity_reversed = inspection_result.get("is_polarity_reversed", False)
    is_tombstoned = inspection_result.get("is_tombstoned", False)

    effective_zncc = max(zncc, rot_zncc)
    is_tilted_match = (abs(tilt_deg) > max_tilt) and (rot_zncc >= 0.75)

    is_bridge_defect = is_bridged and (effective_zncc >= 0.45)
    is_polarity_defect = is_polarity_reversed
    is_tombstone_defect = is_tombstoned
    is_special_defect = is_bridge_defect or is_polarity_defect or is_tombstone_defect or is_tilted_match

    is_present = ((effective_zncc >= z_high) and (diff <= d_low or rot_zncc >= z_high)) or is_tilted_match
    is_missing = (not is_special_defect) and ((effective_zncc < z_low) or (diff > d_high and rot_zncc < z_high))

    if is_tombstone_defect:
        status = "TOMBSTONED"
        reason = f"Component tombstoned / lifted on end (Termination disparity: {inspection_result.get('tombstone_score', 0):.2f})"
    elif is_polarity_defect:
        status = "POLARITY_REVERSED"
        reason = f"Reversed polarity detected (180° inverted match: {inspection_result.get('polarity_score', 0):.2f})"
    elif is_bridge_defect:
        status = "BRIDGED"
        reason = f"Solder bridge / pin short detected across leads (Bridge ratio: {inspection_result.get('bridge_score', 0):.2f})"
    elif is_missing:
        status = "MISSING"
        if zncc < z_low and diff > d_high:
            reason = f"Surface mismatch & high pad residual (ZNCC: {zncc:.2f} < {z_low:.2f}, Diff: {diff:.2f} > {d_high:.2f})"
        elif zncc < z_low:
            reason = f"Low pattern correlation (ZNCC: {zncc:.2f} < {z_low:.2f})"
        else:
            reason = f"Significant structural deviation (Diff: {diff:.2f} > {d_high:.2f})"
    elif is_present:
        # Evaluate SMT placement tolerances (IPC-A-610 Class 2/3 and Auto-Calibration envelope)
        if abs(tilt_deg) > max_tilt:
            if auto_calibrated:
                status = "UNCERTAIN"  # Automatically routed to human review!
                reason = f"Auto-Calibration Alert: Tilt {tilt_deg:+.1f}° exceeds learned limit (±{max_tilt:.1f}° from {good_units} good {model_name} boards) — marked for human review"
            else:
                status = "TILTED"
                reason = f"Component skewed/tilted by {tilt_deg:+.1f}° (Tolerance limit: ±{max_tilt:.1f}°)"
        elif shift_dist > max_shift:
            if auto_calibrated:
                status = "UNCERTAIN"  # Automatically routed to human review!
                reason = f"Auto-Calibration Alert: Shift {shift_dist:.1f}px exceeds learned limit ({max_shift:.1f}px from {good_units} good {model_name} boards) — marked for human review"
            else:
                status = "MISALIGNED"
                reason = f"Component shifted by {shift_dist:.1f}px (Tolerance limit: {max_shift:.1f}px, dx={shift_x:+.1f}, dy={shift_y:+.1f})"
        else:
            status = "PRESENT"
            if auto_calibrated:
                reason = f"Verified present & aligned within auto-calibrated baseline (ZNCC: {zncc:.2f}, Tilt: {tilt_deg:+.1f}°, Shift: {shift_dist:.1f}px)"
            else:
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
    bridged_parts = [p["name"] for p in component_results if p["status"] == "BRIDGED"]
    polarity_parts = [p["name"] for p in component_results if p["status"] == "POLARITY_REVERSED"]
    tombstoned_parts = [p["name"] for p in component_results if p["status"] == "TOMBSTONED"]
    uncertain_parts = [p["name"] for p in component_results if p["status"] == "UNCERTAIN"]
    present_parts = [p["name"] for p in component_results if p["status"] == "PRESENT"]

    defect_parts = missing_parts + tilted_parts + misaligned_parts + bridged_parts + polarity_parts + tombstoned_parts
    if len(defect_parts) > 0:
        board_status = "DEFECT"
        defect_details = []
        if missing_parts:
            defect_details.append(f"{len(missing_parts)} missing: {', '.join(missing_parts)}")
        if tilted_parts:
            defect_details.append(f"{len(tilted_parts)} tilted: {', '.join(tilted_parts)}")
        if misaligned_parts:
            defect_details.append(f"{len(misaligned_parts)} shifted: {', '.join(misaligned_parts)}")
        if bridged_parts:
            defect_details.append(f"{len(bridged_parts)} bridged: {', '.join(bridged_parts)}")
        if polarity_parts:
            defect_details.append(f"{len(polarity_parts)} reversed polarity: {', '.join(polarity_parts)}")
        if tombstoned_parts:
            defect_details.append(f"{len(tombstoned_parts)} tombstoned: {', '.join(tombstoned_parts)}")
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
            "bridged": len(bridged_parts),
            "polarity_reversed": len(polarity_parts),
            "tombstoned": len(tombstoned_parts),
            "uncertain": len(uncertain_parts),
        },
        "missing_components": missing_parts,
        "tilted_components": tilted_parts,
        "misaligned_components": misaligned_parts,
        "bridged_components": bridged_parts,
        "polarity_reversed_components": polarity_parts,
        "tombstoned_components": tombstoned_parts,
        "uncertain_components": uncertain_parts,
        "present_components": present_parts,
        "parts": component_results,
    }
