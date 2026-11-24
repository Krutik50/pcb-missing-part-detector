"""
FastAPI Backend Application for PCB Missing Component Detector (Task B).
Provides 100% offline REST API endpoints:
- POST /api/reference: Upload and canonicalize golden reference board photo.
- POST /api/sessions/{session_id}/components: Define or update named component bounding boxes.
- POST /api/inspect: Inspect one or more test images against the reference session.
- GET  /api/health: Offline service health check.
- GET  /: Web UI single-page application entrypoint.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, status, Query, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.core.config import DetectionConfig, DEFAULT_CONFIG
from app.core.image_loader import load_image_with_exif, normalize_to_reference
from app.core.aligner import align_test_to_reference
from app.core.detector import inspect_component
from app.core.decision import classify_component, aggregate_board_status
from app.core.dl_verifier import get_dl_verifier
from app.core.auto_calibration import get_auto_calibration_registry

BASE_DIR = Path(__file__).resolve().parent

# Maximum upload size: 25 MB per image
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# In-memory session store: session_id -> session_data
SESSIONS: Dict[str, Dict[str, Any]] = {}

app = FastAPI(
    title="PCB Missing Component Detector API",
    description="Automated Optical Inspection for PCB Missing Components (Task B). 100% Offline.",
    version="0.1.0",
)

# Mount static directory for offline assets (plain HTML, CSS, JS)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Mount sample_data directory for local offline testing and demo access
SAMPLE_DIR = BASE_DIR.parent / "sample_data"
if SAMPLE_DIR.exists():
    app.mount("/sample_data", StaticFiles(directory=str(SAMPLE_DIR)), name="sample_data")

# Mount data directory for multi-board physical datasets and presets
DATA_DIR = BASE_DIR.parent / "data"
if DATA_DIR.exists():
    app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")


class ComponentDef(BaseModel):
    name: str
    bbox: List[float]  # [x, y, w, h] either pixel coordinates or normalized [0..1]
    is_normalized: Optional[bool] = False
    shape_type: Optional[str] = "rectangle"  # "rectangle", "pencil", "polygon"
    polygon: Optional[List[List[float]]] = None  # [[x, y], ...] for non-linear contours


class SetComponentsRequest(BaseModel):
    components: List[ComponentDef]


@app.get("/")
async def get_index():
    """Serve the offline single-page application entrypoint."""
    return FileResponse(str(BASE_DIR / "static" / "index.html"))


@app.get("/api/health")
async def health_check():
    """Health check endpoint confirming offline backend availability."""
    cfg = DEFAULT_CONFIG
    return {
        "status": "healthy",
        "service": "PCB Missing Component Detector",
        "version": "0.1.0",
        "offline": True,
        "max_working_dim": cfg.max_dimension,
        "active_sessions_count": len(SESSIONS),
        "default_thresholds": cfg.get_effective_thresholds(),
    }


@app.get("/api/sample-components")
async def get_sample_components():
    """Returns the canonical component definitions from ground_truth.json for demo / quick load."""
    gt_file = BASE_DIR.parent / "sample_data" / "ground_truth.json"
    if gt_file.exists():
        with open(gt_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"components": data.get("components", {})}
    return {"components": {}}


@app.get("/api/calibration/profiles")
async def get_calibration_profiles():
    """Returns empirical auto-calibrated optical tolerance profiles learned across PCB models."""
    reg = get_auto_calibration_registry()
    return {"profiles": reg.list_profiles()}


def _validate_and_decode_image(file_bytes: bytes, filename: str) -> np.ndarray:
    """Validates file size and decodes into a BGR OpenCV image."""
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File '{filename}' is empty (0 bytes).",
        )
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File '{filename}' exceeds maximum allowed upload limit ({MAX_UPLOAD_BYTES // (1024*1024)} MB).",
        )

    # Decode via OpenCV
    np_buf = np.frombuffer(file_bytes, dtype=np.uint8)
    img = cv2.imdecode(np_buf, cv2.IMREAD_COLOR)

    if img is None or img.size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File '{filename}' is not a valid or readable image. Supported formats: PNG, JPEG, BMP, WebP, TIFF.",
        )
    return img


@app.post("/api/reference")
async def upload_reference_image(file: UploadFile = File(...)):
    """
    Uploads a golden reference board photo:
    - Normalizes EXIF orientation
    - Caps working dimension to 1920 (longest side) while preserving aspect ratio
    - Initializes an in-memory session
    """
    content = await file.read()
    raw_bgr = _validate_and_decode_image(content, file.filename or "reference.png")

    # Load with EXIF handling & canonical 1920 capping
    cfg = DetectionConfig()
    working_bgr, orig_shape, scale_factor = load_image_with_exif(raw_bgr, max_dimension=cfg.max_dimension)

    session_id = uuid.uuid4().hex
    work_h, work_w = working_bgr.shape[:2]

    SESSIONS[session_id] = {
        "ref_image": working_bgr,
        "orig_shape": orig_shape,
        "working_shape": (work_h, work_w),
        "scale_factor": scale_factor,
        "filename": file.filename,
        "components": {},  # name -> {name, pixel_bbox, normalized_bbox}
        "created_at": time.time(),
        "signoffs": {},
        "last_inspection_results": [],
    }

    return {
        "session_id": session_id,
        "filename": file.filename,
        "original_width": orig_shape[1],
        "original_height": orig_shape[0],
        "working_width": work_w,
        "working_height": work_h,
        "scale_factor": round(scale_factor, 4),
        "message": "Reference image uploaded and canonicalized successfully.",
    }


@app.post("/api/sessions/{session_id}/components")
async def set_session_components(session_id: str, payload: SetComponentsRequest):
    """
    Registers or updates the list of named component bounding boxes for a session.
    Accepts coordinates in either pixel space or normalized [0..1] range.
    """
    if session_id not in SESSIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found. Please upload a reference image first.",
        )

    session = SESSIONS[session_id]
    work_h, work_w = session["working_shape"]

    if not payload.components:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one component definition must be provided.",
        )

    registered = {}
    for comp in payload.components:
        name = comp.name.strip()
        if not name:
            continue
        bbox = comp.bbox
        if len(bbox) != 4:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Component '{name}' has invalid bbox. Must be [x, y, width, height].",
            )

        x, y, w, h = bbox
        # Check if coordinates are normalized
        is_norm = comp.is_normalized or (max(x, y, w, h) <= 1.0 and max(w, h) < 1.0)
        if is_norm:
            px_x = int(round(x * work_w))
            px_y = int(round(y * work_h))
            px_w = max(4, int(round(w * work_w)))
            px_h = max(4, int(round(h * work_h)))
        else:
            px_x = int(round(x))
            px_y = int(round(y))
            px_w = max(4, int(round(w)))
            px_h = max(4, int(round(h)))

        # Clamp within working canvas bounds
        px_x = max(0, min(px_x, work_w - 4))
        px_y = max(0, min(px_y, work_h - 4))
        px_w = min(px_w, work_w - px_x)
        px_h = min(px_h, work_h - px_y)

        norm_box = [
            round(px_x / work_w, 4),
            round(px_y / work_h, 4),
            round(px_w / work_w, 4),
            round(px_h / work_h, 4),
        ]

        registered[name] = {
            "name": name,
            "pixel_bbox": [px_x, px_y, px_w, px_h],
            "normalized_bbox": norm_box,
            "shape_type": comp.shape_type or "rectangle",
            "polygon": comp.polygon,
        }

    session["components"] = registered
    return {
        "session_id": session_id,
        "registered_components_count": len(registered),
        "components": registered,
    }


@app.get("/api/sessions/{session_id}")
async def get_session_info(session_id: str):
    """Retrieves metadata and registered component annotations for an active session."""
    if session_id not in SESSIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    s = SESSIONS[session_id]
    return {
        "session_id": session_id,
        "filename": s["filename"],
        "working_shape": s["working_shape"],
        "scale_factor": s["scale_factor"],
        "components_count": len(s["components"]),
        "components": s["components"],
        "created_at": s["created_at"],
    }


@app.post("/api/inspect")
async def inspect_test_images(
    session_id: str = Form(...),
    sensitivity: str = Form("balanced"),
    enable_cascade: bool = Form(True),
    components_json: Optional[str] = Form(None),
    max_tilt_deg: Optional[float] = Form(None),
    max_shift_px: Optional[float] = Form(None),
    test_images: List[UploadFile] = File(...),
):
    """
    Inspects one or more uploaded test images against the golden reference session.
    - Accepts 1, 3, or more than 3 test images.
    - Sensitivity mode: 'balanced' (default), 'strict', or 'lenient'.
    - Returns per-part status, ZNCC score, patch difference, explanation, pixel & normalized boxes,
      rigid alignment metadata, and overall board status (OK, DEFECT, REVIEW).
    """
    if session_id not in SESSIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found or expired. Please upload reference image first.",
        )

    session = SESSIONS[session_id]
    ref_bgr = session["ref_image"]
    work_h, work_w = session["working_shape"]

    # Validate sensitivity
    sens = sensitivity.lower().strip()
    if sens not in ["balanced", "strict", "lenient"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sensitivity '{sensitivity}'. Allowed: 'balanced', 'strict', 'lenient'.",
        )

    # Resolve components
    components_dict = {}
    if components_json and components_json.strip():
        try:
            parsed_raw = json.loads(components_json)
            # Support both list of dicts or dict of dicts
            comp_list = parsed_raw if isinstance(parsed_raw, list) else parsed_raw.values()
            for comp in comp_list:
                cname = comp["name"].strip()
                bbox = comp["bbox"]
                x, y, w, h = bbox
                is_norm = comp.get("is_normalized", False) or (max(x, y, w, h) <= 1.0 and max(w, h) < 1.0)
                if is_norm:
                    px_x = int(round(x * work_w))
                    px_y = int(round(y * work_h))
                    px_w = max(4, int(round(w * work_w)))
                    px_h = max(4, int(round(h * work_h)))
                else:
                    px_x = int(round(x))
                    px_y = int(round(y))
                    px_w = max(4, int(round(w)))
                    px_h = max(4, int(round(h)))

                px_x = max(0, min(px_x, work_w - 4))
                px_y = max(0, min(px_y, work_h - 4))
                px_w = min(px_w, work_w - px_x)
                px_h = min(px_h, work_h - px_y)

                components_dict[cname] = {
                    "name": cname,
                    "pixel_bbox": [px_x, px_y, px_w, px_h],
                    "normalized_bbox": [
                        round(px_x / work_w, 4),
                        round(px_y / work_h, 4),
                        round(px_w / work_w, 4),
                        round(px_h / work_h, 4),
                    ],
                }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse 'components_json': {str(e)}",
            )
    else:
        components_dict = session["components"]

    if not components_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No component bounding boxes provided. Pass 'components_json' or register components on session.",
        )

    if not test_images:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No test images uploaded for inspection.",
        )

    # Initialize configuration reading strictly from DetectionConfig
    cfg = DetectionConfig(sensitivity=sens)
    if max_tilt_deg is not None:
        cfg.max_allowed_tilt_deg = float(max_tilt_deg)
    if max_shift_px is not None:
        cfg.max_allowed_shift_px = float(max_shift_px)
    effective_thresh = cfg.get_effective_thresholds()

    results = []

    for file in test_images:
        fname = file.filename or "unknown.png"
        content = await file.read()

        # Handle invalid or corrupt file without crashing the whole request
        try:
            test_raw = _validate_and_decode_image(content, fname)
        except HTTPException as ex:
            results.append({
                "filename": fname,
                "board_status": "ERROR",
                "summary": f"Image validation failed: {ex.detail}",
                "error": ex.detail,
                "alignment": {
                    "success": False,
                    "fallback_used": True,
                    "dx_px": 0.0,
                    "dy_px": 0.0,
                    "rotation_deg": 0.0,
                    "message": ex.detail,
                },
                "missing_components": [],
                "uncertain_components": [],
                "components": [],
            })
            continue

        try:
            t_start = time.perf_counter()

            # Letterbox and active border mask
            ref_norm, test_norm, mask, _ = normalize_to_reference(ref_bgr, test_raw)

            # Rigid alignment
            aligned_test, warp_mat, align_meta = align_test_to_reference(
                ref_norm,
                test_norm,
                mask=mask,
                motion_type=cfg.alignment_motion_type,
                downscale=cfg.alignment_downscale_factor,
            )

            # Resolve auto-calibrated optical tolerance baseline (e.g. 100-board Arduino Uno profile)
            calib_reg = get_auto_calibration_registry()
            board_hint = session.get("board_model") or fname
            auto_profile = calib_reg.get_profile(board_hint)

            # Inspect each component
            comp_results = []
            for cname, cinfo in sorted(components_dict.items()):
                px_box = cinfo["pixel_bbox"]
                norm_box = cinfo["normalized_bbox"]

                insp = inspect_component(
                    ref_norm,
                    aligned_test,
                    px_box,
                    search_margin_px=cfg.search_margin_px,
                    polygon=cinfo.get("polygon"),
                )

                dec = classify_component(cname, insp, cfg, auto_calib=auto_profile)

                # Stage 2 Deep Learning Triage on Uncertain / Glare / Footprint edge cases
                dl_info = None
                if enable_cascade:
                    dl_v = get_dl_verifier()
                    x, y, w, h = px_box
                    ref_crop = ref_norm[y:y+h, x:x+w]
                    test_crop = aligned_test[y:y+h, x:x+w]
                    has_glare = dl_v.detect_glare_saturation(test_crop)
                    core_check = dl_v.evaluate_package_mold_core(ref_crop, test_crop)
                    is_empty_footprint = (dec["status"] == "PRESENT" and core_check["core_delta_e"] > 35.0 and not has_glare)
                    is_glare_fa = (dec["status"] == "MISSING" and has_glare)

                    if dec["status"] == "UNCERTAIN" or is_empty_footprint or is_glare_fa:
                        dl_res = dl_v.verify(ref_crop, test_crop, insp, component_type=cinfo.get("type", "GENERIC"))
                        dl_info = dl_res
                        if dl_res["status"] != "UNCERTAIN":
                            dec["status"] = dl_res["status"]
                            dec["reason"] = dl_res["reason"]

                comp_dict = {
                    "name": cname,
                    "status": dec["status"],
                    "scores": {
                        "zncc": round(float(insp["zncc_score"]), 4),
                        "patch_diff": round(float(insp["patch_diff"]), 4),
                        "tilt_deg": insp.get("tilt_deg", 0.0),
                        "shift_dist_px": insp.get("shift_dist_px", 0.0),
                    },
                    "reason": dec["reason"],
                    "shape_type": cinfo.get("shape_type", "rectangle"),
                    "polygon": cinfo.get("polygon"),
                    "box": {
                        "pixel": px_box,
                        "normalized": norm_box,
                    },
                }
                if dl_info:
                    comp_dict["dl_triage"] = dl_info

                comp_results.append(comp_dict)

            # Aggregate board status
            b_eval = aggregate_board_status(comp_results)
            board_stat = b_eval["board_status"]
            missing_list = b_eval["missing_components"]
            tilted_list = b_eval.get("tilted_components", [])
            misaligned_list = b_eval.get("misaligned_components", [])
            bridged_list = b_eval.get("bridged_components", [])
            polarity_list = b_eval.get("polarity_reversed_components", [])
            tombstoned_list = b_eval.get("tombstoned_components", [])
            uncertain_list = b_eval["uncertain_components"]

            t_elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 1)

            results.append({
                "filename": fname,
                "board_status": board_stat,
                "summary": b_eval["summary"],
                "elapsed_ms": t_elapsed_ms,
                "alignment": {
                    "success": bool(align_meta["success"]),
                    "fallback_used": bool(align_meta["fallback_used"]),
                    "dx_px": round(float(align_meta["dx_px"]), 2),
                    "dy_px": round(float(align_meta["dy_px"]), 2),
                    "rotation_deg": round(float(align_meta["rotation_deg"]), 2),
                    "message": align_meta.get("fallback_reason") or "EUCLIDEAN alignment succeeded",
                },
                "missing_components": missing_list,
                "tilted_components": tilted_list,
                "misaligned_components": misaligned_list,
                "bridged_components": bridged_list,
                "polarity_reversed_components": polarity_list,
                "tombstoned_components": tombstoned_list,
                "uncertain_components": uncertain_list,
                "components": comp_results,
            })

        except Exception as e:
            # Fallback for unexpected image-processing issues, preventing server crash
            results.append({
                "filename": fname,
                "board_status": "ERROR",
                "summary": f"Unexpected processing error: {str(e)}",
                "error": str(e),
                "alignment": {
                    "success": False,
                    "fallback_used": True,
                    "dx_px": 0.0,
                    "dy_px": 0.0,
                    "rotation_deg": 0.0,
                    "message": "Processing failed",
                },
                "missing_components": [],
                "uncertain_components": [],
                "components": [],
            })

    session["last_inspection_results"] = results

    calib_reg = get_auto_calibration_registry()
    board_hint = session.get("board_model") or (results[0]["filename"] if results else None)
    auto_profile = calib_reg.get_profile(board_hint)

    return {
        "session_id": session_id,
        "sensitivity": sens,
        "thresholds": effective_thresh,
        "total_images_inspected": len(test_images),
        "auto_calibration": {
            "board_model": auto_profile["name"],
            "good_units_count": auto_profile["good_units_count"],
            "learned_max_tilt": auto_profile["learned_max_tilt"],
            "learned_max_shift": auto_profile["learned_max_shift"],
            "status": "AUTO-CALIBRATED",
            "rule": auto_profile["human_review_rule"],
        },
        "results": results,
    }


# --- AUTH & OPERATOR RBAC ---

DEFAULT_OPERATORS = [
    {
        "operator_id": "OP-8402",
        "name": "Sarah Jenkins",
        "role": "INSPECTOR",
        "role_label": "Line Quality Inspector",
        "description": "Routine batch inspection, 3× loupe analysis, verify uncertain calls. Footprint & tolerances locked.",
        "badge": "OP-8402",
        "pin": "1234",
    },
    {
        "operator_id": "LEAD-104",
        "name": "Marcus Vance",
        "role": "SUPERVISOR",
        "role_label": "SMT Process Supervisor",
        "description": "Footprint authoring, recipe save/export, defect overrides, batch release certification.",
        "badge": "LEAD-104",
        "pin": "5678",
    },
    {
        "operator_id": "QA-DIR-01",
        "name": "Dr. Elena Rostova",
        "role": "ADMIN",
        "role_label": "Plant Quality Manager",
        "description": "Full administrative authorization, SMT tolerance tuning, optical reticle alignment, ISO audit logs.",
        "badge": "QA-DIR-01",
        "pin": "9999",
    },
]

class LoginRequest(BaseModel):
    operator_id: str
    name: Optional[str] = None
    role: Optional[str] = "INSPECTOR"
    pin: Optional[str] = None


@app.get("/api/auth/profiles")
async def get_auth_profiles():
    """Returns preset operator profiles for fast demo sign-in."""
    return {"profiles": DEFAULT_OPERATORS}


@app.post("/api/auth/login")
async def operator_login(req: LoginRequest):
    """Logs in an operator and returns authenticated session token."""
    matching = next((u for u in DEFAULT_OPERATORS if u["operator_id"].lower() == req.operator_id.lower()), None)
    if matching:
        user_data = dict(matching)
        if req.name:
            user_data["name"] = req.name
    else:
        user_data = {
            "operator_id": req.operator_id,
            "name": req.name or f"Operator {req.operator_id}",
            "role": req.role or "INSPECTOR",
            "role_label": "Quality Inspector" if req.role == "INSPECTOR" else (req.role or "Operator"),
            "badge": req.operator_id,
        }
    token = f"tok_{uuid.uuid4().hex[:12]}"
    user_data["session_token"] = token
    return {"success": True, "user": user_data}


@app.get("/api/presets")
async def get_physical_presets():
    """
    Returns all 5 real physical board presets from ground_truth_multiboard.json,
    complete with reference image URLs, component boxes, and sample test images.
    """
    gt_file = BASE_DIR.parent / "data" / "multiboard" / "ground_truth_multiboard.json"
    if not gt_file.exists():
        return {"presets": []}

    try:
        with open(gt_file, "r", encoding="utf-8") as f:
            gt_data = json.load(f)
        boards = gt_data.get("boards", {})
        images = gt_data.get("images", {})

        presets = []
        for b_id, b_meta in boards.items():
            comps = []
            for cname, cinfo in b_meta.get("components", {}).items():
                comps.append({
                    "name": cname,
                    "bbox": cinfo["bbox"],
                    "normalized_bbox": cinfo.get("normalized_bbox"),
                    "type": cinfo.get("type", "GENERIC")
                })

            sample_tests = []
            for img_rel, img_info in images.items():
                if img_info.get("board_type") == b_id and img_info.get("split") == "test":
                    fname = Path(img_rel).name
                    sample_tests.append({
                        "name": fname,
                        "url": f"/data/multiboard/{img_rel}",
                        "expected_status": img_info.get("expected_board_status", "OK"),
                        "defects": img_info.get("defects", {})
                    })

            presets.append({
                "id": b_id,
                "name": b_meta.get("name", b_id),
                "tier": b_meta.get("tier", "Standard"),
                "resolution": b_meta.get("resolution", [1024, 1024]),
                "reference_url": f"/data/multiboard/{b_meta['reference_image']}",
                "components": comps,
                "sample_tests": sample_tests
            })
        return {"presets": presets}
    except Exception as e:
        return {"presets": [], "error": str(e)}


# --- RECIPE MANAGEMENT & OPERATOR SIGNOFF ENDPOINTS ---

class SignoffRequest(BaseModel):
    filename: str
    component_name: str
    final_status: str
    operator_id: str
    operator_role: Optional[str] = "INSPECTOR"
    note: Optional[str] = ""


@app.get("/api/sample-recipe")
async def get_sample_recipe():
    """Returns canonical reference board recipe for rapid testing & import."""
    gt_file = BASE_DIR.parent / "sample_data" / "ground_truth.json"
    comps = []
    if gt_file.exists():
        with open(gt_file, "r", encoding="utf-8") as f:
            gt_data = json.load(f)
        for cname, cinfo in gt_data.get("components", {}).items():
            comps.append({
                "name": cname,
                "normalized_bbox": cinfo["normalized_bbox"],
                "type": cinfo.get("type", "GENERIC"),
            })
    return {
        "recipe_version": "1.0",
        "board_name": "PCB_SAMPLE_MAIN_BOARD",
        "image_size": {
            "width": 1920,
            "height": 1080,
            "aspect_ratio": 1.7778,
        },
        "image_fingerprint": "sample_fp_1920_ref",
        "sensitivity": "balanced",
        "components": comps,
    }


@app.post("/api/recipes/validate")
async def validate_recipe(
    recipe: Dict[str, Any],
    expected_width: Optional[int] = Query(None),
    expected_height: Optional[int] = Query(None),
    expected_fingerprint: Optional[str] = Query(None),
):
    """Validates an uploaded or imported PCB inspection recipe."""
    comps = recipe.get("components")
    if not comps or len(comps) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recipe contains zero components. Define at least one component.",
        )

    for comp in comps:
        if "normalized_bbox" in comp:
            nb = comp["normalized_bbox"]
            if any(v < 0.0 or v > 1.0 for v in nb):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Normalized coordinates must be between 0.0 and 1.0",
                )

    dim_mismatch = False
    dim_warning = None
    ar_mismatch = False
    ar_warning = None
    fp_mismatch = False
    fp_warning = None

    img_size = recipe.get("image_size", {})
    rw = img_size.get("width")
    rh = img_size.get("height")

    if expected_width and expected_height and rw and rh:
        if rw != expected_width or rh != expected_height:
            dim_mismatch = True
        r_ar = img_size.get("aspect_ratio") or (rw / rh)
        exp_ar = expected_width / expected_height
        if abs(r_ar - exp_ar) > 0.05:
            ar_mismatch = True
            ar_warning = f"Aspect ratio warning: Recipe AR ({r_ar:.3f}) differs from reference image AR ({exp_ar:.3f})."
            dim_warning = ar_warning

    if expected_fingerprint and recipe.get("image_fingerprint"):
        if recipe["image_fingerprint"] != expected_fingerprint:
            fp_mismatch = True
            fp_warning = f"Reference image fingerprint does not match recipe fingerprint."

    return {
        "valid": True,
        "board_name": recipe.get("board_name", "UNKNOWN"),
        "components_count": len(comps),
        "dimension_mismatch": dim_mismatch,
        "dimension_warning": dim_warning,
        "aspect_ratio_mismatch": ar_mismatch,
        "aspect_ratio_warning": ar_warning,
        "fingerprint_mismatch": fp_mismatch,
        "fingerprint_warning": fp_warning,
        "components": comps,
    }


@app.post("/api/sessions/{session_id}/signoff")
async def record_operator_signoff(session_id: str, signoff: SignoffRequest):
    """Logs human operator manual sign-off on borderline / uncertain parts or supervisor defect overrides."""
    if session_id not in SESSIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    sess = SESSIONS[session_id]
    sess.setdefault("signoffs", {})

    # RBAC Enforcement: Line Inspectors cannot override confirmed defects to PRESENT
    is_inspector = (signoff.operator_role or "").upper() == "INSPECTOR"
    if is_inspector and signoff.final_status == "PRESENT":
        for res in sess.get("last_inspection_results", []):
            if res.get("filename") == signoff.filename:
                for c in res.get("components", []):
                    if c.get("name") == signoff.component_name and c.get("status") in [
                        "MISSING", "TILTED", "MISALIGNED", "BRIDGED", "POLARITY_REVERSED", "TOMBSTONED"
                    ]:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Defect overrides to PRESENT require Supervisor or Admin authorization.",
                        )

    key = f"{signoff.filename}::{signoff.component_name}"
    sess["signoffs"][key] = {
        "filename": signoff.filename,
        "component_name": signoff.component_name,
        "final_status": signoff.final_status,
        "operator_id": signoff.operator_id,
        "operator_role": signoff.operator_role or "INSPECTOR",
        "note": signoff.note,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
    }
    return {"status": "success", "message": "Signoff recorded successfully"}


@app.get("/api/sessions/{session_id}/report.csv")
async def export_inspection_csv(session_id: str):
    """Exports inspection results and operator sign-offs as Monitored Board Logs CSV."""
    if session_id not in SESSIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    sess = SESSIONS[session_id]
    rows = ["Timestamp,Session_ID,Board_Filename,Component,Status,ZNCC,Diff,Operator_ID,Note"]
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    signoffs = sess.get("signoffs", {})
    results = sess.get("last_inspection_results", [])
    for res in results:
        fname = res.get("filename", "unknown.png")
        for comp in res.get("components", []):
            cname = comp["name"]
            stat = comp["status"]
            scores = comp.get("scores", {})
            zncc = scores.get("zncc", 0.0)
            diff = scores.get("patch_diff", 0.0)
            s_key = f"{fname}::{cname}"
            op_id = ""
            note = ""
            if s_key in signoffs:
                sign = signoffs[s_key]
                stat = sign.get("final_status", stat)
                op_id = sign.get("operator_id", "")
                role = sign.get("operator_role", "")
                if role:
                    op_id = f"{op_id} [{role}]"
                note = sign.get("note", "")
            rows.append(f"{ts},{session_id},{fname},{cname},{stat},{zncc:.4f},{diff:.4f},{op_id},{note}")
    csv_content = "\n".join(rows)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=inspection_report_{session_id}.csv"},
    )
