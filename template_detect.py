"""template_detect.py

Auto-detects the transparent billboard "window" in a template PNG and
returns ordered corner coordinates — replaces manual click-point picking
(find points/click_points.py) for the single-panel case.

Detection approach:
    1. Pull the alpha channel, threshold it to isolate transparent pixels.
    2. Morphological close/open to clean anti-aliased edge noise.
    3. Find the largest contour in the cleaned mask.
    4. Reduce the contour to 4 corners (approxPolyDP, falling back to
       minAreaRect for noisy/non-quadrilateral contours).
    5. Order the 4 points TL, TR, BR, BL to match the convention already
       used throughout template_coordinates.py.

Single-panel only. Multi-panel sites (LHS/MID/RHS) are explicitly out of
scope here: checked against the real "Bendigo (Digital) Kangaroo Flat -
35553-D.png" template, the three panels turn out to be genuinely different
planes (a wraparound corner billboard), not a straight-line division of one
flat quad — and the transparent cutout in that template is a single
contiguous hole, so there isn't even separate-contour pixel evidence to
detect panel boundaries from. Any geometric interpolation would produce
confident-looking but wrong coordinates. Multi-panel corner-picking stays
manual until there's a real basis for automating it.
"""

from __future__ import annotations

import gc
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
from PIL import Image

Point = Tuple[int, int]

ALPHA_THRESHOLD = 10            # pixels with alpha below this count as "transparent"
MIN_WINDOW_AREA_RATIO = 0.002   # ignore contours smaller than 0.2% of the image area
MORPH_KERNEL_SIZE = 5


def order_points(pts: np.ndarray) -> List[Point]:
    """Order 4 points as TL, TR, BR, BL (matches template_coordinates.py convention)."""
    pts = pts.reshape(4, 2).astype(float)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).flatten()

    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]

    return [(int(round(p[0])), int(round(p[1]))) for p in (tl, tr, br, bl)]


def detect_transparent_quad(image_path: Path) -> List[Point]:
    """
    Finds the largest transparent region in a template PNG and returns its
    4 corners ordered TL, TR, BR, BL.

    Raises ValueError if no suitable transparent window is found — callers
    must surface this to the admin (e.g. generation_errors-style state),
    never swallow it.
    """
    with Image.open(image_path) as img:
        rgba = img.convert("RGBA")
        alpha = np.array(rgba.getchannel("A"), dtype=np.uint8)
        width, height = rgba.size

    mask = (alpha < ALPHA_THRESHOLD).astype(np.uint8) * 255
    del alpha

    kernel = np.ones((MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    del kernel

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    del mask

    if not contours:
        gc.collect()
        raise ValueError("No transparent window found in this template.")

    image_area = width * height
    largest = max(contours, key=cv2.contourArea)

    if cv2.contourArea(largest) < image_area * MIN_WINDOW_AREA_RATIO:
        gc.collect()
        raise ValueError("Transparent region found is too small to be a billboard window.")

    perimeter = cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, 0.02 * perimeter, True)

    if len(approx) == 4:
        quad = approx.reshape(4, 2)
    else:
        # Perspective skew or edge noise didn't reduce cleanly to 4 points —
        # fall back to the minimum-area rotated rectangle.
        rect = cv2.minAreaRect(largest)
        quad = cv2.boxPoints(rect)

    del contours, largest
    gc.collect()

    return order_points(quad)


def draw_quad_overlay(image_path: Path, quad: List[Point], max_edge: int = 1000) -> Image.Image:
    """
    Returns a downscaled RGB preview of the template with the detected quad
    drawn on top, for the admin to visually confirm before saving. Caller
    owns the returned Image and should .close() it when done.
    """
    from PIL import ImageDraw

    with Image.open(image_path) as src:
        preview = src.convert("RGB")
        scale = min(1.0, max_edge / max(preview.size))
        if scale < 1.0:
            new_size = (int(preview.width * scale), int(preview.height * scale))
            preview = preview.resize(new_size, Image.LANCZOS)

    draw = ImageDraw.Draw(preview)
    scaled_quad = [(int(x * scale), int(y * scale)) for x, y in quad]
    draw.polygon(scaled_quad, outline=(215, 223, 35), width=4)

    labels = ["TL", "TR", "BR", "BL"]
    for (x, y), label in zip(scaled_quad, labels):
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(84, 45, 84), outline=(255, 255, 255))
        draw.text((x + 8, y - 8), label, fill=(255, 255, 255))

    gc.collect()
    return preview


# --- Quality-aware template sizing ---
#
# Calibrated against a real test batch, not a theoretical guess: 8 live
# templates were composited with the same text-dense artwork and visually
# judged. Billboard-face pixel heights of 73/99/119px all looked visibly
# soft; 142/195/207/253/288px all looked fine. The cliff sits somewhere in
# the 119-142px gap. FACE_HEIGHT_TARGET_PX below is set with a margin above
# that cliff, not exactly at it, since only one confirmed-good data point
# (142px) is that close to the boundary.
FACE_HEIGHT_TARGET_PX = 250

# Floor on the OVERALL template height, independent of the face-height
# math above — protects the final mockup's resolution as a client-facing
# deliverable in its own right, since the app composites directly onto
# the template's native resolution with no separate output upscale step.
# Grounded in the low end of templates already confirmed fine in
# production use (Traralgon tested fine at 923px height); rounded up for
# a margin rather than sitting exactly at that observed floor.
MIN_TEMPLATE_HEIGHT_PX = 1200


def compute_ideal_template_height(image_height: int, quad_height: int) -> int:
    """
    Given a detected billboard face's pixel height within a template image
    of the given height, returns the ideal TEMPLATE height that would
    deliver FACE_HEIGHT_TARGET_PX of billboard-face resolution — while
    never recommending below MIN_TEMPLATE_HEIGHT_PX, which protects the
    overall mockup's quality regardless of what the face-legibility math
    alone would allow.

    Callers should never upscale to reach this value — if the source is
    already smaller, leave it as-is rather than fake quality with upscaling.
    """
    if quad_height <= 0 or image_height <= 0:
        raise ValueError("image_height and quad_height must both be positive")

    ratio = quad_height / image_height
    ideal_for_face = FACE_HEIGHT_TARGET_PX / ratio
    return max(round(ideal_for_face), MIN_TEMPLATE_HEIGHT_PX)


def scale_quad(quad: List[Point], scale: float) -> List[Point]:
    """Scales a quad's coordinates by the given factor, rounding to ints."""
    return [(round(x * scale), round(y * scale)) for x, y in quad]

