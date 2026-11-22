"""
Procedural Realistic Circuit Board Generator for Task B.
Generates:
- 1 Defect-free Reference Board
- 20 Calibration Boards (~35% complete/all-OK with varied lighting/glare; ~65% with single, adjacent, or multi-missing parts, including glare on bare pads)
- 10 Held-out Test Boards (Harder unseen set: wider camera shifts, wider exposure swings, glare on empty footprints, adjacent missing parts, distinct random seeds)
- Updated ground_truth.json with exact missing parts, pixel bboxes, normalized bboxes, and perturbation parameters.
"""

import json
import math
import os
import random
from pathlib import Path
import cv2
import numpy as np

WIDTH = 1920
HEIGHT = 1080

SAMPLE_DIR = Path("sample_data")
CALIB_DIR = SAMPLE_DIR / "calibration"
TEST_DIR = SAMPLE_DIR / "test_heldout"

# Defined circuit layout (bounding boxes in reference frame: [x, y, w, h])
COMPONENTS = {
    # Main Microcontroller (QFP package with perimeter pins)
    "U1_MCU": {
        "type": "QFP32",
        "bbox": [580, 400, 200, 200],
        "label": "STM32F4",
        "pins": 32,
    },
    # Voltage Regulator (SOT-223 package)
    "U2_REG": {
        "type": "SOT223",
        "bbox": [940, 440, 140, 100],
        "label": "AMS1117",
        "pins": 4,
    },
    # EEPROM / Memory chip (SOIC-8 package)
    "U3_EEPROM": {
        "type": "SOIC8",
        "bbox": [940, 620, 120, 90],
        "label": "24C08",
        "pins": 8,
    },
    # Bank of identical decoupling capacitors (placed in a tight row)
    "C1_DECOUP": {
        "type": "C0805",
        "bbox": [480, 410, 50, 30],
        "label": "C1",
    },
    "C2_DECOUP": {
        "type": "C0805",
        "bbox": [480, 470, 50, 30],
        "label": "C2",
    },
    "C3_DECOUP": {
        "type": "C0805",
        "bbox": [480, 530, 50, 30],
        "label": "C3",
    },
    # Bank of identical pull-up resistors (placed in a tight row)
    "R1_PULLUP": {
        "type": "R0805",
        "bbox": [820, 410, 50, 28],
        "label": "R1",
        "code": "103",
    },
    "R2_PULLUP": {
        "type": "R0805",
        "bbox": [820, 460, 50, 28],
        "label": "R2",
        "code": "103",
    },
    "R3_PULLUP": {
        "type": "R0805",
        "bbox": [820, 510, 50, 28],
        "label": "R3",
        "code": "103",
    },
    "R4_PULLUP": {
        "type": "R0805",
        "bbox": [820, 560, 50, 28],
        "label": "R4",
        "code": "103",
    },
    # Power filtering electrolytic capacitor
    "C4_BULK": {
        "type": "ELEC_CAN",
        "bbox": [1160, 420, 110, 110],
        "label": "100uF",
    },
    # Surface mount diode
    "D1_LED": {
        "type": "SMD_LED",
        "bbox": [1160, 580, 60, 35],
        "label": "D1_PWR",
    },
    # Current sense power resistor
    "R5_SHUNTR": {
        "type": "R1206",
        "bbox": [940, 280, 80, 45],
        "label": "R5",
        "code": "R010",
    },
    # High-frequency crystal oscillator
    "Y1_XTAL": {
        "type": "XTAL_CAN",
        "bbox": [580, 280, 130, 65],
        "label": "16.000",
    },
}


def draw_pcb_base():
    """Generates the bare PCB substrate, copper traces, ground pours, and vias."""
    base = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    base[:, :] = (24, 78, 40)

    # Subtle woven fiberglass texture
    noise_grid = np.random.normal(0, 4, (HEIGHT, WIDTH)).astype(np.float32)
    x_coords = np.arange(WIDTH)
    y_coords = np.arange(HEIGHT)
    weave_x = np.sin(x_coords / 2.0) * 2.5
    weave_y = np.cos(y_coords / 2.0) * 2.5
    weave = weave_x[None, :] + weave_y[:, None] + noise_grid
    base = np.clip(base.astype(np.float32) + weave[:, :, None], 0, 255).astype(np.uint8)

    # Copper traces underneath the solder mask
    trace_layer = np.zeros_like(base)
    traces = [
        [(400, 425), (460, 425)],
        [(400, 485), (460, 485)],
        [(400, 545), (460, 545)],
        [(530, 425), (580, 425)],
        [(530, 485), (580, 485)],
        [(530, 545), (580, 545)],
        [(780, 425), (820, 425)],
        [(780, 475), (820, 475)],
        [(780, 525), (820, 525)],
        [(780, 575), (820, 575)],
        [(870, 425), (940, 425)],
        [(870, 475), (940, 475)],
        [(780, 500), (900, 500), (940, 470)],
        [(710, 312), (710, 400)],
        [(645, 345), (645, 400)],
        [(1080, 460), (1160, 460)],
        [(1060, 665), (1160, 665), (1160, 615)],
        [(980, 325), (980, 440)],
    ]
    for pts in traces:
        for i in range(len(pts) - 1):
            cv2.line(trace_layer, pts[i], pts[i + 1], (38, 115, 62), 4, cv2.LINE_AA)

    # Ground plane copper hatching
    for y in range(150, HEIGHT - 150, 80):
        cv2.line(trace_layer, (150, y), (WIDTH - 150, y), (30, 95, 50), 1, cv2.LINE_AA)
    for x in range(150, WIDTH - 150, 80):
        cv2.line(trace_layer, (x, 150), (x, HEIGHT - 150), (30, 95, 50), 1, cv2.LINE_AA)

    mask = cv2.cvtColor(trace_layer, cv2.COLOR_BGR2GRAY) > 0
    base[mask] = trace_layer[mask]

    # Vias
    vias = [
        (450, 400), (450, 460), (450, 520), (550, 380), (790, 390),
        (890, 410), (910, 530), (1120, 430), (1120, 550), (730, 290),
        (560, 310), (1030, 380), (1120, 650), (1250, 450), (1250, 600)
    ]
    for vx, vy in vias:
        cv2.circle(base, (vx, vy), 7, (45, 140, 80), -1, cv2.LINE_AA)
        cv2.circle(base, (vx, vy), 5, (160, 175, 185), -1, cv2.LINE_AA)
        cv2.circle(base, (vx, vy), 3, (12, 16, 20), -1, cv2.LINE_AA)

    # Silkscreen board text
    cv2.putText(base, "INDUSTRIAL SENSOR CONTROLLER REV 2.1", (400, 220),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (230, 235, 230), 2, cv2.LINE_AA)
    cv2.putText(base, "GND", (390, 380), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 235, 230), 1, cv2.LINE_AA)
    cv2.putText(base, "+3V3", (390, 580), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 235, 230), 1, cv2.LINE_AA)

    # Optical fiducial alignment marks
    for fx, fy in [(220, 200), (WIDTH - 220, 200), (220, HEIGHT - 200), (WIDTH - 220, HEIGHT - 200)]:
        cv2.circle(base, (fx, fy), 14, (24, 78, 40), -1)
        cv2.circle(base, (fx, fy), 10, (190, 200, 210), -1, cv2.LINE_AA)
        cv2.circle(base, (fx, fy), 4, (24, 78, 40), -1, cv2.LINE_AA)
        cv2.rectangle(base, (fx - 18, fy - 18), (fx + 18, fy + 18), (230, 235, 230), 1, cv2.LINE_AA)

    return base


def draw_exposed_pads_and_silkscreen(img, comp_id, info):
    """Renders bare solder pads and silkscreen outlines exposed when component is missing."""
    x, y, w, h = info["bbox"]
    ctype = info["type"]

    # Silkscreen outline
    cv2.rectangle(img, (x - 3, y - 3), (x + w + 3, y + h + 3), (225, 230, 225), 1, cv2.LINE_AA)
    cv2.putText(img, info["label"], (x, y - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (225, 230, 225), 1, cv2.LINE_AA)

    pad_color = (195, 205, 215)
    pad_border = (140, 150, 160)

    if ctype in ("C0805", "R0805"):
        pad_w = 12
        cv2.rectangle(img, (x, y + 2), (x + pad_w, y + h - 2), pad_color, -1)
        cv2.rectangle(img, (x, y + 2), (x + pad_w, y + h - 2), pad_border, 1)
        cv2.rectangle(img, (x + w - pad_w, y + 2), (x + w, y + h - 2), pad_color, -1)
        cv2.rectangle(img, (x + w - pad_w, y + 2), (x + w, y + h - 2), pad_border, 1)

    elif ctype == "R1206":
        pad_w = 16
        cv2.rectangle(img, (x, y + 3), (x + pad_w, y + h - 3), pad_color, -1)
        cv2.rectangle(img, (x, y + 3), (x + pad_w, y + h - 3), pad_border, 1)
        cv2.rectangle(img, (x + w - pad_w, y + 3), (x + w, y + h - 3), pad_color, -1)
        cv2.rectangle(img, (x + w - pad_w, y + 3), (x + w, y + h - 3), pad_border, 1)

    elif ctype == "SMD_LED":
        pad_w = 14
        cv2.rectangle(img, (x, y + 4), (x + pad_w, y + h - 4), pad_color, -1)
        cv2.rectangle(img, (x + w - pad_w, y + 4), (x + w, y + h - 4), pad_color, -1)
        cv2.line(img, (x + w + 2, y), (x + w + 2, y + h), (230, 235, 230), 2, cv2.LINE_AA)

    elif ctype == "QFP32":
        num_pads = 8
        spacing = (w - 40) // (num_pads - 1)
        for i in range(num_pads):
            px = x + 20 + i * spacing
            cv2.rectangle(img, (px - 4, y - 8), (px + 4, y + 6), pad_color, -1)
            cv2.rectangle(img, (px - 4, y + h - 6), (px + 4, y + h + 8), pad_color, -1)
        spacing_y = (h - 40) // (num_pads - 1)
        for i in range(num_pads):
            py = y + 20 + i * spacing_y
            cv2.rectangle(img, (x - 8, py - 4), (x + 6, py + 4), pad_color, -1)
            cv2.rectangle(img, (x + w - 6, py - 4), (x + w + 8, py + 4), pad_color, -1)
        cv2.circle(img, (x - 14, y - 14), 4, (230, 235, 230), -1, cv2.LINE_AA)
        cv2.rectangle(img, (x + 35, y + 35), (x + w - 35, y + h - 35), (170, 180, 190), -1)
        cv2.rectangle(img, (x + 35, y + 35), (x + w - 35, y + h - 35), pad_border, 1)

    elif ctype == "SOIC8":
        spacing_y = (h - 20) // 3
        for i in range(4):
            py = y + 10 + i * spacing_y
            cv2.rectangle(img, (x - 6, py - 5), (x + 8, py + 5), pad_color, -1)
            cv2.rectangle(img, (x + w - 8, py - 5), (x + w + 6, py + 5), pad_color, -1)
        cv2.circle(img, (x - 10, y - 10), 3, (230, 235, 230), -1, cv2.LINE_AA)

    elif ctype == "SOT223":
        cv2.rectangle(img, (x + 30, y - 8), (x + w - 30, y + 10), pad_color, -1)
        spacing_x = (w - 30) // 2
        for i in range(3):
            px = x + 15 + i * spacing_x
            cv2.rectangle(img, (px - 8, y + h - 10), (px + 8, y + h + 8), pad_color, -1)

    elif ctype == "ELEC_CAN":
        cv2.circle(img, (x + w // 2, y + h // 2), w // 2 + 2, (225, 230, 225), 1, cv2.LINE_AA)
        cv2.rectangle(img, (x + 10, y + h // 2 - 12), (x + 28, y + h // 2 + 12), pad_color, -1)
        cv2.rectangle(img, (x + w - 28, y + h // 2 - 12), (x + w - 10, y + h // 2 + 12), pad_color, -1)

    elif ctype == "XTAL_CAN":
        cv2.rectangle(img, (x, y), (x + w, y + h), (225, 230, 225), 1, cv2.LINE_AA)
        cv2.rectangle(img, (x + 8, y + 8), (x + 24, y + 24), pad_color, -1)
        cv2.rectangle(img, (x + w - 24, y + h - 24), (x + w - 8, y + h - 8), pad_color, -1)


def draw_component_present(img, comp_id, info):
    """Renders the mounted physical component."""
    x, y, w, h = info["bbox"]
    ctype = info["type"]

    if ctype == "C0805":
        cv2.rectangle(img, (x + 4, y + 3), (x + w - 4, y + h - 3), (95, 135, 175), -1)
        cv2.rectangle(img, (x + 2, y + 3), (x + 11, y + h - 3), (205, 215, 225), -1)
        cv2.rectangle(img, (x + w - 11, y + 3), (x + w - 2, y + h - 3), (205, 215, 225), -1)
        cv2.line(img, (x + 4, y + 4), (x + w - 4, y + 4), (130, 170, 210), 1)

    elif ctype == "R0805":
        cv2.rectangle(img, (x + 4, y + 3), (x + w - 4, y + h - 3), (30, 32, 35), -1)
        cv2.rectangle(img, (x + 2, y + 3), (x + 10, y + h - 3), (200, 210, 220), -1)
        cv2.rectangle(img, (x + w - 10, y + 3), (x + w - 2, y + h - 3), (200, 210, 220), -1)
        if "code" in info:
            cv2.putText(img, info["code"], (x + 13, y + h - 9),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, (220, 220, 220), 1, cv2.LINE_AA)

    elif ctype == "R1206":
        cv2.rectangle(img, (x + 6, y + 4), (x + w - 6, y + h - 4), (28, 30, 32), -1)
        cv2.rectangle(img, (x + 3, y + 4), (x + 14, y + h - 4), (205, 215, 225), -1)
        cv2.rectangle(img, (x + w - 14, y + 4), (x + w - 3, y + h - 4), (205, 215, 225), -1)
        if "code" in info:
            cv2.putText(img, info["code"], (x + 18, y + h - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 230, 230), 1, cv2.LINE_AA)

    elif ctype == "SMD_LED":
        cv2.rectangle(img, (x + 5, y + 4), (x + w - 5, y + h - 4), (50, 160, 70), -1)
        cv2.rectangle(img, (x + 2, y + 4), (x + 10, y + h - 4), (205, 215, 225), -1)
        cv2.rectangle(img, (x + w - 10, y + 4), (x + w - 2, y + h - 4), (205, 215, 225), -1)
        cv2.circle(img, (x + w // 2, y + h // 2), 6, (90, 220, 120), -1, cv2.LINE_AA)

    elif ctype == "QFP32":
        num_pins = 8
        spacing = (w - 40) // (num_pins - 1)
        for i in range(num_pins):
            px = x + 20 + i * spacing
            cv2.line(img, (px, y - 6), (px, y + 15), (210, 220, 230), 3, cv2.LINE_AA)
            cv2.line(img, (px, y + h - 15), (px, y + h + 6), (210, 220, 230), 3, cv2.LINE_AA)
        spacing_y = (h - 40) // (num_pins - 1)
        for i in range(num_pins):
            py = y + 20 + i * spacing_y
            cv2.line(img, (x - 6, py), (x + 15, py), (210, 220, 230), 3, cv2.LINE_AA)
            cv2.line(img, (x + w - 15, py), (x + w + 6, py), (210, 220, 230), 3, cv2.LINE_AA)

        cv2.rectangle(img, (x + 12, y + 12), (x + w - 12, y + h - 12), (32, 34, 38), -1)
        cv2.rectangle(img, (x + 16, y + 16), (x + w - 16, y + h - 16), (42, 45, 50), 1)
        cv2.circle(img, (x + 28, y + 28), 6, (20, 22, 25), -1, cv2.LINE_AA)
        cv2.circle(img, (x + 28, y + 28), 6, (60, 65, 72), 1, cv2.LINE_AA)
        cv2.putText(img, "ARM", (x + 40, y + 70), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (140, 145, 150), 1, cv2.LINE_AA)
        cv2.putText(img, info["label"], (x + 40, y + 105), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (160, 165, 170), 2, cv2.LINE_AA)
        cv2.putText(img, "94V-0 2341", (x + 40, y + 135), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 125, 130), 1, cv2.LINE_AA)

    elif ctype == "SOIC8":
        spacing_y = (h - 20) // 3
        for i in range(4):
            py = y + 10 + i * spacing_y
            cv2.line(img, (x - 5, py), (x + 10, py), (210, 220, 230), 3, cv2.LINE_AA)
            cv2.line(img, (x + w - 10, py), (x + w + 5, py), (210, 220, 230), 3, cv2.LINE_AA)
        cv2.rectangle(img, (x + 8, y + 4), (x + w - 8, y + h - 4), (32, 34, 38), -1)
        cv2.circle(img, (x + 16, y + 14), 4, (20, 22, 25), -1, cv2.LINE_AA)
        cv2.putText(img, info["label"], (x + 24, y + h // 2 + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 155, 160), 1, cv2.LINE_AA)

    elif ctype == "SOT223":
        cv2.rectangle(img, (x + 30, y - 6), (x + w - 30, y + 10), (210, 220, 230), -1)
        spacing_x = (w - 30) // 2
        for i in range(3):
            px = x + 15 + i * spacing_x
            cv2.rectangle(img, (px - 6, y + h - 10), (px + 6, y + h + 6), (210, 220, 230), -1)
        cv2.rectangle(img, (x + 8, y + 8), (x + w - 8, y + h - 8), (30, 32, 36), -1)
        cv2.putText(img, info["label"], (x + 18, y + h // 2 + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 165, 170), 1, cv2.LINE_AA)

    elif ctype == "ELEC_CAN":
        cx, cy = x + w // 2, y + h // 2
        radius = w // 2 - 4
        cv2.circle(img, (cx, cy), radius, (190, 195, 205), -1, cv2.LINE_AA)
        cv2.ellipse(img, (cx, cy), (radius, radius), 0, -90, 90, (35, 38, 42), -1)
        cv2.putText(img, "-", (cx + radius // 2 - 6, cy + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (230, 230, 230), 2, cv2.LINE_AA)
        cv2.putText(img, info["label"], (cx - radius + 10, cy + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 25, 30), 1, cv2.LINE_AA)

    elif ctype == "XTAL_CAN":
        cv2.rectangle(img, (x + 6, y + 6), (x + w - 6, y + h - 6), (195, 205, 215), -1)
        cv2.rectangle(img, (x + 6, y + 6), (x + w - 6, y + h - 6), (150, 160, 170), 2)
        cv2.putText(img, info["label"], (x + 16, y + h // 2 + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (40, 45, 50), 1, cv2.LINE_AA)


def build_board_image(missing_parts=None):
    """Assembles a board image with all components present, minus any in missing_parts."""
    if missing_parts is None:
        missing_parts = set()
    else:
        missing_parts = set(missing_parts)

    img = draw_pcb_base()
    for comp_id, info in COMPONENTS.items():
        draw_exposed_pads_and_silkscreen(img, comp_id, info)
    for comp_id, info in COMPONENTS.items():
        if comp_id not in missing_parts:
            draw_component_present(img, comp_id, info)

    return img


def apply_camera_perturbations(img, dx=0.0, dy=0.0, angle_deg=0.0,
                               gain=1.0, bias=0, glare_points=None, blur_sigma=0.0):
    """Applies realistic physical imaging perturbations."""
    h, w = img.shape[:2]

    # Rigid shift / rotation
    center = (w / 2.0, h / 2.0)
    rot_mat = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    rot_mat[0, 2] += dx
    rot_mat[1, 2] += dy
    warped = cv2.warpAffine(img, rot_mat, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)

    # Lighting gain & bias
    adjusted = warped.astype(np.float32) * gain + bias

    # Glare spots
    if glare_points:
        glare_mask = np.zeros((h, w), dtype=np.float32)
        for gx, gy, radius, intensity in glare_points:
            pt = rot_mat @ np.array([gx, gy, 1.0])
            tgx, tgy = int(pt[0]), int(pt[1])
            if 0 <= tgx < w and 0 <= tgy < h:
                y_grid, x_grid = np.ogrid[-tgy:h - tgy, -tgx:w - tgx]
                dist_sq = x_grid * x_grid + y_grid * y_grid
                spot = intensity * np.exp(-dist_sq / (2.0 * radius * radius))
                glare_mask = np.maximum(glare_mask, spot)
        adjusted += glare_mask[:, :, None]

    # Defocus blur
    if blur_sigma > 0:
        ksize = int(blur_sigma * 4) | 1
        adjusted = cv2.GaussianBlur(adjusted, (ksize, ksize), blur_sigma)

    # Sensor grain
    noise = np.random.normal(0, 3.2, (h, w, 3)).astype(np.float32)
    adjusted += noise

    return np.clip(adjusted, 0, 255).astype(np.uint8)


def generate_all_samples():
    """Generates the reference board, 20 calibration boards, 10 held-out test boards."""
    os.makedirs(CALIB_DIR, exist_ok=True)
    os.makedirs(TEST_DIR, exist_ok=True)

    ground_truth = {
        "board_info": {
            "name": "Industrial Sensor Controller Rev 2.1",
            "resolution": [WIDTH, HEIGHT],
            "total_components": len(COMPONENTS),
        },
        "components": {},
        "images": {},
    }

    for cid, info in COMPONENTS.items():
        x, y, w, h = info["bbox"]
        ground_truth["components"][cid] = {
            "type": info["type"],
            "label": info["label"],
            "pixel_bbox": [x, y, w, h],
            "normalized_bbox": [
                round(x / WIDTH, 6),
                round(y / HEIGHT, 6),
                round(w / WIDTH, 6),
                round(h / HEIGHT, 6),
            ],
        }

    # -------------------------------------------------------------
    # 1. Reference Board
    # -------------------------------------------------------------
    print("Generating reference good board...")
    np.random.seed(100)
    ref_clean = build_board_image(missing_parts=set())
    ref_photo = apply_camera_perturbations(ref_clean, dx=0, dy=0, angle_deg=0, gain=1.0, bias=0)
    ref_path = SAMPLE_DIR / "reference.png"
    cv2.imwrite(str(ref_path), ref_photo)

    ground_truth["images"]["reference.png"] = {
        "split": "reference",
        "relative_path": "reference.png",
        "missing_parts": [],
        "present_parts": list(COMPONENTS.keys()),
        "expected_board_status": "OK",
        "perturbations": {"dx": 0, "dy": 0, "angle_deg": 0.0, "gain": 1.0, "bias": 0},
    }

    # -------------------------------------------------------------
    # 2. Calibration Set (20 images: 7 complete boards, 13 defective)
    # -------------------------------------------------------------
    print("Generating calibration set (20 boards)...")
    np.random.seed(101)
    random.seed(101)

    calib_specs = [
        # --- Complete Boards (7 boards: ~35% of set) ---
        {"name": "calib_01_all_ok_nominal.png", "missing": [], "dx": 1.5, "dy": -1.2, "angle": 0.15, "gain": 1.02, "bias": 4, "glare": None, "blur": 0.0},
        {"name": "calib_02_all_ok_shift_pos.png", "missing": [], "dx": 3.2, "dy": 2.8, "angle": 0.35, "gain": 0.98, "bias": -3, "glare": None, "blur": 0.3},
        {"name": "calib_03_all_ok_shift_neg.png", "missing": [], "dx": -3.8, "dy": -2.6, "angle": -0.40, "gain": 1.05, "bias": 6, "glare": None, "blur": 0.2},
        {"name": "calib_04_all_ok_bright.png", "missing": [], "dx": 2.0, "dy": -3.0, "angle": -0.25, "gain": 1.12, "bias": 14, "glare": None, "blur": 0.0},
        {"name": "calib_05_all_ok_dim.png", "missing": [], "dx": -2.4, "dy": 1.8, "angle": 0.22, "gain": 0.90, "bias": -12, "glare": None, "blur": 0.4},
        {"name": "calib_06_all_ok_glare_mcu.png", "missing": [], "dx": 1.8, "dy": 0.8, "angle": 0.18, "gain": 1.06, "bias": 8, "glare": [(680, 500, 55, 75.0)], "blur": 0.3},
        {"name": "calib_07_all_ok_glare_passives.png", "missing": [], "dx": -3.1, "dy": 3.4, "angle": -0.32, "gain": 1.08, "bias": 10, "glare": [(480, 440, 40, 65.0), (820, 460, 35, 60.0)], "blur": 0.5},

        # --- Single Missing Parts (4 boards) ---
        {"name": "calib_08_missing_u1_mcu.png", "missing": ["U1_MCU"], "dx": 1.2, "dy": 2.4, "angle": 0.20, "gain": 1.04, "bias": 6, "glare": None, "blur": 0.0},
        {"name": "calib_09_missing_c1.png", "missing": ["C1_DECOUP"], "dx": -2.0, "dy": -1.5, "angle": -0.18, "gain": 0.96, "bias": -4, "glare": None, "blur": 0.0},
        {"name": "calib_10_missing_r3.png", "missing": ["R3_PULLUP"], "dx": 2.5, "dy": -2.2, "angle": 0.28, "gain": 1.02, "bias": 5, "glare": None, "blur": 0.2},
        {"name": "calib_11_missing_y1_xtal.png", "missing": ["Y1_XTAL"], "dx": -1.5, "dy": 3.1, "angle": -0.22, "gain": 0.94, "bias": -8, "glare": None, "blur": 0.3},

        # --- Adjacent Missing Parts (4 boards) ---
        {"name": "calib_12_missing_adj_c1_c2.png", "missing": ["C1_DECOUP", "C2_DECOUP"], "dx": -2.8, "dy": 1.5, "angle": -0.30, "gain": 1.00, "bias": 0, "glare": None, "blur": 0.2},
        {"name": "calib_13_missing_adj_r1_r2.png", "missing": ["R1_PULLUP", "R2_PULLUP"], "dx": 3.0, "dy": -1.8, "angle": 0.32, "gain": 1.05, "bias": 6, "glare": None, "blur": 0.0},
        {"name": "calib_14_missing_adj_r3_r4.png", "missing": ["R3_PULLUP", "R4_PULLUP"], "dx": -1.2, "dy": -2.8, "angle": -0.15, "gain": 0.92, "bias": -10, "glare": None, "blur": 0.4},
        {"name": "calib_15_missing_adj_c2_c3.png", "missing": ["C2_DECOUP", "C3_DECOUP"], "dx": 2.2, "dy": 2.0, "angle": 0.25, "gain": 1.03, "bias": 4, "glare": None, "blur": 0.2},

        # --- Glare Directly on Bare Footprints (3 boards) ---
        {"name": "calib_16_missing_c2_glare_on_pad.png", "missing": ["C2_DECOUP"], "dx": 1.6, "dy": -1.4, "angle": 0.16, "gain": 1.07, "bias": 10, "glare": [(480, 470, 25, 70.0)], "blur": 0.3},
        {"name": "calib_17_missing_u2_glare_on_tab.png", "missing": ["U2_REG"], "dx": -2.5, "dy": 2.2, "angle": -0.28, "gain": 1.09, "bias": 12, "glare": [(990, 440, 40, 75.0)], "blur": 0.2},
        {"name": "calib_18_missing_r1_glare_on_pad.png", "missing": ["R1_PULLUP"], "dx": 2.8, "dy": -2.5, "angle": 0.30, "gain": 1.06, "bias": 8, "glare": [(820, 410, 22, 65.0)], "blur": 0.0},

        # --- Multi-Component Mixed Deficiencies (2 boards) ---
        {"name": "calib_19_missing_c4_d1.png", "missing": ["C4_BULK", "D1_LED"], "dx": -3.5, "dy": -1.8, "angle": -0.38, "gain": 0.95, "bias": -6, "glare": None, "blur": 0.3},
        {"name": "calib_20_missing_u3_r5_c3.png", "missing": ["U3_EEPROM", "R5_SHUNTR", "C3_DECOUP"], "dx": 3.8, "dy": 2.5, "angle": 0.42, "gain": 1.10, "bias": 12, "glare": [(940, 620, 35, 55.0)], "blur": 0.4},
    ]

    for spec in calib_specs:
        raw = build_board_image(missing_parts=spec["missing"])
        perturbed = apply_camera_perturbations(
            raw,
            dx=spec["dx"],
            dy=spec["dy"],
            angle_deg=spec["angle"],
            gain=spec["gain"],
            bias=spec["bias"],
            glare_points=spec["glare"],
            blur_sigma=spec["blur"],
        )
        save_path = CALIB_DIR / spec["name"]
        cv2.imwrite(str(save_path), perturbed)

        missing = spec["missing"]
        present = [c for c in COMPONENTS if c not in missing]
        ground_truth["images"][f"calibration/{spec['name']}"] = {
            "split": "calibration",
            "relative_path": f"calibration/{spec['name']}",
            "missing_parts": missing,
            "present_parts": present,
            "expected_board_status": "DEFECT" if missing else "OK",
            "perturbations": {
                "dx": spec["dx"], "dy": spec["dy"], "angle_deg": spec["angle"],
                "gain": spec["gain"], "bias": spec["bias"],
            },
        }

    # -------------------------------------------------------------
    # 3. Held-Out Test Set (10 images: 3 complete, 7 defective)
    # Different random seeds & WIDER perturbation ranges
    # -------------------------------------------------------------
    print("Generating held-out test set (10 boards with wider perturbations)...")
    np.random.seed(303)  # Distinct seed
    random.seed(303)

    test_specs = [
        # --- Complete Boards (3 boards: 30% of test set) ---
        {
            "name": "test_01_all_ok_max_shift.png",
            "missing": [],
            "dx": 6.2, "dy": -5.4, "angle": 0.78,  # Near maximum plausible alignment shift
            "gain": 1.04, "bias": 6,
            "glare": None, "blur": 0.4,
        },
        {
            "name": "test_02_all_ok_dim_underexposed.png",
            "missing": [],
            "dx": -5.5, "dy": 4.8, "angle": -0.68,
            "gain": 0.84, "bias": -18,  # Distinctly underexposed
            "glare": None, "blur": 0.5,
        },
        {
            "name": "test_03_all_ok_severe_dual_glare.png",
            "missing": [],
            "dx": 2.4, "dy": -3.2, "angle": 0.35,
            "gain": 1.18, "bias": 22,  # Overexposed with two hot glare spots
            "glare": [(680, 480, 75, 95.0), (1160, 440, 50, 85.0)],
            "blur": 0.6,
        },

        # --- Adjacent Missing Components (2 boards) ---
        {
            "name": "test_04_missing_adj_c1_c2.png",
            "missing": ["C1_DECOUP", "C2_DECOUP"],
            "dx": -4.8, "dy": -5.1, "angle": -0.65,
            "gain": 0.92, "bias": -10,
            "glare": None, "blur": 0.3,
        },
        {
            "name": "test_05_missing_adj_r2_r3_r4.png",
            "missing": ["R2_PULLUP", "R3_PULLUP", "R4_PULLUP"],  # 3 adjacent resistors missing in a row
            "dx": 5.0, "dy": 3.8, "angle": 0.62,
            "gain": 1.06, "bias": 8,
            "glare": None, "blur": 0.2,
        },

        # --- Glare Directly on Bare Missing Footprints (2 boards) ---
        {
            "name": "test_06_missing_u1_glare_on_bare_pads.png",
            "missing": ["U1_MCU"],
            "dx": 3.4, "dy": -4.2, "angle": 0.48,
            "gain": 1.12, "bias": 15,
            "glare": [(680, 500, 65, 90.0)],  # Glare directly covering exposed pads of missing MCU
            "blur": 0.4,
        },
        {
            "name": "test_07_missing_c3_glare_on_pad.png",
            "missing": ["C3_DECOUP"],
            "dx": -5.8, "dy": 2.6, "angle": -0.72,
            "gain": 1.08, "bias": 10,
            "glare": [(480, 530, 28, 80.0)],  # Glare directly on C3 exposed solder pad
            "blur": 0.3,
        },

        # --- Isolated Single & Multi Missing Components (3 boards) ---
        {
            "name": "test_08_missing_u2_regulator.png",
            "missing": ["U2_REG"],
            "dx": -3.8, "dy": 5.6, "angle": -0.55,
            "gain": 0.88, "bias": -14,
            "glare": None, "blur": 0.5,
        },
        {
            "name": "test_09_missing_d1_led_y1_xtal.png",
            "missing": ["D1_LED", "Y1_XTAL"],
            "dx": 5.6, "dy": -4.8, "angle": 0.70,
            "gain": 1.14, "bias": 16,
            "glare": [(940, 280, 35, 60.0)],
            "blur": 0.4,
        },
        {
            "name": "test_10_missing_multi_scattered.png",
            "missing": ["C4_BULK", "R5_SHUNTR", "U3_EEPROM", "C1_DECOUP"],
            "dx": -6.4, "dy": -5.8, "angle": -0.85,  # Maximum extreme test shift
            "gain": 0.90, "bias": -12,
            "glare": [(820, 460, 30, 65.0)],
            "blur": 0.6,
        },
    ]

    for spec in test_specs:
        raw = build_board_image(missing_parts=spec["missing"])
        perturbed = apply_camera_perturbations(
            raw,
            dx=spec["dx"],
            dy=spec["dy"],
            angle_deg=spec["angle"],
            gain=spec["gain"],
            bias=spec["bias"],
            glare_points=spec["glare"],
            blur_sigma=spec["blur"],
        )
        save_path = TEST_DIR / spec["name"]
        cv2.imwrite(str(save_path), perturbed)

        missing = spec["missing"]
        present = [c for c in COMPONENTS if c not in missing]
        ground_truth["images"][f"test_heldout/{spec['name']}"] = {
            "split": "test_heldout",
            "relative_path": f"test_heldout/{spec['name']}",
            "missing_parts": missing,
            "present_parts": present,
            "expected_board_status": "DEFECT" if missing else "OK",
            "perturbations": {
                "dx": spec["dx"], "dy": spec["dy"], "angle_deg": spec["angle"],
                "gain": spec["gain"], "bias": spec["bias"],
            },
        }

    # Save complete ground truth mapping
    gt_path = SAMPLE_DIR / "ground_truth.json"
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2)

    # -------------------------------------------------------------
    # Summary Metrics Calculation
    # -------------------------------------------------------------
    calib_total = len(calib_specs)
    calib_complete = sum(1 for s in calib_specs if len(s["missing"]) == 0)
    calib_defective = calib_total - calib_complete
    calib_missing_parts = sum(len(s["missing"]) for s in calib_specs)

    test_total = len(test_specs)
    test_complete = sum(1 for s in test_specs if len(s["missing"]) == 0)
    test_defective = test_total - test_complete
    test_missing_parts = sum(len(s["missing"]) for s in test_specs)

    print("\n" + "=" * 65)
    print("  SAMPLE DATASET REGENERATION SUMMARY")
    print("=" * 65)
    print(f"{'Split':<16} | {'Total Images':<12} | {'Complete (OK)':<14} | {'Defective':<10} | {'Missing Parts'}")
    print("-" * 65)
    print(f"{'Reference':<16} | {1:<12} | {1:<14} | {0:<10} | {0}")
    print(f"{'Calibration':<16} | {calib_total:<12} | {calib_complete:<14} ({calib_complete/calib_total*100:.1f}%) | {calib_defective:<10} | {calib_missing_parts}")
    print(f"{'Held-Out Test':<16} | {test_total:<12} | {test_complete:<14} ({test_complete/test_total*100:.1f}%) | {test_defective:<10} | {test_missing_parts}")
    print("-" * 65)
    print(f"{'Total Testable':<16} | {calib_total + test_total:<12} | {calib_complete + test_complete:<14} | {calib_defective + test_defective:<10} | {calib_missing_parts + test_missing_parts}")
    print("=" * 65)


if __name__ == "__main__":
    generate_all_samples()
