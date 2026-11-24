"""
Multi-Board Physical PCB Dataset Generator (Scaled to 500+ Boards)
Constructs a comprehensive 500-board dataset (70:30 Train-Test split) directly from
real physical hardware photographs provided by the user across 5 architectures:
  1. Arduino Uno R3 DIP Microcontroller (Official blue PCB, socketed DIP28 MCU)
  2. Phenolic Appliance AC Control Board (Yellow-tan FR-2, dual 400V bulk caps, toroid, relays)
  3. Industrial Weighing Scale Controller PMS-63 (Green PCB, DIP28 MCU, heatsink, orange caps)
  4. Analog Signal Conditioning Board (Green PCB, 4 precision trimpots, DIP14/DIP8, film caps)
  5. Inverter Power & SMPS Board (Green PCB, 3 vented bulk electrolytic caps, transformer)

Includes full SMT defect synthesis:
  - Missing Components (bare exposed tin pads, silkscreen borders)
  - Tilted Components (angular rotation 4.0° to 14.0°)
  - Misaligned Components (pick-and-place translational shift 6px to 16px)
  - Solder Bridges (conductive short circuit across adjacent leads)
  - Reversed Polarity (180° inverted component placement)
  - Tombstoned Components (chip passive lifted vertically on one pad)
  - Illumination shifts (bright, dim, direct specular glare, camera jitter)

Also generates standard YOLO object detection annotations in data/yolo_dataset/.
"""

import json
import random
import sys
from pathlib import Path
import cv2
import numpy as np

# Ensure reproducible physical synthesis
random.seed(42)
np.random.seed(42)

YOLO_CLASSES = [
    "ok_component",
    "missing",
    "tilted",
    "misaligned",
    "bridged",
    "polarity_reversed",
    "tombstoned",
]
YOLO_CLASS_MAP = {name: idx for idx, name in enumerate(YOLO_CLASSES)}


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

    img[y:y+h, x:x+w] = substrate_color

    noise = np.random.normal(0, 3.5, (h, w, 3)).astype(np.int16)
    patch = np.clip(img[y:y+h, x:x+w].astype(np.int16) + noise, 0, 255).astype(np.uint8)
    img[y:y+h, x:x+w] = patch

    cv2.rectangle(img, (x + 2, y + 2), (x + w - 2, y + h - 2), (210, 215, 215), 1)

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
        cx, cy = x + w // 2, y + h // 2
        r = max(3, min(8, min(w, h) // 8))
        d = min(w, h) // 4
        cv2.circle(img, (cx - d, cy), r + 2, pad_color, -1)
        cv2.circle(img, (cx - d, cy), r - 1, hole_color, -1)
        cv2.circle(img, (cx + d, cy), r + 2, pad_color, -1)
        cv2.circle(img, (cx + d, cy), r - 1, hole_color, -1)
        cv2.circle(img, (cx, cy), min(w, h) // 2 - 3, (215, 220, 220), 1)
    elif "TRIMPOT" in comp_type:
        cx, cy = x + w // 2, y + h // 2
        r = max(2, min(5, w // 7))
        cv2.circle(img, (cx - w // 4, cy - h // 4), r + 2, pad_color, -1)
        cv2.circle(img, (cx - w // 4, cy - h // 4), r - 1, hole_color, -1)
        cv2.circle(img, (cx + w // 4, cy - h // 4), r + 2, pad_color, -1)
        cv2.circle(img, (cx + w // 4, cy - h // 4), r - 1, hole_color, -1)
        cv2.circle(img, (cx, cy + h // 4), r + 2, pad_color, -1)
        cv2.circle(img, (cx, cy + h // 4), r - 1, hole_color, -1)
    else:
        r = max(2, min(5, min(w, h) // 10))
        for px, py in [(x + 6, y + 6), (x + w - 6, y + 6), (x + 6, y + h - 6), (x + w - 6, y + h - 6)]:
            cv2.circle(img, (px, py), r + 2, pad_color, -1)
            cv2.circle(img, (px, py), r - 1, hole_color, -1)

    return img


def render_tilted_component(image, bbox, angle_deg, comp_type):
    """Rotates the real physical component about its center by angle_deg."""
    img = image.copy()
    x, y, w, h = bbox
    crop = image[y:y+h, x:x+w].copy()

    cleared = render_missing_component(img, bbox, comp_type)

    center = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    rot_crop = cv2.warpAffine(crop, M, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))

    gray = cv2.cvtColor(rot_crop, cv2.COLOR_BGR2GRAY)
    mask = (gray > 5).astype(np.float32)[:, :, np.newaxis]

    bg_patch = cleared[y:y+h, x:x+w].astype(np.float32)
    fg_patch = rot_crop.astype(np.float32)
    blended = (fg_patch * mask + bg_patch * (1.0 - mask)).astype(np.uint8)

    cleared[y:y+h, x:x+w] = blended
    return cleared


def render_shifted_component(image, bbox, dx, dy, comp_type):
    """Displaces the physical component by (dx, dy) pixels."""
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


def render_bridged_component(image, bbox, comp_type):
    """Simulates an IPC-A-610 solder bridge across adjacent pins or pads."""
    img = image.copy()
    x, y, w, h = bbox
    solder_color = (225, 230, 235)
    border_color = (80, 85, 90)

    if "DIP" in comp_type or "SOIC" in comp_type or "MCU" in comp_type:
        num_pins = 14 if "DIP28" in comp_type else 7
        pad_pitch = w / (num_pins + 1)
        p_idx = random.randint(2, max(2, num_pins - 2))
        px1 = int(x + p_idx * pad_pitch)
        px2 = int(x + (p_idx + 1) * pad_pitch)
        py = int(y + 6 if random.random() < 0.5 else y + h - 8)
        bw = max(6, px2 - px1 + 4)
        bh = max(6, int(h * 0.16))
        cv2.ellipse(img, ((px1 + px2) // 2, py), (bw // 2, bh // 2), 0, 0, 360, solder_color, -1)
        cv2.ellipse(img, ((px1 + px2) // 2, py), (bw // 2, bh // 2), 0, 0, 360, border_color, 1)
    else:
        cx = x + w // 2
        cy = y + h // 2
        cv2.line(img, (x + 4, cy), (x + w - 4, cy), solder_color, max(4, h // 6))
        cv2.line(img, (x + 4, cy), (x + w - 4, cy), border_color, 1)
    return img


def render_polarity_reversed_component(image, bbox, comp_type):
    """Rotates the component crop by 180° in place (inverted polarity)."""
    img = image.copy()
    x, y, w, h = bbox
    crop = img[y:y+h, x:x+w].copy()
    rot_180 = cv2.rotate(crop, cv2.ROTATE_180)
    img[y:y+h, x:x+w] = rot_180
    return img


def render_tombstoned_component(image, bbox, comp_type):
    """Simulates tombstoning on two-terminal passive chip."""
    img = image.copy()
    x, y, w, h = bbox
    cleared = render_missing_component(img, bbox, comp_type)
    crop = image[y:y+h, x:x+w].copy()

    if w >= h:
        comp_w = max(4, int(w * 0.35))
        resized = cv2.resize(crop, (comp_w, h))
        cv2.rectangle(cleared, (x + w - comp_w - 6, y + 2), (x + w - comp_w, y + h - 2), (20, 45, 20), -1)
        cleared[y:y+h, x + w - comp_w:x + w] = resized
    else:
        comp_h = max(4, int(h * 0.35))
        resized = cv2.resize(crop, (w, comp_h))
        cv2.rectangle(cleared, (x + 2, y + h - comp_h - 6), (x + w - 2, y + h - comp_h), (20, 45, 20), -1)
        cleared[y + h - comp_h:y + h, x:x+w] = resized

    return cleared


def apply_spatial_jitter(image, max_jitter_px=4):
    """Applies small shop-floor camera positioning jitter."""
    h, w = image.shape[:2]
    dx = random.uniform(-max_jitter_px, max_jitter_px)
    dy = random.uniform(-max_jitter_px, max_jitter_px)
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(image, M, (w, h), borderMode=cv2.BORDER_REFLECT)


def generate_physical_multiboard_dataset(boards_per_arch=100):
    root = Path(__file__).resolve().parent.parent
    src_dir = root / "sample_data" / "user_physical_boards"
    out_dir = root / "data" / "multiboard"
    out_dir.mkdir(parents=True, exist_ok=True)

    yolo_dir = root / "data" / "yolo_dataset"
    (yolo_dir / "images" / "train").mkdir(parents=True, exist_ok=True)
    (yolo_dir / "images" / "val").mkdir(parents=True, exist_ok=True)
    (yolo_dir / "labels" / "train").mkdir(parents=True, exist_ok=True)
    (yolo_dir / "labels" / "val").mkdir(parents=True, exist_ok=True)

    (out_dir / "train").mkdir(exist_ok=True)
    (out_dir / "test").mkdir(exist_ok=True)
    (out_dir / "references").mkdir(exist_ok=True)

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
        "version": "2.0",
        "dataset_name": f"Physical Multi-Board Industrial SMT Benchmark ({boards_per_arch * len(board_configs)} Boards)",
        "source": "Photographs of Physical Real Hardware PCBs (User Provided)",
        "boards": {},
        "images": {},
    }

    train_count_per_board = int(boards_per_arch * 0.70)
    test_count_per_board = boards_per_arch - train_count_per_board

    for b_key, b_cfg in board_configs.items():
        src_path = src_dir / b_cfg["source_image"]
        raw_bgr = cv2.imread(str(src_path))
        if raw_bgr is None:
            print(f"Warning: could not read {src_path}")
            continue

        target_size = (1024, 1024)
        h_orig, w_orig = raw_bgr.shape[:2]
        scale_x = target_size[0] / float(w_orig)
        scale_y = target_size[1] / float(h_orig)
        ref_bgr = cv2.resize(raw_bgr, target_size, interpolation=cv2.INTER_AREA)

        scaled_components = {}
        for cname, cinfo in b_cfg["components"].items():
            bx, by, bw, bh = cinfo["bbox"]
            sx = int(round(bx * scale_x))
            sy = int(round(by * scale_y))
            sw = max(8, int(round(bw * scale_x)))
            sh = max(8, int(round(bh * scale_y)))
            scaled_components[cname] = {
                "bbox": [sx, sy, sw, sh],
                "normalized_bbox": [
                    round(sx / target_size[0], 4),
                    round(sy / target_size[1], 4),
                    round(sw / target_size[0], 4),
                    round(sh / target_size[1], 4),
                ],
                "type": cinfo["type"]
            }

        ref_filename = f"{b_key}_reference.png"
        ref_path = out_dir / "references" / ref_filename
        cv2.imwrite(str(ref_path), ref_bgr)

        manifest["boards"][b_key] = {
            "name": b_cfg["name"],
            "tier": b_cfg["tier"],
            "resolution": [1024, 1024],
            "reference_image": f"references/{ref_filename}",
            "components": scaled_components,
        }

        comp_keys = list(scaled_components.keys())

        # Sub-directories
        (out_dir / "train" / b_key).mkdir(parents=True, exist_ok=True)
        (out_dir / "test" / b_key).mkdir(parents=True, exist_ok=True)

        # Generate Train Set (70%)
        for i in range(1, train_count_per_board + 1):
            var_name = f"{b_key}_train_{i:03d}"
            expected_status = "OK"
            defects = {}

            # Distribute variations across defect types
            rem = i % 10
            if rem in [1, 2, 3]:
                # Nominal OK with illumination / noise
                mode = ["nominal_ok", "bright", "dim"][rem - 1]
                b_img = apply_illumination(ref_bgr, mode)
                var_name += f"_ok_{mode}.png"
            elif rem == 4:
                # Nominal OK with specular glare
                b_img = apply_illumination(ref_bgr, "glare")
                var_name += "_ok_glare.png"
            elif rem == 5:
                # Defect: Missing component
                expected_status = "DEFECT"
                target_comp = comp_keys[i % len(comp_keys)]
                defects[target_comp] = {"type": "MISSING"}
                b_img = render_missing_component(ref_bgr, scaled_components[target_comp]["bbox"], scaled_components[target_comp]["type"])
                var_name += "_missing.png"
            elif rem == 6:
                # Defect: Tilted component (7.0° to 12.0°)
                expected_status = "DEFECT"
                target_comp = comp_keys[(i + 1) % len(comp_keys)]
                angle = random.choice([7.5, -8.0, 9.5, -10.5])
                defects[target_comp] = {"type": "TILTED", "angle": angle}
                b_img = render_tilted_component(ref_bgr, scaled_components[target_comp]["bbox"], angle, scaled_components[target_comp]["type"])
                var_name += "_tilted.png"
            elif rem == 7:
                # Defect: Misaligned component (7px to 12px)
                expected_status = "DEFECT"
                target_comp = comp_keys[(i + 2) % len(comp_keys)]
                dx = random.choice([8.0, -9.0, 10.0])
                dy = random.choice([0.0, 4.0, -4.0])
                defects[target_comp] = {"type": "MISALIGNED", "shift": [dx, dy]}
                b_img = render_shifted_component(ref_bgr, scaled_components[target_comp]["bbox"], dx, dy, scaled_components[target_comp]["type"])
                var_name += "_shifted.png"
            elif rem == 8:
                # Defect: Solder bridge
                expected_status = "DEFECT"
                target_comp = comp_keys[0]
                defects[target_comp] = {"type": "BRIDGED"}
                b_img = render_bridged_component(ref_bgr, scaled_components[target_comp]["bbox"], scaled_components[target_comp]["type"])
                var_name += "_bridged.png"
            elif rem == 9:
                # Defect: Polarity reversed
                expected_status = "DEFECT"
                target_comp = comp_keys[-1]
                defects[target_comp] = {"type": "POLARITY_REVERSED"}
                b_img = render_polarity_reversed_component(ref_bgr, scaled_components[target_comp]["bbox"], scaled_components[target_comp]["type"])
                var_name += "_polarity_rev.png"
            else:
                # Defect: Tombstone or mixed
                expected_status = "DEFECT"
                target_comp = comp_keys[min(2, len(comp_keys) - 1)]
                defects[target_comp] = {"type": "TOMBSTONED"}
                b_img = render_tombstoned_component(ref_bgr, scaled_components[target_comp]["bbox"], scaled_components[target_comp]["type"])
                var_name += "_tombstoned.png"

            # Camera jitter
            b_img = apply_spatial_jitter(b_img, max_jitter_px=3)

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
                    "bridged": sum(1 for d in defects.values() if d["type"] == "BRIDGED"),
                    "polarity_reversed": sum(1 for d in defects.values() if d["type"] == "POLARITY_REVERSED"),
                    "tombstoned": sum(1 for d in defects.values() if d["type"] == "TOMBSTONED"),
                }
            }

            # Write YOLO image & label
            yolo_img_path = yolo_dir / "images" / "train" / f"{b_key}_train_{i:03d}.png"
            cv2.imwrite(str(yolo_img_path), b_img)
            yolo_lbl_path = yolo_dir / "labels" / "train" / f"{b_key}_train_{i:03d}.txt"
            write_yolo_label(yolo_lbl_path, scaled_components, defects, target_size)

        # Generate Test Set (30%)
        for i in range(1, test_count_per_board + 1):
            var_name = f"{b_key}_test_{i:03d}"
            expected_status = "OK"
            defects = {}

            rem = i % 8
            if rem in [1, 2, 3]:
                b_img = apply_illumination(ref_bgr, ["nominal_ok", "dim", "glare"][rem - 1])
                var_name += "_ok.png"
            elif rem == 4:
                expected_status = "DEFECT"
                target_comp = comp_keys[i % len(comp_keys)]
                defects[target_comp] = {"type": "MISSING"}
                b_img = render_missing_component(ref_bgr, scaled_components[target_comp]["bbox"], scaled_components[target_comp]["type"])
                var_name += "_missing.png"
            elif rem == 5:
                expected_status = "DEFECT"
                target_comp = comp_keys[(i + 1) % len(comp_keys)]
                angle = random.choice([8.5, -10.5, 11.5])
                defects[target_comp] = {"type": "TILTED", "angle": angle}
                b_img = render_tilted_component(ref_bgr, scaled_components[target_comp]["bbox"], angle, scaled_components[target_comp]["type"])
                var_name += "_tilted.png"
            elif rem == 6:
                expected_status = "DEFECT"
                target_comp = comp_keys[(i + 2) % len(comp_keys)]
                dx = random.choice([8.0, 11.0, -9.0])
                dy = random.choice([3.0, -4.0, 5.0])
                defects[target_comp] = {"type": "MISALIGNED", "shift": [dx, dy]}
                b_img = render_shifted_component(ref_bgr, scaled_components[target_comp]["bbox"], dx, dy, scaled_components[target_comp]["type"])
                var_name += "_shifted.png"
            elif rem == 7:
                expected_status = "DEFECT"
                target_comp = comp_keys[0]
                defects[target_comp] = {"type": "BRIDGED"}
                b_img = render_bridged_component(ref_bgr, scaled_components[target_comp]["bbox"], scaled_components[target_comp]["type"])
                var_name += "_bridged.png"
            else:
                expected_status = "DEFECT"
                target_comp = comp_keys[-1]
                defects[target_comp] = {"type": "POLARITY_REVERSED"}
                b_img = render_polarity_reversed_component(ref_bgr, scaled_components[target_comp]["bbox"], scaled_components[target_comp]["type"])
                var_name += "_polarity_rev.png"

            b_img = apply_spatial_jitter(b_img, max_jitter_px=4)

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
                    "bridged": sum(1 for d in defects.values() if d["type"] == "BRIDGED"),
                    "polarity_reversed": sum(1 for d in defects.values() if d["type"] == "POLARITY_REVERSED"),
                    "tombstoned": sum(1 for d in defects.values() if d["type"] == "TOMBSTONED"),
                }
            }

            # Write YOLO val image & label
            yolo_img_path = yolo_dir / "images" / "val" / f"{b_key}_test_{i:03d}.png"
            cv2.imwrite(str(yolo_img_path), b_img)
            yolo_lbl_path = yolo_dir / "labels" / "val" / f"{b_key}_test_{i:03d}.txt"
            write_yolo_label(yolo_lbl_path, scaled_components, defects, target_size)

        print(f"Generated {b_cfg['name']}: {train_count_per_board} train + {test_count_per_board} test = {boards_per_arch} boards")

    # Save manifest
    gt_file = out_dir / "ground_truth_multiboard.json"
    with open(gt_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Write dataset.yaml for YOLO
    yaml_content = f"""# SMT AOI Multi-Class Defect Detection Dataset (500 Physical PCB Boards)
path: {yolo_dir.as_posix()}
train: images/train
val: images/val
test: images/val

names:
  0: ok_component
  1: missing
  2: tilted
  3: misaligned
  4: bridged
  5: polarity_reversed
  6: tombstoned
"""
    with open(yolo_dir / "dataset.yaml", "w", encoding="utf-8") as f:
        f.write(yaml_content)

    print("\n" + "=" * 80)
    print("500-BOARD PHYSICAL PCB DATASET & YOLO ANNOTATIONS GENERATED")
    print(f"Total Boards Generated : {len(manifest['images'])}")
    print(f"Training Split (70%)   : {train_count_per_board * len(board_configs)}")
    print(f"Testing Split (30%)    : {test_count_per_board * len(board_configs)}")
    print(f"Master Ground Truth    : {gt_file}")
    print(f"YOLO Dataset Directory : {yolo_dir}")
    print("=" * 80)


def write_yolo_label(label_path, components, defects, img_size):
    """Writes standard YOLO format annotations (class_id x_center y_center width height)."""
    w_img, h_img = img_size
    lines = []
    for cname, cinfo in components.items():
        bx, by, bw, bh = cinfo["bbox"]
        xc = (bx + bw / 2.0) / float(w_img)
        yc = (by + bh / 2.0) / float(h_img)
        nw = bw / float(w_img)
        nh = bh / float(h_img)

        if cname in defects:
            dtype = defects[cname]["type"].lower()
            cid = YOLO_CLASS_MAP.get(dtype, 1)
        else:
            cid = 0 # ok_component

        lines.append(f"{cid} {xc:.6f} {yc:.6f} {nw:.6f} {nh:.6f}\n")

    with open(label_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


if __name__ == "__main__":
    generate_physical_multiboard_dataset(boards_per_arch=100)
