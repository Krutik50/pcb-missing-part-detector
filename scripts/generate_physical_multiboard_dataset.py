"""
Multi-Board Physical SMT Dataset Generator with 70:30 Industry Split.
Generates diverse physical PCB designs across 3 complexity tiers:
- Tier 1 (Simple): LM2596 Buck Converter, MPU-6050 Sensor Breakout
- Tier 2 (Medium): Arduino Uno R3, ESP32 DevKit
- Tier 3 (Complex): Industrial Sensor Controller (Multi-IC STM32 + EEPROM + Regulators + Passives)

Defect Taxonomy (IPC-A-610 Standard):
1. MISSING: Part unpopulated / dropped (bare pads + exposed FR-4 substrate)
2. TILTED: Part rotated beyond tolerance (|theta| > 3.5 deg)
3. MISALIGNED: Part shifted translationally beyond tolerance (dist > 5.0 px)
4. NOMINAL: Part present within acceptable tolerance (|theta| <= 1.5 deg, dist <= 2.0 px)

Split:
- 70% Training / Calibration
- 30% Held-Out Testing (strictly isolated)
"""

import os
import json
import math
import random
from pathlib import Path
from typing import Dict, Any, List, Tuple
import cv2
import numpy as np


OUTPUT_DIR = Path("data/multiboard")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def draw_pcb_background(w: int, h: int, color_theme: str = "green") -> np.ndarray:
    """Generates realistic PCB soldermask texture with substrate weave and copper ground planes."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    if color_theme == "green":
        base_color = (24, 110, 32)
        trace_color = (18, 140, 42)
    elif color_theme == "blue":
        base_color = (130, 60, 18)
        trace_color = (160, 80, 24)
    elif color_theme == "black":
        base_color = (25, 25, 25)
        trace_color = (38, 38, 38)
    elif color_theme == "red":
        base_color = (25, 25, 140)
        trace_color = (35, 35, 175)
    else:
        base_color = (24, 110, 32)
        trace_color = (18, 140, 42)

    img[:] = base_color

    # Add subtle weave noise
    noise = np.random.normal(0, 3, (h, w, 3)).astype(np.int16)
    img_textured = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # Draw circuit traces
    for _ in range(40):
        x1 = random.randint(50, w - 50)
        y1 = random.randint(50, h - 50)
        length = random.randint(100, 400)
        direction = random.choice([(1, 0), (0, 1), (1, 1), (1, -1)])
        x2 = min(w - 20, max(20, x1 + direction[0] * length))
        y2 = min(h - 20, max(20, y1 + direction[1] * length))
        thick = random.choice([2, 3, 4])
        cv2.line(img_textured, (x1, y1), (x2, y2), trace_color, thick)

    # Gold/copper mounting holes in corners
    for mx, my in [(60, 60), (w - 60, 60), (60, h - 60), (w - 60, h - 60)]:
        cv2.circle(img_textured, (mx, my), 28, (40, 180, 215), -1)  # Gold pad ring
        cv2.circle(img_textured, (mx, my), 24, (200, 200, 200), -1) # Tin solder ring
        cv2.circle(img_textured, (mx, my), 16, (10, 10, 10), -1)     # Drill hole

    return img_textured


def draw_component_patch(comp_type: str, w: int, h: int, label: str = "") -> Tuple[np.ndarray, np.ndarray]:
    """
    Renders an isolated component patch (foreground BGR) and its populated vs bare solder pads.
    Returns:
        populated_patch, bare_pads_patch
    """
    patch = np.zeros((h, w, 3), dtype=np.uint8)
    bare = np.zeros((h, w, 3), dtype=np.uint8)

    # Component types
    if "QFP" in comp_type or "QFN" in comp_type or "MCU" in comp_type:
        # Square/Rectangular IC with pins on 4 sides
        pad_len = max(6, int(0.15 * min(w, h)))
        # Bare pads (metallic tin/gold rectangles around perimeter)
        bare[:] = (24, 110, 32)
        # Solder pads around 4 edges
        for i in range(pad_len, w - pad_len, max(6, int(w / 12))):
            cv2.rectangle(bare, (i, 2), (i + 4, pad_len), (210, 215, 215), -1) # Top
            cv2.rectangle(bare, (i, h - pad_len), (i + 4, h - 2), (210, 215, 215), -1) # Bottom
        for j in range(pad_len, h - pad_len, max(6, int(h / 12))):
            cv2.rectangle(bare, (2, j), (pad_len, j + 4), (210, 215, 215), -1) # Left
            cv2.rectangle(bare, (w - pad_len, j), (w - 2, j + 4), (210, 215, 215), -1) # Right
        # Silkscreen box & pin 1 dot on bare board
        cv2.rectangle(bare, (pad_len + 2, pad_len + 2), (w - pad_len - 2, h - pad_len - 2), (240, 240, 240), 1)
        cv2.circle(bare, (pad_len + 8, pad_len + 8), 3, (240, 240, 240), -1)

        # Populated: Copy bare pads, then add black epoxy package body
        patch = bare.copy()
        cv2.rectangle(patch, (pad_len, pad_len), (w - pad_len, h - pad_len), (26, 26, 26), -1)
        # Chamfer / bevel highlight
        cv2.rectangle(patch, (pad_len, pad_len), (w - pad_len, h - pad_len), (60, 60, 60), 1)
        cv2.circle(patch, (pad_len + 10, pad_len + 10), 4, (15, 15, 15), -1)
        if label:
            cv2.putText(patch, label, (pad_len + 8, h // 2 + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (140, 140, 140), 1)

    elif "SOIC" in comp_type or "SOP" in comp_type:
        # Dual-row IC (e.g. SOIC-8, SOIC-16)
        pad_len = max(6, int(0.20 * h))
        bare[:] = (24, 110, 32)
        step = max(8, int(w / 5))
        for i in range(step // 2, w - 4, step):
            cv2.rectangle(bare, (i, 2), (i + 5, pad_len), (215, 220, 220), -1)
            cv2.rectangle(bare, (i, h - pad_len), (i + 5, h - 2), (215, 220, 220), -1)
        cv2.rectangle(bare, (4, pad_len + 2), (w - 4, h - pad_len - 2), (240, 240, 240), 1)

        patch = bare.copy()
        cv2.rectangle(patch, (4, pad_len), (w - 4, h - pad_len), (28, 28, 28), -1)
        cv2.circle(patch, (10, pad_len + 6), 3, (15, 15, 15), -1)
        if label:
            cv2.putText(patch, label, (8, h // 2 + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (135, 135, 135), 1)

    elif "SOT" in comp_type:
        # 3-terminal regulator (tab on top, 3 leads bottom)
        bare[:] = (24, 110, 32)
        # Top large tab pad
        cv2.rectangle(bare, (w // 4, 2), (3 * w // 4, int(0.35 * h)), (215, 220, 220), -1)
        # 3 bottom leads
        for i in [w // 6, w // 2 - 4, 5 * w // 6 - 8]:
            cv2.rectangle(bare, (i, int(0.75 * h)), (i + 8, h - 2), (215, 220, 220), -1)

        patch = bare.copy()
        cv2.rectangle(patch, (w // 6, int(0.25 * h)), (5 * w // 6, int(0.75 * h)), (30, 30, 30), -1)
        if label:
            cv2.putText(patch, label, (w // 4, int(0.55 * h)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 140, 140), 1)

    elif "XTAL" in comp_type or "CRYSTAL" in comp_type:
        # Metallic crystal can
        bare[:] = (24, 110, 32)
        cv2.rectangle(bare, (4, 4), (12, h - 4), (215, 220, 220), -1)
        cv2.rectangle(bare, (w - 12, 4), (w - 4, h - 4), (215, 220, 220), -1)

        patch = bare.copy()
        # Metallic silver body
        cv2.rectangle(patch, (8, 4), (w - 8, h - 4), (195, 195, 205), -1)
        cv2.rectangle(patch, (8, 4), (w - 8, h - 4), (230, 230, 240), 1)
        cv2.putText(patch, "16.0", (12, h // 2 + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (70, 70, 70), 1)

    elif "INDUCTOR" in comp_type:
        # Power inductor (dark square / toroidal)
        bare[:] = (24, 110, 32)
        cv2.rectangle(bare, (2, h // 4), (10, 3 * h // 4), (215, 220, 220), -1)
        cv2.rectangle(bare, (w - 10, h // 4), (w - 2, 3 * h // 4), (215, 220, 220), -1)

        patch = bare.copy()
        cv2.rectangle(patch, (8, 4), (w - 8, h - 4), (35, 38, 42), -1)
        cv2.circle(patch, (w // 2, h // 2), int(min(w, h) * 0.35), (45, 48, 52), -1)
        cv2.putText(patch, "100", (w // 2 - 12, h // 2 + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (160, 160, 160), 1)

    elif "ELECTRO" in comp_type or "CAP_CAN" in comp_type:
        # Aluminum electrolytic can capacitor
        bare[:] = (24, 110, 32)
        cv2.rectangle(bare, (2, 2), (w - 2, h - 2), (240, 240, 240), 1)
        cv2.circle(bare, (w // 2, h // 2), min(w, h) // 2 - 4, (215, 220, 220), 2)

        patch = bare.copy()
        rad = min(w, h) // 2 - 4
        cv2.circle(patch, (w // 2, h // 2), rad, (190, 195, 200), -1)
        # Black polarity mark stripe
        cv2.ellipse(patch, (w // 2, h // 2), (rad, rad), 0, -45, 45, (40, 40, 40), -1)

    else:
        # 0805 / 0603 Chip Resistor or Ceramic Capacitor
        bare[:] = (24, 110, 32)
        cv2.rectangle(bare, (2, 2), (8, h - 2), (215, 220, 220), -1)
        cv2.rectangle(bare, (w - 8, 2), (w - 2, h - 2), (215, 220, 220), -1)

        patch = bare.copy()
        is_resistor = "R" in comp_type.upper()
        body_color = (20, 20, 20) if is_resistor else (75, 120, 165) # Black for resistor, brown for cap
        cv2.rectangle(patch, (6, 2), (w - 6, h - 2), body_color, -1)
        # Silver terminal caps
        cv2.rectangle(patch, (2, 2), (6, h - 2), (200, 205, 210), -1)
        cv2.rectangle(patch, (w - 6, 2), (w - 2, h - 2), (200, 205, 210), -1)

    return patch, bare


# Definition of Physical Board Templates
BOARD_SPECS = {
    "arduino_uno": {
        "theme": "blue",
        "name": "Arduino Uno R3 Physical Microcontroller",
        "components": {
            "U1_ATMEGA328": {"type": "QFP32", "bbox": [560, 420, 160, 160], "label": "MEGA328"},
            "U2_CH340G": {"type": "SOIC16", "bbox": [320, 260, 120, 70], "label": "CH340G"},
            "U3_AMS1117": {"type": "SOT223", "bbox": [280, 420, 90, 70], "label": "1117-5V"},
            "Y1_CRYSTAL_16M": {"type": "XTAL", "bbox": [470, 480, 60, 30], "label": "16MHz"},
            "C1_BULK": {"type": "CAP_CAN", "bbox": [200, 360, 70, 70], "label": "47uF"},
            "C2_BULK": {"type": "CAP_CAN", "bbox": [200, 480, 70, 70], "label": "47uF"},
            "C3_DECOUP": {"type": "C0805", "bbox": [530, 410, 24, 40], "label": "0.1uF"},
            "C4_DECOUP": {"type": "C0805", "bbox": [730, 520, 24, 40], "label": "0.1uF"},
            "R1_PULLUP": {"type": "R0805", "bbox": [490, 380, 24, 40], "label": "10k"},
            "R2_LED": {"type": "R0805", "bbox": [750, 420, 24, 40], "label": "1k"},
            "D1_LED_ON": {"type": "R0805", "bbox": [790, 420, 24, 40], "label": "GREEN"},
        }
    },
    "esp32_devkit": {
        "theme": "black",
        "name": "ESP32-WROOM-32 IoT Module",
        "components": {
            "U1_ESP32_MODULE": {"type": "QFN_SHIELD", "bbox": [600, 260, 260, 320], "label": "ESP32-WROOM"},
            "U2_CP2102": {"type": "QFN28", "bbox": [420, 480, 90, 90], "label": "CP2102"},
            "U3_ME6211_LDO": {"type": "SOT223", "bbox": [420, 360, 80, 60], "label": "3.3V"},
            "C1_RF_DECOUP": {"type": "C0603", "bbox": [570, 300, 20, 32], "label": "10uF"},
            "C2_RF_DECOUP": {"type": "C0603", "bbox": [570, 360, 20, 32], "label": "0.1uF"},
            "R1_BOOT_PULLUP": {"type": "R0603", "bbox": [540, 480, 20, 32], "label": "10k"},
            "R2_TXD_RES": {"type": "R0603", "bbox": [540, 530, 20, 32], "label": "470R"},
            "D1_PWR_LED": {"type": "R0603", "bbox": [360, 360, 20, 32], "label": "RED"},
        }
    },
    "power_buck_lm2596": {
        "theme": "green",
        "name": "LM2596 High-Efficiency Step-Down Buck Converter",
        "components": {
            "U1_LM2596_SW": {"type": "TO263", "bbox": [480, 340, 160, 140], "label": "LM2596"},
            "L1_POWER_INDUCTOR": {"type": "INDUCTOR", "bbox": [680, 330, 140, 140], "label": "100uH"},
            "C1_INPUT_FILTER": {"type": "CAP_CAN", "bbox": [320, 340, 90, 90], "label": "220uF"},
            "C2_OUTPUT_FILTER": {"type": "CAP_CAN", "bbox": [860, 340, 90, 90], "label": "220uF"},
            "D1_SCHOTTKY": {"type": "SMC_DIODE", "bbox": [520, 510, 80, 50], "label": "SS34"},
            "R1_FEEDBACK": {"type": "R0805", "bbox": [670, 500, 30, 45], "label": "3.3k"},
            "C3_FEEDBACK_CAP": {"type": "C0805", "bbox": [720, 500, 30, 45], "label": "1nF"},
        }
    },
    "sensor_mpu6050": {
        "theme": "blue",
        "name": "MPU-6050 6-Axis MotionTracking IMU",
        "components": {
            "U1_MPU6050": {"type": "QFN24", "bbox": [500, 380, 110, 110], "label": "MPU6050"},
            "U2_KB33_LDO": {"type": "SOT223", "bbox": [360, 390, 75, 60], "label": "3.3V"},
            "C1_CHARGE_PUMP": {"type": "C0603", "bbox": [630, 390, 20, 30], "label": "2.2nF"},
            "C2_VLOGIC": {"type": "C0603", "bbox": [630, 440, 20, 30], "label": "0.1uF"},
            "R1_I2C_SCL": {"type": "R0603", "bbox": [460, 340, 30, 20], "label": "4.7k"},
            "R2_I2C_SDA": {"type": "R0603", "bbox": [510, 340, 30, 20], "label": "4.7k"},
            "D1_POWER_LED": {"type": "R0603", "bbox": [320, 390, 20, 30], "label": "LED"},
        }
    },
    "industrial_sensor_controller": {
        "theme": "green",
        "name": "Industrial Sensor Controller Rev 2.1 (Full Suite)",
        "components": {
            "U1_MCU": {"type": "QFP32", "bbox": [580, 400, 200, 200], "label": "STM32F4"},
            "U2_REG": {"type": "SOT223", "bbox": [940, 440, 140, 100], "label": "AMS1117"},
            "U3_EEPROM": {"type": "SOIC8", "bbox": [940, 620, 120, 90], "label": "24C08"},
            "C1_DECOUP": {"type": "C0805", "bbox": [470, 430, 24, 30], "label": "100nF"},
            "C2_DECOUP": {"type": "C0805", "bbox": [470, 520, 24, 30], "label": "100nF"},
            "C3_DECOUP": {"type": "C0805", "bbox": [830, 430, 24, 30], "label": "100nF"},
            "C4_BULK": {"type": "C1206", "bbox": [1130, 470, 36, 45], "label": "10uF"},
            "R1_PULLUP": {"type": "R0805", "bbox": [880, 420, 24, 48], "label": "4.7k"},
            "R2_PULLUP": {"type": "R0805", "bbox": [880, 490, 24, 48], "label": "4.7k"},
            "R3_PULLUP": {"type": "R0805", "bbox": [880, 560, 24, 48], "label": "4.7k"},
            "R4_PULLUP": {"type": "R0805", "bbox": [880, 630, 24, 48], "label": "4.7k"},
            "R5_SHUNTR": {"type": "R0805", "bbox": [880, 700, 24, 48], "label": "0.1R"},
            "D1_LED": {"type": "LED0805", "bbox": [500, 670, 24, 35], "label": "PWR"},
            "Y1_XTAL": {"type": "XTAL", "bbox": [440, 460, 40, 80], "label": "8MHz"},
        }
    }
}


def build_base_board(board_key: str) -> Tuple[np.ndarray, Dict[str, Any], Dict[str, Tuple[np.ndarray, np.ndarray]]]:
    """Generates the clean golden physical reference board and component patches."""
    spec = BOARD_SPECS[board_key]
    w, h = 1920, 1080
    theme = spec.get("theme", "green")
    board_img = draw_pcb_background(w, h, color_theme=theme)
    components = spec["components"]
    patches = {}

    for cname, cinfo in components.items():
        bx, by, bw, bh = cinfo["bbox"]
        c_type = cinfo.get("type", "GENERIC")
        label = cinfo.get("label", "")
        pop, bare = draw_component_patch(c_type, bw, bh, label=label)
        patches[cname] = (pop, bare)
        # Paste populated component onto reference board
        board_img[by:by+bh, bx:bx+bw] = pop

    return board_img, components, patches


def inject_defects_and_save(
    base_img: np.ndarray,
    components: Dict[str, Any],
    patches: Dict[str, Tuple[np.ndarray, np.ndarray]],
    target_path: Path,
    defects: Dict[str, Dict[str, Any]],
    global_shift: Tuple[int, int] = (0, 0),
    global_rotation: float = 0.0,
    glare_pos: Tuple[int, int] = None,
    brightness_mult: float = 1.0,
):
    """
    Synthesizes a test board with specified component defects:
    defects[cname] = {"type": "MISSING" | "TILTED" | "MISALIGNED", "param": float / tuple}
    """
    img = base_img.copy()
    h, w = img.shape[:2]

    # Apply component modifications
    for cname, cinfo in components.items():
        bx, by, bw, bh = cinfo["bbox"]
        pop, bare = patches[cname]

        if cname in defects:
            d_info = defects[cname]
            dtype = d_info["type"]

            if dtype == "MISSING":
                # Inpaint bare pads
                img[by:by+bh, bx:bx+bw] = bare

            elif dtype == "TILTED":
                # Rotate component by angle in degrees (beyond 3.5 deg tolerance)
                angle = d_info.get("angle", 7.0)
                # First put bare pads underneath so corners reveal substrate
                img[by:by+bh, bx:bx+bw] = bare
                center = (bw / 2.0, bh / 2.0)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                rotated_comp = cv2.warpAffine(pop, M, (bw, bh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_TRANSPARENT)
                # Alpha composite
                mask = (rotated_comp > 0).astype(np.uint8) * 255
                mask_gray = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
                _, bin_mask = cv2.threshold(mask_gray, 10, 255, cv2.THRESH_BINARY)
                roi = img[by:by+bh, bx:bx+bw]
                roi_bg = cv2.bitwise_and(roi, roi, mask=cv2.bitwise_not(bin_mask))
                roi_fg = cv2.bitwise_and(rotated_comp, rotated_comp, mask=bin_mask)
                img[by:by+bh, bx:bx+bw] = cv2.add(roi_bg, roi_fg)

            elif dtype == "MISALIGNED":
                # Shift component position by (dx, dy)
                dx, dy = d_info.get("shift", (8, 4))
                # Put bare pads at original location
                img[by:by+bh, bx:bx+bw] = bare
                # Paste populated at shifted location
                sx = max(0, min(w - bw, bx + dx))
                sy = max(0, min(h - bh, by + dy))
                img[sy:sy+bh, sx:sx+bw] = pop
        else:
            # Nominal component: add natural micro-jitter (within tolerance: tilt <= 1.5 deg, shift <= 1.5 px)
            micro_tilt = random.uniform(-1.0, 1.0)
            if abs(micro_tilt) > 0.4:
                center = (bw / 2.0, bh / 2.0)
                M = cv2.getRotationMatrix2D(center, micro_tilt, 1.0)
                rot = cv2.warpAffine(pop, M, (bw, bh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                img[by:by+bh, bx:bx+bw] = rot

    # Apply global mechanical board rotation and translation
    if global_rotation != 0.0 or global_shift != (0, 0):
        M_board = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), global_rotation, 1.0)
        M_board[0, 2] += global_shift[0]
        M_board[1, 2] += global_shift[1]
        img = cv2.warpAffine(img, M_board, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))

    # Apply spot glare if requested
    if glare_pos is not None:
        gx, gy = glare_pos
        Y, X = np.ogrid[:h, :w]
        dist_sq = (X - gx) ** 2 + (Y - gy) ** 2
        radius = 90
        glare_intensity = np.exp(-dist_sq / (2 * (radius ** 2))) * 180.0
        glare_3ch = np.dstack([glare_intensity] * 3).astype(np.float32)
        img = np.clip(img.astype(np.float32) + glare_3ch, 0, 255).astype(np.uint8)

    # Apply brightness gain
    if brightness_mult != 1.0:
        img = np.clip(img.astype(np.float32) * brightness_mult, 0, 255).astype(np.uint8)

    # Save image
    target_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target_path), img)


def generate_full_dataset():
    print("=" * 80)
    print("GENERATING MULTI-BOARD PHYSICAL SMT DATASET (70:30 SPLIT)")
    print("=" * 80)

    gt_manifest = {
        "metadata": {
            "title": "Industrial Multi-Board Physical SMT Placement Dataset",
            "split_ratio": "70% Training / Calibration, 30% Held-Out Testing",
            "resolution": [1920, 1080],
            "ipc_tolerances": {
                "max_allowed_tilt_deg": 3.5,
                "max_allowed_shift_px": 5.0
            }
        },
        "boards": {},
        "images": {}
    }

    total_images = 0
    train_count = 0
    test_count = 0

    for bkey, bspec in BOARD_SPECS.items():
        print(f"\nProcessing Board Type: {bspec['name']} ({bkey})")
        base_img, comps, patches = build_base_board(bkey)

        # Save Reference Board
        ref_path = OUTPUT_DIR / bkey / "reference.png"
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(ref_path), base_img)

        comp_keys = sorted(list(comps.keys()))
        gt_manifest["boards"][bkey] = {
            "name": bspec["name"],
            "reference_image": str(ref_path.relative_to(OUTPUT_DIR)),
            "components": {
                k: {
                    "bbox": v["bbox"],
                    "normalized_bbox": [
                        round(v["bbox"][0] / 1920, 4),
                        round(v["bbox"][1] / 1080, 4),
                        round(v["bbox"][2] / 1920, 4),
                        round(v["bbox"][3] / 1080, 4),
                    ],
                    "type": v.get("type", "GENERIC")
                }
                for k, v in comps.items()
            }
        }

        # 14 Variations per board: 10 Train (71.4%), 4 Test (28.6%) -> 70:30 Industry standard
        variations = [
            # Train Split (10 images)
            {"id": "01_nominal_ok", "split": "train", "defects": {}, "shift": (1, -1), "rot": 0.2},
            {"id": "02_nominal_bright", "split": "train", "defects": {}, "gain": 1.25},
            {"id": "03_nominal_dim", "split": "train", "defects": {}, "gain": 0.75},
            {"id": "04_nominal_glare", "split": "train", "defects": {}, "glare": (comps[comp_keys[0]]["bbox"][0] + 50, comps[comp_keys[0]]["bbox"][1] + 50)},
            {"id": "05_missing_single", "split": "train", "defects": {comp_keys[1]: {"type": "MISSING"}}},
            {"id": "06_missing_double", "split": "train", "defects": {comp_keys[0]: {"type": "MISSING"}, comp_keys[2]: {"type": "MISSING"}}},
            {"id": "07_tilted_part", "split": "train", "defects": {comp_keys[1]: {"type": "TILTED", "angle": 7.5}}},
            {"id": "08_shifted_part", "split": "train", "defects": {comp_keys[2]: {"type": "MISALIGNED", "shift": (9, 3)}}},
            {"id": "09_mixed_missing_tilted", "split": "train", "defects": {comp_keys[0]: {"type": "TILTED", "angle": -8.0}, comp_keys[-1]: {"type": "MISSING"}}},
            {"id": "10_mixed_all_defects", "split": "train", "defects": {comp_keys[1]: {"type": "MISSING"}, comp_keys[2]: {"type": "TILTED", "angle": 6.5}, comp_keys[3]: {"type": "MISALIGNED", "shift": (-8, 6)}}},

            # Held-Out Test Split (4 images) - 30% strictly held out
            {"id": "test_01_all_ok_max_jitter", "split": "test", "defects": {}, "shift": (-3, 2), "rot": -0.8},
            {"id": "test_02_missing_critical_ic", "split": "test", "defects": {comp_keys[0]: {"type": "MISSING"}}},
            {"id": "test_03_tilted_severe_skew", "split": "test", "defects": {comp_keys[1]: {"type": "TILTED", "angle": 10.5}}},
            {"id": "test_04_misaligned_shifted_part", "split": "test", "defects": {comp_keys[2]: {"type": "MISALIGNED", "shift": (12, -4)}}}
        ]

        for var in variations:
            split = var["split"]
            fname = f"{bkey}_{var['id']}.png"
            target_file = OUTPUT_DIR / split / bkey / fname
            defects = var["defects"]

            inject_defects_and_save(
                base_img,
                comps,
                patches,
                target_file,
                defects=defects,
                global_shift=var.get("shift", (0, 0)),
                global_rotation=var.get("rot", 0.0),
                glare_pos=var.get("glare"),
                brightness_mult=var.get("gain", 1.0)
            )

            total_images += 1
            if split == "train":
                train_count += 1
            else:
                test_count += 1

            has_defects = len(defects) > 0
            expected_board_status = "DEFECT" if has_defects else "OK"

            gt_manifest["images"][str(target_file.relative_to(OUTPUT_DIR))] = {
                "board_type": bkey,
                "split": split,
                "expected_board_status": expected_board_status,
                "defects": defects,
                "defect_counts": {
                    "missing": len([c for c, d in defects.items() if d["type"] == "MISSING"]),
                    "tilted": len([c for c, d in defects.items() if d["type"] == "TILTED"]),
                    "misaligned": len([c for c, d in defects.items() if d["type"] == "MISALIGNED"]),
                }
            }

    # Save master ground truth
    gt_path = OUTPUT_DIR / "ground_truth_multiboard.json"
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(gt_manifest, f, indent=2)

    print("\n" + "=" * 80)
    print("DATASET GENERATION COMPLETE")
    print("=" * 80)
    print(f"Total Boards Generated : {total_images}")
    print(f"Training Split (70%)   : {train_count} ({train_count / total_images * 100:.1f}%)")
    print(f"Testing Split (30%)    : {test_count} ({test_count / total_images * 100:.1f}%)")
    print(f"Master Ground Truth    : {gt_path}")


if __name__ == "__main__":
    generate_full_dataset()
