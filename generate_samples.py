"""
Procedural Realistic Circuit Board Generator for Task B.
Generates a reference board and challenging test boards with:
- Substrate texture, copper traces, vias, and silkscreen outlines.
- Bare solder pads revealed when components are missing.
- Similar-looking neighboring components (e.g. capacitor & resistor banks).
- Real-world perturbations: rigid camera shifts (dx, dy, rotation),
  exposure/lighting shifts, localized specular glare, and sensor noise.
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
    # Base solder mask color: Deep industrial green
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

    # Copper traces underneath the solder mask (slightly lighter/warmer green)
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

    # Add copper ground plane hatching
    for y in range(150, HEIGHT - 150, 80):
        cv2.line(trace_layer, (150, y), (WIDTH - 150, y), (30, 95, 50), 1, cv2.LINE_AA)
    for x in range(150, WIDTH - 150, 80):
        cv2.line(trace_layer, (x, 150), (x, HEIGHT - 150), (30, 95, 50), 1, cv2.LINE_AA)

    # Blend traces into base
    mask = cv2.cvtColor(trace_layer, cv2.COLOR_BGR2GRAY) > 0
    base[mask] = trace_layer[mask]

    # Draw circular vias (dark drill hole with copper/gold ring)
    vias = [
        (450, 400), (450, 460), (450, 520), (550, 380), (790, 390),
        (890, 410), (910, 530), (1120, 430), (1120, 550), (730, 290),
        (560, 310), (1030, 380), (1120, 650), (1250, 450), (1250, 600)
    ]
    for vx, vy in vias:
        cv2.circle(base, (vx, vy), 7, (45, 140, 80), -1, cv2.LINE_AA)
        cv2.circle(base, (vx, vy), 5, (160, 175, 185), -1, cv2.LINE_AA)  # tin ring
        cv2.circle(base, (vx, vy), 3, (12, 16, 20), -1, cv2.LINE_AA)     # drill hole

    # Silkscreen text (Board model, fiducials, logo)
    cv2.putText(base, "INDUSTRIAL SENSOR CONTROLLER REV 2.1", (400, 220),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (230, 235, 230), 2, cv2.LINE_AA)
    cv2.putText(base, "GND", (390, 380), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 235, 230), 1, cv2.LINE_AA)
    cv2.putText(base, "+3V3", (390, 580), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 235, 230), 1, cv2.LINE_AA)

    # Optical fiducial alignment marks on corners of board
    for fx, fy in [(220, 200), (WIDTH - 220, 200), (220, HEIGHT - 200), (WIDTH - 220, HEIGHT - 200)]:
        cv2.circle(base, (fx, fy), 14, (24, 78, 40), -1)
        cv2.circle(base, (fx, fy), 10, (190, 200, 210), -1, cv2.LINE_AA)
        cv2.circle(base, (fx, fy), 4, (24, 78, 40), -1, cv2.LINE_AA)
        cv2.rectangle(base, (fx - 18, fy - 18), (fx + 18, fy + 18), (230, 235, 230), 1, cv2.LINE_AA)

    return base


def draw_exposed_pads_and_silkscreen(img, comp_id, info):
    """
    Renders the bare exposed metal pads and silkscreen box that are visible
    when a component is MISSING.
    """
    x, y, w, h = info["bbox"]
    ctype = info["type"]

    # Silkscreen component boundary outline (crisp white)
    cv2.rectangle(img, (x - 3, y - 3), (x + w + 3, y + h + 3), (225, 230, 225), 1, cv2.LINE_AA)
    # Silkscreen component label
    cv2.putText(img, info["label"], (x, y - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (225, 230, 225), 1, cv2.LINE_AA)

    pad_color = (195, 205, 215)  # Silver/tin solder pad with flux shine
    pad_border = (140, 150, 160)

    if ctype in ("C0805", "R0805"):
        # Two rectangular solder pads on left and right
        pad_w = 12
        # Left pad
        cv2.rectangle(img, (x, y + 2), (x + pad_w, y + h - 2), pad_color, -1)
        cv2.rectangle(img, (x, y + 2), (x + pad_w, y + h - 2), pad_border, 1)
        # Right pad
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
        # Cathode silkscreen marker
        cv2.line(img, (x + w + 2, y), (x + w + 2, y + h), (230, 235, 230), 2, cv2.LINE_AA)

    elif ctype == "QFP32":
        # 8 pads per side
        num_pads = 8
        spacing = (w - 40) // (num_pads - 1)
        # Top & Bottom pads
        for i in range(num_pads):
            px = x + 20 + i * spacing
            cv2.rectangle(img, (px - 4, y - 8), (px + 4, y + 6), pad_color, -1)
            cv2.rectangle(img, (px - 4, y + h - 6), (px + 4, y + h + 8), pad_color, -1)
        # Left & Right pads
        spacing_y = (h - 40) // (num_pads - 1)
        for i in range(num_pads):
            py = y + 20 + i * spacing_y
            cv2.rectangle(img, (x - 8, py - 4), (x + 6, py + 4), pad_color, -1)
            cv2.rectangle(img, (x + w - 6, py - 4), (x + w + 8, py + 4), pad_color, -1)
        # Pin 1 silkscreen dot
        cv2.circle(img, (x - 14, y - 14), 4, (230, 235, 230), -1, cv2.LINE_AA)
        # Exposed center thermal ground pad
        cv2.rectangle(img, (x + 35, y + 35), (x + w - 35, y + h - 35), (170, 180, 190), -1)
        cv2.rectangle(img, (x + 35, y + 35), (x + w - 35, y + h - 35), pad_border, 1)

    elif ctype == "SOIC8":
        # 4 pads on left, 4 on right
        spacing_y = (h - 20) // 3
        for i in range(4):
            py = y + 10 + i * spacing_y
            cv2.rectangle(img, (x - 6, py - 5), (x + 8, py + 5), pad_color, -1)
            cv2.rectangle(img, (x + w - 8, py - 5), (x + w + 6, py + 5), pad_color, -1)
        cv2.circle(img, (x - 10, y - 10), 3, (230, 235, 230), -1, cv2.LINE_AA)

    elif ctype == "SOT223":
        # 3 small pins on bottom, 1 large thermal tab on top
        cv2.rectangle(img, (x + 25, y - 8), (x + w - 25, y + 10), pad_color, -1)  # Tab
        spacing_x = (w - 30) // 2
        for i in range(3):
            px = x + 15 + i * spacing_x
            cv2.rectangle(img, (px - 8, y + h - 10), (px + 8, y + h + 8), pad_color, -1)

    elif ctype == "ELEC_CAN":
        # Large circular base with two square solder tabs
        cv2.circle(img, (x + w // 2, y + h // 2), w // 2 + 2, (225, 230, 225), 1, cv2.LINE_AA)
        cv2.rectangle(img, (x + 10, y + h // 2 - 12), (x + 28, y + h // 2 + 12), pad_color, -1)
        cv2.rectangle(img, (x + w - 28, y + h // 2 - 12), (x + w - 10, y + h // 2 + 12), pad_color, -1)

    elif ctype == "XTAL_CAN":
        cv2.rectangle(img, (x, y), (x + w, y + h), (225, 230, 225), 1, cv2.LINE_AA)
        cv2.rectangle(img, (x + 8, y + 8), (x + 24, y + 24), pad_color, -1)
        cv2.rectangle(img, (x + w - 24, y + h - 24), (x + w - 8, y + h - 8), pad_color, -1)


def draw_component_present(img, comp_id, info):
    """Renders the physical electronic component mounted on top of the pads."""
    x, y, w, h = info["bbox"]
    ctype = info["type"]

    if ctype == "C0805":
        # Ceramic capacitor: Tan/brown center with silver metallic end-caps
        cv2.rectangle(img, (x + 4, y + 3), (x + w - 4, y + h - 3), (95, 135, 175), -1)  # Tan ceramic (BGR)
        # Silver terminations overlapping pads
        cv2.rectangle(img, (x + 2, y + 3), (x + 11, y + h - 3), (205, 215, 225), -1)
        cv2.rectangle(img, (x + w - 11, y + 3), (x + w - 2, y + h - 3), (205, 215, 225), -1)
        # Subtle 3D highlight on top edge
        cv2.line(img, (x + 4, y + 4), (x + w - 4, y + 4), (130, 170, 210), 1)

    elif ctype == "R0805":
        # SMD resistor: Matte black epoxy body with silver end-caps and white code
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
        # Clear/tinted LED body with internal gold wirebond & green glow lens
        cv2.rectangle(img, (x + 5, y + 4), (x + w - 5, y + h - 4), (50, 160, 70), -1)
        cv2.rectangle(img, (x + 2, y + 4), (x + 10, y + h - 4), (205, 215, 225), -1)
        cv2.rectangle(img, (x + w - 10, y + 4), (x + w - 2, y + h - 4), (205, 215, 225), -1)
        cv2.circle(img, (x + w // 2, y + h // 2), 6, (90, 220, 120), -1, cv2.LINE_AA)

    elif ctype == "QFP32":
        # Draw gull-wing silver pins connecting to pads
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

        # Molded dark epoxy plastic IC body
        cv2.rectangle(img, (x + 12, y + 12), (x + w - 12, y + h - 12), (32, 34, 38), -1)
        # Beveled inner border
        cv2.rectangle(img, (x + 16, y + 16), (x + w - 16, y + h - 16), (42, 45, 50), 1)
        # Pin 1 circular dimple
        cv2.circle(img, (x + 28, y + 28), 6, (20, 22, 25), -1, cv2.LINE_AA)
        cv2.circle(img, (x + 28, y + 28), 6, (60, 65, 72), 1, cv2.LINE_AA)
        # Laser marked text
        cv2.putText(img, "ARM", (x + 40, y + 70), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (140, 145, 150), 1, cv2.LINE_AA)
        cv2.putText(img, info["label"], (x + 40, y + 105), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (160, 165, 170), 2, cv2.LINE_AA)
        cv2.putText(img, "94V-0 2341", (x + 40, y + 135), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 125, 130), 1, cv2.LINE_AA)

    elif ctype == "SOIC8":
        # Pins
        spacing_y = (h - 20) // 3
        for i in range(4):
            py = y + 10 + i * spacing_y
            cv2.line(img, (x - 5, py), (x + 10, py), (210, 220, 230), 3, cv2.LINE_AA)
            cv2.line(img, (x + w - 10, py), (x + w + 5, py), (210, 220, 230), 3, cv2.LINE_AA)
        # Plastic body
        cv2.rectangle(img, (x + 8, y + 4), (x + w - 8, y + h - 4), (32, 34, 38), -1)
        cv2.circle(img, (x + 16, y + 14), 4, (20, 22, 25), -1, cv2.LINE_AA)
        cv2.putText(img, info["label"], (x + 24, y + h // 2 + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 155, 160), 1, cv2.LINE_AA)

    elif ctype == "SOT223":
        # Tab pin on top
        cv2.rectangle(img, (x + 30, y - 6), (x + w - 30, y + 10), (210, 220, 230), -1)
        # 3 leads on bottom
        spacing_x = (w - 30) // 2
        for i in range(3):
            px = x + 15 + i * spacing_x
            cv2.rectangle(img, (px - 6, y + h - 10), (px + 6, y + h + 6), (210, 220, 230), -1)
        # Main black body
        cv2.rectangle(img, (x + 8, y + 8), (x + w - 8, y + h - 8), (30, 32, 36), -1)
        cv2.putText(img, info["label"], (x + 18, y + h // 2 + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 165, 170), 1, cv2.LINE_AA)

    elif ctype == "ELEC_CAN":
        # Cylindrical aluminum capacitor can
        cx, cy = x + w // 2, y + h // 2
        radius = w // 2 - 4
        cv2.circle(img, (cx, cy), radius, (190, 195, 205), -1, cv2.LINE_AA)
        # Black polarity marking half-moon / band
        cv2.ellipse(img, (cx, cy), (radius, radius), 0, -90, 90, (35, 38, 42), -1)
        cv2.putText(img, "-", (cx + radius // 2 - 6, cy + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (230, 230, 230), 2, cv2.LINE_AA)
        cv2.putText(img, info["label"], (cx - radius + 10, cy + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 25, 30), 1, cv2.LINE_AA)

    elif ctype == "XTAL_CAN":
        # Metal can crystal oscillator
        cv2.rectangle(img, (x + 6, y + 6), (x + w - 6, y + h - 6), (195, 205, 215), -1)
        cv2.rectangle(img, (x + 6, y + 6), (x + w - 6, y + h - 6), (150, 160, 170), 2)
        cv2.putText(img, info["label"], (x + 16, y + h // 2 + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (40, 45, 50), 1, cv2.LINE_AA)


def build_board_image(missing_parts=None):
    """Assembles a board image with all components present, minus any specified in missing_parts."""
    if missing_parts is None:
        missing_parts = set()
    else:
        missing_parts = set(missing_parts)

    img = draw_pcb_base()

    # Step 1: Draw silkscreen outlines and bare solder pads for ALL components
    for comp_id, info in COMPONENTS.items():
        draw_exposed_pads_and_silkscreen(img, comp_id, info)

    # Step 2: Draw components only for those NOT marked missing
    for comp_id, info in COMPONENTS.items():
        if comp_id not in missing_parts:
            draw_component_present(img, comp_id, info)

    return img


def apply_camera_perturbations(img, dx=0.0, dy=0.0, angle_deg=0.0,
                               gain=1.0, bias=0, glare_points=None, blur_sigma=0.0):
    """
    Applies realistic physical imaging perturbations:
    - Translation (dx, dy)
    - Small camera rotation (angle_deg)
    - Exposure changes (gain, bias)
    - Localized specular glare spots
    - Defocus blur & sensor noise
    """
    h, w = img.shape[:2]

    # 1. Rigid camera shift / rotation around image center
    center = (w / 2.0, h / 2.0)
    rot_mat = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    rot_mat[0, 2] += dx
    rot_mat[1, 2] += dy
    # Warp with neutral border replication
    warped = cv2.warpAffine(img, rot_mat, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)

    # 2. Photometric shift (linear exposure gain & bias)
    adjusted = warped.astype(np.float32) * gain + bias

    # 3. Specular glare spots (radial Gaussian highlights on solder joints or glossy IC surfaces)
    if glare_points:
        glare_mask = np.zeros((h, w), dtype=np.float32)
        for gx, gy, radius, intensity in glare_points:
            # Map glare point coordinates through the camera transform
            pt = rot_mat @ np.array([gx, gy, 1.0])
            tgx, tgy = int(pt[0]), int(pt[1])
            if 0 <= tgx < w and 0 <= tgy < h:
                y_grid, x_grid = np.ogrid[-tgy:h - tgy, -tgx:w - tgx]
                dist_sq = x_grid * x_grid + y_grid * y_grid
                spot = intensity * np.exp(-dist_sq / (2.0 * radius * radius))
                glare_mask = np.maximum(glare_mask, spot)
        adjusted += glare_mask[:, :, None]

    # 4. Defocus blur (minor depth-of-field variations)
    if blur_sigma > 0:
        ksize = int(blur_sigma * 4) | 1
        adjusted = cv2.GaussianBlur(adjusted, (ksize, ksize), blur_sigma)

    # 5. CMOS sensor grain noise
    noise = np.random.normal(0, 3.2, (h, w, 3)).astype(np.float32)
    adjusted += noise

    return np.clip(adjusted, 0, 255).astype(np.uint8)


def generate_all_samples():
    """Generates the reference board, calibration set, held-out test set, and ground_truth.json."""
    os.makedirs(CALIB_DIR, exist_ok=True)
    os.makedirs(TEST_DIR, exist_ok=True)

    # Deterministic seed for reproducible evaluation data
    np.random.seed(42)
    random.seed(42)

    ground_truth = {
        "board_info": {
            "name": "Industrial Sensor Controller Rev 2.1",
            "resolution": [WIDTH, HEIGHT],
            "total_components": len(COMPONENTS),
        },
        "components": {},
        "images": {},
    }

    # Record normalized coordinates for every component
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
    # 1. Reference Board (Known-Good Board with ALL parts present)
    # -------------------------------------------------------------
    print("Generating reference good board...")
    ref_clean = build_board_image(missing_parts=set())
    # Reference photo has minimal noise and neutral exposure
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
    # 2. Calibration Set (5 images for tuning thresholds & metrics)
    # -------------------------------------------------------------
    print("Generating calibration set (5 boards)...")
    calib_specs = [
        {
            "name": "calib_01_all_ok.png",
            "missing": [],
            "dx": 2.2, "dy": -1.8, "angle": 0.25,
            "gain": 1.04, "bias": 6,
            "glare": [(940, 440, 35, 45.0)],  # mild glare on U2 regulator
            "blur": 0.4,
        },
        {
            "name": "calib_02_missing_c2_r4.png",
            "missing": ["C2_DECOUP", "R4_PULLUP"],
            "dx": -3.5, "dy": 2.1, "angle": -0.32,
            "gain": 0.94, "bias": -8,
            "glare": None,
            "blur": 0.0,
        },
        {
            "name": "calib_03_missing_u1_mcu.png",
            "missing": ["U1_MCU"],
            "dx": 1.5, "dy": 3.0, "angle": 0.18,
            "gain": 1.08, "bias": 12,
            "glare": [(680, 500, 50, 60.0)],
            "blur": 0.5,
        },
        {
            "name": "calib_04_missing_r1_c3.png",
            "missing": ["R1_PULLUP", "C3_DECOUP"],
            "dx": -2.0, "dy": -2.5, "angle": -0.22,
            "gain": 0.97, "bias": -4,
            "glare": [(820, 410, 25, 40.0)],
            "blur": 0.3,
        },
        {
            "name": "calib_05_all_ok_glare_shift.png",
            "missing": [],
            "dx": 4.1, "dy": -3.2, "angle": 0.45,
            "gain": 1.10, "bias": 15,
            "glare": [(580, 400, 60, 75.0), (1160, 420, 40, 60.0)],
            "blur": 0.6,
        },
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
    # 3. Held-Out Test Set (6 boards for blind evaluation)
    # -------------------------------------------------------------
    print("Generating held-out test set (6 boards)...")
    test_specs = [
        {
            "name": "test_01_all_ok_shifted.png",
            "missing": [],
            "dx": -4.8, "dy": 3.6, "angle": -0.55,
            "gain": 0.92, "bias": -10,
            "glare": None,
            "blur": 0.4,
        },
        {
            "name": "test_02_missing_c1.png",
            "missing": ["C1_DECOUP"],
            "dx": 2.8, "dy": -2.0, "angle": 0.30,
            "gain": 1.05, "bias": 8,
            "glare": [(480, 410, 20, 50.0)],  # Glare directly on the empty pad
            "blur": 0.2,
        },
        {
            "name": "test_03_missing_u2_r2.png",
            "missing": ["U2_REG", "R2_PULLUP"],
            "dx": -1.8, "dy": -3.5, "angle": -0.28,
            "gain": 0.89, "bias": -14,
            "glare": None,
            "blur": 0.5,
        },
        {
            "name": "test_04_missing_d1_led_y1_xtal.png",
            "missing": ["D1_LED", "Y1_XTAL"],
            "dx": 3.6, "dy": 2.4, "angle": 0.40,
            "gain": 1.07, "bias": 10,
            "glare": [(1160, 580, 25, 55.0)],
            "blur": 0.3,
        },
        {
            "name": "test_05_all_ok_high_glare.png",
            "missing": [],
            "dx": 1.2, "dy": -1.4, "angle": -0.15,
            "gain": 1.14, "bias": 18,
            "glare": [(680, 480, 70, 90.0), (940, 620, 35, 50.0)],
            "blur": 0.6,
        },
        {
            "name": "test_06_missing_multiple_components.png",
            "missing": ["C4_BULK", "R5_SHUNTR", "U3_EEPROM", "R3_PULLUP"],
            "dx": -5.2, "dy": -4.0, "angle": -0.65,
            "gain": 0.95, "bias": -6,
            "glare": [(820, 510, 30, 45.0)],
            "blur": 0.4,
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

    print(f"\nSuccessfully generated sample dataset in '{SAMPLE_DIR}':")
    print(f" - 1 Reference board ({ref_path})")
    print(f" - {len(calib_specs)} Calibration boards in {CALIB_DIR}")
    print(f" - {len(test_specs)} Held-out test boards in {TEST_DIR}")
    print(f" - Ground truth mapping saved to {gt_path}")


if __name__ == "__main__":
    generate_all_samples()
