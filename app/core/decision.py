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

    # Decision Rule Logic
    is_present = (zncc >= z_high) and (diff <= d_low)
    is_missing = (zncc < z_low) or (diff > d_high)

    if is_present:
        status = "PRESENT"
        reason = f"High confidence match (ZNCC: {zncc:.2f} >= {z_high:.2f}, Diff: {diff:.2f} <= {d_low:.2f})"
    elif is_missing:
        status = "MISSING"
        if zncc < z_low and diff > d_high:
            reason = f"Surface mismatch & high pad residual (ZNCC: {zncc:.2f} < {z_low:.2f}, Diff: {diff:.2f} > {d_high:.2f})"
        elif zncc < z_low:
            reason = f"Low pattern correlation (ZNCC: {zncc:.2f} < {z_low:.2f})"
        else:
            reason = f"Significant structural deviation (Diff: {diff:.2f} > {d_high:.2f})"
    else:
        status = "UNCERTAIN"
        reason = f"Borderline scores (ZNCC: {zncc:.2f}, Diff: {diff:.2f}) - manual visual check recommended"

    return {
        "name": component_name,
        "status": status,
        "zncc_score": zncc,
        "patch_diff": diff,
        "shift_px": inspection_result.get("shift_px", (0, 0)),
        "reason": reason,
        "best_bbox": inspection_result.get("best_bbox"),
        "is_low_texture": inspection_result.get("is_low_texture", False),
    }


def aggregate_board_status(component_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes overall board-level verdict:
    - "DEFECT": If at least one component is MISSING
    - "REVIEW": If no components are MISSING, but at least one is UNCERTAIN
    - "OK": If all components are PRESENT
    """
    missing_parts = [p["name"] for p in component_results if p["status"] == "MISSING"]
    uncertain_parts = [p["name"] for p in component_results if p["status"] == "UNCERTAIN"]
    present_parts = [p["name"] for p in component_results if p["status"] == "PRESENT"]

    if len(missing_parts) > 0:
        board_status = "DEFECT"
        summary_message = f"Defect: {len(missing_parts)} missing part(s) detected: {', '.join(missing_parts)}"
    elif len(uncertain_parts) > 0:
        board_status = "REVIEW"
        summary_message = f"Review needed: {len(uncertain_parts)} borderline part(s): {', '.join(uncertain_parts)}"
    else:
        board_status = "OK"
        summary_message = "All parts present and verified"

    return {
        "board_status": board_status,
        "summary": summary_message,
        "counts": {
            "total": len(component_results),
            "present": len(present_parts),
            "missing": len(missing_parts),
            "uncertain": len(uncertain_parts),
        },
        "missing_components": missing_parts,
        "uncertain_components": uncertain_parts,
        "present_components": present_parts,
        "parts": component_results,
    }
