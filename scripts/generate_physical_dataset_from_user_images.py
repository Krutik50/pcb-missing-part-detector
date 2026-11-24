"""
Multi-Board Physical PCB Dataset Generator
Constructs a full 70-board dataset (70:30 Train-Test split) directly from real
physical hardware photographs provided by the user:
  1. Arduino Uno R3 DIP Microcontroller (Official blue PCB, socketed DIP28 MCU)
  2. Phenolic Appliance AC Control Board (Yellow-tan FR-2, dual 400V bulk caps, toroid, relays)
  3. Industrial Weighing Scale Controller PMS-63 (Green PCB, DIP28 MCU, heatsink, orange caps)
  4. Analog Signal Conditioning Board (Green PCB, 4 precision trimpots, DIP14/DIP8, film caps)
  5. Inverter Power & SMPS Board (Green PCB, 3 vented bulk electrolytic caps, transformer)
"""

import json
import random
from pathlib import Path
import cv2
import numpy as np

def apply_illumination(image, mode):
    img = image.copy()
    if mode == "nominal_ok":
        return img
    elif mode == "bright":
        table = np.array([min(255, int(i * 1.15)) for i in range(256)], dtype=np.uint8)
        return cv2.LUT(img, table)
    elif mode == "dim":
        table = np.array([int(i * 0.82) for i in range(256)], dtype=np.uint8)
        return cv2.LUT(img, table)
    elif mode == "glare":
        h, w = img.shape[:2]
        cx, cy = w // 2 + random.randint(-40, 40), h // 2 + random.randint(-40, 40)
        radius = min(w, h) // 4
        y, x = np.ogrid[:h, :w]
        dist_sq = (x - cx) ** 2 + (y - cy) ** 2
        glare_mask = np.exp(-dist_sq / (2.0 * (radius ** 2)))
        glare_mask = (glare_mask * 75).astype(np.uint8)
        glare_bgr = cv2.merge([glare_mask, glare_mask, glare_mask])
        return cv2.add(img, glare_bgr)
    return img

def render_missing_component(image, bbox, comp_type):
    """
    Renders realistic bare desoldered PCB substrate and exposed solder pads
    at the component footprint location.
    """
    img = image.copy()
    x, y, w, h = bbox
    img_h, img_w = img.shape[:2]

    # Sample local substrate color from border
    margin = 8
    y0 = max(0, y - margin)
    y1 = min(img_h, y + h + margin)
    x0 = max(0, x - margin)
    x1 = min(img_w, x + w + margin)

    border_samples = []
    if y > margin:
        border_samples.append(img[y0:y, x:x+w].reshape(-1, 3))
    if y + h + margin < img_h:
        border_samples.append(img[y+h:y1, x:x+w].reshape(-1, 3))
    if x > margin:
        border_samples.append(img[y:y+h, x0:x].reshape(-1, 3))
    if x + w + margin < img_w:
        border_samples.append(img[y:y+h, x+w:x1].reshape(-1, 3))

    if border_samples:
        substrate_color = np.median(np.vstack(border_samples), axis=0).astype(np.uint8)
    else:
        substrate_color = np.array([35, 100, 35], dtype=np.uint8)

    # Inpaint interior with bare substrate
    img[y:y+h, x:x+w] = substrate_color

    # Add realistic subtle substrate grain
    noise = np.random.normal(0, 3.5, (h, w, 3)).astype(np.int16)
    patch = np.clip(img[y:y+h, x:x+w].astype(np.int16) + noise, 0, 255).astype(np.uint8)
    img[y:y+h, x:x+w] = patch

    # Draw silkscreen component outline border (white/light-yellow)
    cv2.rectangle(img, (x + 2, y + 2), (x + w - 2, y + h - 2), (210, 215, 215), 1)

    # Draw exposed tin/copper solder pads according to package type
    pad_color = (190, 195, 195)
    hole_color = (25, 25, 25)

    if "DIP" in comp_type or "SOIC" in comp_type:
        num_pins = 14 if "DIP28" in comp_type else (7 if "DIP14" in comp_type else 4)
        pad_pitch = w / (num_pins + 1)
        r = max(2, min(5, h // 12))
        for i in range(1, num_pins + 1):
            px = int(x + i * pad_pitch)
            py1 = int(y + r + 3)
            py2 = int(y + h - r - 3)
            cv2.circle(img, (px, py1), r + 2, pad_color, -1)
            cv2.circle(img, (px, py1), r - 1, hole_color, -1)
            cv2.circle(img, (px, py2), r + 2, pad_color, -1)
            cv2.circle(img, (px, py2), r - 1, hole_color, -1)
    elif "CAP" in comp_type or "ELECTRO" in comp_type:
        # Dual circular through-hole pads for electrolytic capacitor
        cx, cy = x + w // 2, y + h // 2
        r = max(3, min(8, min(w, h) // 8))
        d = min(w, h) // 4
        # Positive pad with '+'
        cv2.circle(img, (cx - d, cy), r + 2, pad_color, -1)
        cv2.circle(img, (cx - d, cy), r - 1, hole_color, -1)
        # Negative pad
        cv2.circle(img, (cx + d, cy), r + 2, pad_color, -1)
        cv2.circle(img, (cx + d, cy), r - 1, hole_color, -1)
        # Silkscreen polarity circle
        cv2.circle(img, (cx, cy), min(w, h) // 2 - 3, (215, 220, 220), 1)
    elif "TRIMPOT" in comp_type:
        # 3 through-hole pads in triangle
        cx, cy = x + w // 2, y + h // 2
        r = max(2, min(5, w // 7))
        cv2.circle(img, (cx - w // 4, cy - h // 4), r + 2, pad_color, -1)
        cv2.circle(img, (cx - w // 4, cy - h // 4), r - 1, hole_color, -1)
        cv2.circle(img, (cx + w // 4, cy - h // 4), r + 2, pad_color, -1)
        cv2.circle(img, (cx + w // 4, cy - h // 4), r - 1, hole_color, -1)
        cv2.circle(img, (cx, cy + h // 4), r + 2, pad_color, -1)
        cv2.circle(img, (cx, cy + h // 4), r - 1, hole_color, -1)
    else:
        # Generic terminal pads at corners
        r = max(2, min(5, min(w, h) // 10))
        for px, py in [(x + 6, y + 6), (x + w - 6, y + 6), (x + 6, y + h - 6), (x + w - 6, y + h - 6)]:
            cv2.circle(img, (px, py), r + 2, pad_color, -1)
            cv2.circle(img, (px, py), r - 1, hole_color, -1)

    return img

def render_tilted_component(image, bbox, angle_deg, comp_type):
    """
    Rotates the real physical component about its center by angle_deg.
    """
    img = image.copy()
    x, y, w, h = bbox
    crop = image[y:y+h, x:x+w].copy()

    # Inpaint background with substrate so edges don't smear
    cleared = render_missing_component(img, bbox, comp_type)

    center = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    rot_crop = cv2.warpAffine(crop, M, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))

    # Alpha mask for rotated component
    gray = cv2.cvtColor(rot_crop, cv2.COLOR_BGR2GRAY)
    mask = (gray > 5).astype(np.float32)[:, :, np.newaxis]

    bg_patch = cleared[y:y+h, x:x+w].astype(np.float32)
    fg_patch = rot_crop.astype(np.float32)
    blended = (fg_patch * mask + bg_patch * (1.0 - mask)).astype(np.uint8)

    cleared[y:y+h, x:x+w] = blended
    return cleared

def render_shifted_component(image, bbox, dx, dy, comp_type):
    """
    Displaces the physical component by (dx, dy) pixels.
    """
    img = image.copy()
    x, y, w, h = bbox
    crop = image[y:y+h, x:x+w].copy()

    cleared = render_missing_component(img, bbox, comp_type)
    sx = int(x + dx)
    sy = int(y + dy)
    img_h, img_w = img.shape[:2]

    if 0 <= sx and sx + w <= img_w and 0 <= sy and sy + h <= img_h:
        cleared[sy:sy+h, sx:sx+w] = crop

    return cleared

def apply_spatial_jitter(image, max_jitter_px=4):
    """
    Applies small shop-floor camera positioning jitter.
    """
    h, w = image.shape[:2]
    dx = random.uniform(-max_jitter_px, max_jitter_px)
    dy = random.uniform(-max_jitter_px, max_jitter_px)
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(image, M, (w, h), borderMode=cv2.BORDER_REFLECT)


def generate_physical_multiboard_dataset():
    root = Path(__file__).resolve().parent.parent
    src_dir = root / "sample_data" / "user_physical_boards"
    out_dir = root / "data" / "multiboard"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "train").mkdir(exist_ok=True)
    (out_dir / "test").mkdir(exist_ok=True)

    # 5 Real Physical Board Classes
    board_configs = {
        "arduino_uno_dip": {
            "name": "Official Arduino Uno R3 Physical MCU Board (Socketed DIP28)",
            "source_image": "01_arduino_uno_dip.jpg",
            "tier": "Tier 2 (Medium Microcontroller)",
            "components": {
                "U1_ATMEGA328_DIP": {"bbox": [485, 575, 450, 115], "type": "DIP28_MCU"},
                "J1_USB_PORT": {"bbox": [38, 280, 240, 160], "type": "USB_TYPE_B"},
                "J2_DC_JACK": {"bbox": [92, 680, 200, 120], "type": "DC_BARREL_JACK"},
                "SW1_RESET_BTN": {"bbox": [150, 190, 100, 85], "type": "TACTILE_SWITCH"},
                "C1_47UF_ALUM": {"bbox": [310, 685, 80, 80], "type": "SMD_ELECTRO_CAP"},
                "C2_47UF_ALUM": {"bbox": [395, 685, 80, 80], "type": "SMD_ELECTRO_CAP"},
                "Y1_16MHZ_XTAL": {"bbox": [300, 488, 135, 60], "type": "HC49S_CRYSTAL"},
                "U2_ATMEGA16U2": {"bbox": [340, 380, 75, 75], "type": "QFN32_USB_IC"},
                "VR1_AMS1117": {"bbox": [170, 595, 80, 70], "type": "SOT223_LDO"},
            }
        },
        "phenolic_appliance_board": {
            "name": "Appliance AC Power & Control Board (Yellow Phenolic FR-2)",
            "source_image": "02_phenolic_appliance_board.jpg",
            "tier": "Tier 1 (High-Voltage Power Supply)",
            "components": {
                "C1_400V_BULK": {"bbox": [260, 0, 130, 185], "type": "RADIAL_400V_CAP"},
                "C2_400V_BULK": {"bbox": [380, 0, 120, 185], "type": "RADIAL_400V_CAP"},
                "L1_TOROID_COIL": {"bbox": [560, 70, 130, 130], "type": "TOROIDAL_INDUCTOR"},
                "K1_POWER_RELAY": {"bbox": [535, 190, 200, 155], "type": "POWER_RELAY"},
                "K2_RELAY_BLOCK": {"bbox": [750, 25, 140, 290], "type": "HV_RELAY_MODULE"},
                "U103_DIP8": {"bbox": [280, 520, 60, 60], "type": "DIP8_POWER_IC"},
                "MOV_Y1_BLUE": {"bbox": [425, 335, 55, 45], "type": "BLUE_DISC_MOV"},
                "CONN_WHITE_HDR": {"bbox": [775, 545, 105, 125], "type": "TERMINAL_HEADER"},
            }
        },
        "industrial_weighing_pms63": {
            "name": "Industrial Weighing Scale Indicator Controller (PMS-63)",
            "source_image": "03_industrial_weighing_pms63.jpg",
            "tier": "Tier 2 (Industrial Mixed-Signal Controller)",
            "components": {
                "U1_MCU_DIP28": {"bbox": [170, 75, 65, 205], "type": "DIP28_MCU"},
                "U2_OPAMP_DIP8": {"bbox": [60, 255, 60, 60], "type": "DIP8_OPAMP"},
                "Q8_HEATSINK": {"bbox": [340, 230, 110, 80], "type": "TO220_HEATSINK"},
                "C2_ORANGE_CAP": {"bbox": [365, 310, 80, 70], "type": "RADIAL_ELECTRO_CAP"},
                "C9_ORANGE_CAP": {"bbox": [95, 215, 55, 50], "type": "RADIAL_ELECTRO_CAP"},
                "C10_ORANGE_CAP": {"bbox": [110, 295, 60, 55], "type": "RADIAL_ELECTRO_CAP"},
                "HDR_DISPLAY": {"bbox": [415, 95, 35, 100], "type": "DISPLAY_HEADER"},
                "R_ARRAY1": {"bbox": [260, 70, 70, 220], "type": "RESISTOR_ARRAY"},
            }
        },
        "analog_instrumentation": {
            "name": "Analog Precision Signal Conditioning & Test PCB",
            "source_image": "04_analog_instrumentation.png",
            "tier": "Tier 3 (Precision Analog Instrumentation)",
            "components": {
                "U1_DIP14": {"bbox": [390, 250, 75, 40], "type": "DIP14_ANALOG_IC"},
                "U2_DIP8": {"bbox": [135, 265, 45, 45], "type": "DIP8_OPAMP"},
                "VR1_TRIMPOT": {"bbox": [335, 130, 40, 45], "type": "BOURNS_TRIMPOT"},
                "VR2_TRIMPOT": {"bbox": [420, 185, 40, 45], "type": "BOURNS_TRIMPOT"},
                "VR3_TRIMPOT": {"bbox": [198, 225, 40, 45], "type": "BOURNS_TRIMPOT"},
                "VR4_TRIMPOT": {"bbox": [68, 255, 40, 45], "type": "BOURNS_TRIMPOT"},
                "C6_ELECTRO": {"bbox": [175, 105, 45, 55], "type": "RADIAL_ELECTRO_CAP"},
                "C36_FILM": {"bbox": [330, 275, 75, 30], "type": "BOX_FILM_CAP"},
                "D35_LED": {"bbox": [240, 265, 20, 25], "type": "3MM_RED_LED"},
                "Q1_TO220": {"bbox": [245, 88, 40, 40], "type": "TO220_REGULATOR"},
            }
        },
        "inverter_power_board": {
            "name": "Inverter & SMPS Power Controller PCB",
            "source_image": "06_inverter_power_board.jpg",
            "tier": "Tier 1 (Power Inverter & Motor Driver)",
            "components": {
                "C1_BULK_VENT": {"bbox": [205, 280, 70, 70], "type": "VENTED_ELECTRO_CAP"},
                "C2_BULK_VENT": {"bbox": [275, 265, 80, 75], "type": "VENTED_ELECTRO_CAP"},
                "C3_BULK_VENT": {"bbox": [230, 350, 80, 75], "type": "VENTED_ELECTRO_CAP"},
                "T1_TRANSFORMER": {"bbox": [100, 250, 65, 45], "type": "SMPS_TRANSFORMER"},
                "K1_RELAY": {"bbox": [60, 155, 45, 80], "type": "POWER_RELAY"},
                "U1_MCU": {"bbox": [210, 130, 35, 35], "type": "QFP32_PWM_MCU"},
            }
        }
    }

    manifest = {
        "metadata": {
            "title": "Industrial Multi-Board Physical SMT/THT PCB Inspection Dataset",
            "dataset_origin": "Real Hardware Physical Photographs (User Provided Artifacts)",
            "split_ratio": "70% Training / Calibration, 30% Held-Out Testing (Industry Standard)",
            "total_boards": 70,
            "train_boards": 50,
            "test_boards": 20,
            "tolerances": {
                "max_allowed_tilt_deg": 3.5,
                "max_allowed_shift_px": 5.0
            }
        },
        "boards": {},
        "images": {}
    }

    print("=" * 80)
    print("GENERATING NEW PHYSICAL PCB DATASET (70:30 SPLIT)")
    print("Source: Real physical board photographs provided by user")
    print("=" * 80)

    for b_key, b_cfg in board_configs.items():
        src_path = src_dir / b_cfg["source_image"]
        ref_bgr = cv2.imread(str(src_path))
        if ref_bgr is None:
            raise FileNotFoundError(f"Source image not found: {src_path}")

        img_h, img_w = ref_bgr.shape[:2]
        board_dir = out_dir / b_key
        board_dir.mkdir(exist_ok=True)
        ref_save_path = board_dir / "reference.png"
        cv2.imwrite(str(ref_save_path), ref_bgr)

        # Store normalized coordinates
        board_comps = {}
        for cname, cinfo in b_cfg["components"].items():
            bx, by, bw, bh = cinfo["bbox"]
            board_comps[cname] = {
                "bbox": [bx, by, bw, bh],
                "normalized_bbox": [
                    round(bx / img_w, 4),
                    round(by / img_h, 4),
                    round(bw / img_w, 4),
                    round(bh / img_h, 4),
                ],
                "type": cinfo["type"]
            }

        manifest["boards"][b_key] = {
            "name": b_cfg["name"],
            "tier": b_cfg["tier"],
            "resolution": [img_w, img_h],
            "reference_image": f"{b_key}/reference.png",
            "components": board_comps
        }

        comp_keys = list(b_cfg["components"].keys())

        # Generate 10 Train variations (71.4%)
        (out_dir / "train" / b_key).mkdir(parents=True, exist_ok=True)
        for i in range(1, 11):
            var_name = f"{b_key}_{i:02d}"
            expected_status = "OK"
            defects = {}

            if i == 1:
                # Nominal OK
                b_img = ref_bgr.copy()
                var_name += "_nominal_ok.png"
            elif i == 2:
                # Nominal Bright (+15%)
                b_img = apply_illumination(ref_bgr, "bright")
                var_name += "_nominal_bright.png"
            elif i == 3:
                # Nominal Dim (-18%)
                b_img = apply_illumination(ref_bgr, "dim")
                var_name += "_nominal_dim.png"
            elif i == 4:
                # Nominal with Specular Glare
                b_img = apply_illumination(ref_bgr, "glare")
                var_name += "_nominal_glare.png"
            elif i == 5:
                # Defect: Single missing component
                expected_status = "DEFECT"
                target_comp = comp_keys[-1]
                defects[target_comp] = {"type": "MISSING"}
                b_img = render_missing_component(ref_bgr, b_cfg["components"][target_comp]["bbox"], b_cfg["components"][target_comp]["type"])
                var_name += "_missing_single.png"
            elif i == 6:
                # Defect: Double missing components
                expected_status = "DEFECT"
                target1 = comp_keys[0]
                target2 = comp_keys[1] if len(comp_keys) > 1 else comp_keys[0]
                defects[target1] = {"type": "MISSING"}
                defects[target2] = {"type": "MISSING"}
                b_img = render_missing_component(ref_bgr, b_cfg["components"][target1]["bbox"], b_cfg["components"][target1]["type"])
                b_img = render_missing_component(b_img, b_cfg["components"][target2]["bbox"], b_cfg["components"][target2]["type"])
                var_name += "_missing_double.png"
            elif i == 7:
                # Defect: Tilted component (7.5 deg > 3.5 deg limit)
                expected_status = "DEFECT"
                target_comp = comp_keys[0]
                angle = 7.5
                defects[target_comp] = {"type": "TILTED", "angle": angle}
                b_img = render_tilted_component(ref_bgr, b_cfg["components"][target_comp]["bbox"], angle, b_cfg["components"][target_comp]["type"])
                var_name += "_tilted_part.png"
            elif i == 8:
                # Defect: Shifted component (8 px > 5 px limit)
                expected_status = "DEFECT"
                target_comp = comp_keys[1] if len(comp_keys) > 1 else comp_keys[0]
                dx, dy = 8.0, 0.0
                defects[target_comp] = {"type": "MISALIGNED", "shift": [dx, dy]}
                b_img = render_shifted_component(ref_bgr, b_cfg["components"][target_comp]["bbox"], dx, dy, b_cfg["components"][target_comp]["type"])
                var_name += "_shifted_part.png"
            elif i == 9:
                # Defect: Mixed missing & tilted
                expected_status = "DEFECT"
                target_m = comp_keys[-1]
                target_t = comp_keys[0]
                angle = -8.0
                defects[target_m] = {"type": "MISSING"}
                defects[target_t] = {"type": "TILTED", "angle": angle}
                b_img = render_missing_component(ref_bgr, b_cfg["components"][target_m]["bbox"], b_cfg["components"][target_m]["type"])
                b_img = render_tilted_component(b_img, b_cfg["components"][target_t]["bbox"], angle, b_cfg["components"][target_t]["type"])
                var_name += "_mixed_missing_tilted.png"
            elif i == 10:
                # Defect: Mixed all defects
                expected_status = "DEFECT"
                target_m = comp_keys[0]
                target_t = comp_keys[1] if len(comp_keys) > 1 else comp_keys[0]
                target_s = comp_keys[2] if len(comp_keys) > 2 else comp_keys[0]
                defects[target_m] = {"type": "MISSING"}
                defects[target_t] = {"type": "TILTED", "angle": 8.5}
                defects[target_s] = {"type": "MISALIGNED", "shift": [7.0, 4.0]}
                b_img = render_missing_component(ref_bgr, b_cfg["components"][target_m]["bbox"], b_cfg["components"][target_m]["type"])
                b_img = render_tilted_component(b_img, b_cfg["components"][target_t]["bbox"], 8.5, b_cfg["components"][target_t]["type"])
                b_img = render_shifted_component(b_img, b_cfg["components"][target_s]["bbox"], 7.0, 4.0, b_cfg["components"][target_s]["type"])
                var_name += "_mixed_all_defects.png"

            # Save train image
            save_path = out_dir / "train" / b_key / var_name
            cv2.imwrite(str(save_path), b_img)
            rel_path = f"train/{b_key}/{var_name}"
            manifest["images"][rel_path] = {
                "board_type": b_key,
                "split": "train",
                "expected_board_status": expected_status,
                "defects": defects,
                "defect_counts": {
                    "missing": sum(1 for d in defects.values() if d["type"] == "MISSING"),
                    "tilted": sum(1 for d in defects.values() if d["type"] == "TILTED"),
                    "misaligned": sum(1 for d in defects.values() if d["type"] == "MISALIGNED"),
                }
            }

        # Generate 4 Held-Out Test variations (28.6%)
        (out_dir / "test" / b_key).mkdir(parents=True, exist_ok=True)
        for i in range(1, 5):
            var_name = f"{b_key}_test_{i:02d}"
            expected_status = "OK"
            defects = {}

            if i == 1:
                # Test 1: Nominal OK with maximum spatial translation jitter
                b_img = apply_spatial_jitter(ref_bgr, max_jitter_px=4)
                var_name += "_all_ok_max_jitter.png"
            elif i == 2:
                # Test 2: Missing critical IC / component
                expected_status = "DEFECT"
                target_comp = comp_keys[0] # primary IC
                defects[target_comp] = {"type": "MISSING"}
                b_img = render_missing_component(ref_bgr, b_cfg["components"][target_comp]["bbox"], b_cfg["components"][target_comp]["type"])
                b_img = apply_spatial_jitter(b_img, max_jitter_px=3)
                var_name += "_missing_critical_ic.png"
            elif i == 3:
                # Test 3: Severe angular tilt (10.5 deg)
                expected_status = "DEFECT"
                target_comp = comp_keys[1] if len(comp_keys) > 1 else comp_keys[0]
                angle = 10.5
                defects[target_comp] = {"type": "TILTED", "angle": angle}
                b_img = render_tilted_component(ref_bgr, b_cfg["components"][target_comp]["bbox"], angle, b_cfg["components"][target_comp]["type"])
                b_img = apply_spatial_jitter(b_img, max_jitter_px=3)
                var_name += "_tilted_severe_skew.png"
            elif i == 4:
                # Test 4: Misaligned / shifted part (7.5 px)
                expected_status = "DEFECT"
                target_comp = comp_keys[2] if len(comp_keys) > 2 else comp_keys[0]
                dx, dy = 7.5, 3.5
                defects[target_comp] = {"type": "MISALIGNED", "shift": [dx, dy]}
                b_img = render_shifted_component(ref_bgr, b_cfg["components"][target_comp]["bbox"], dx, dy, b_cfg["components"][target_comp]["type"])
                b_img = apply_spatial_jitter(b_img, max_jitter_px=3)
                var_name += "_misaligned_shifted_part.png"

            save_path = out_dir / "test" / b_key / var_name
            cv2.imwrite(str(save_path), b_img)
            rel_path = f"test/{b_key}/{var_name}"
            manifest["images"][rel_path] = {
                "board_type": b_key,
                "split": "test",
                "expected_board_status": expected_status,
                "defects": defects,
                "defect_counts": {
                    "missing": sum(1 for d in defects.values() if d["type"] == "MISSING"),
                    "tilted": sum(1 for d in defects.values() if d["type"] == "TILTED"),
                    "misaligned": sum(1 for d in defects.values() if d["type"] == "MISALIGNED"),
                }
            }

        print(f"Generated {b_cfg['name']}: 10 train + 4 test = 14 boards")

    # Save manifest
    gt_file = out_dir / "ground_truth_multiboard.json"
    with open(gt_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("\n" + "=" * 80)
    print("PHYSICAL PCB DATASET GENERATION COMPLETE")
    print(f"Total Boards Generated : {len(manifest['images'])}")
    print(f"Training Split (70%)   : 50 (71.4%)")
    print(f"Testing Split (30%)    : 20 (28.6%)")
    print(f"Master Ground Truth    : {gt_file}")
    print("=" * 80)

if __name__ == "__main__":
    generate_physical_multiboard_dataset()
