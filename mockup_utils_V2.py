from PIL import Image
import os
from template_coordinates import TEMPLATE_COORDINATES
import numpy as np
import cv2

def generate_filename(template_name, client_name, campaign_name, live_date):
    site = template_name.replace(".png", "")
    filename = f"{site} - {client_name} - {campaign_name} - {live_date} - Mock.jpg"
    return filename

def generate_mockup(template_path, artwork_path, output_path, coords):
    try:
        template = Image.open(template_path).convert("RGBA")
        artwork = Image.open(artwork_path).convert("RGBA")

        src_coords = [(0, 0), (artwork.width, 0), (artwork.width, artwork.height), (0, artwork.height)]
        dst_coords = coords

        if len(dst_coords) != 4:
            raise ValueError("Template coordinates must contain exactly 4 points.")

        coeffs = find_perspective_transform(src_coords, dst_coords)
        transformed_artwork = artwork.transform(template.size, Image.PERSPECTIVE, coeffs, Image.BICUBIC)

        base = Image.new("RGBA", template.size, (0, 0, 0, 0))
        base.paste(transformed_artwork, (0, 0), transformed_artwork)
        base.paste(template, (0, 0), template)
        base.convert("RGB").save(output_path, "JPEG", quality=95)

    except Exception as e:
        raise RuntimeError(f"Error generating mockup: {e}")

def find_perspective_transform(src, dst):
    from numpy import array, linalg

    matrix = []
    for p1, p2 in zip(dst, src):
        matrix.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0]*p1[0], -p2[0]*p1[1]])
        matrix.append([0, 0, 0, p1[0], p1[1], 1, -p2[1]*p1[0], -p2[1]*p1[1]])
    A = array(matrix)
    B = array(src).reshape(8)
    res = linalg.lstsq(A, B, rcond=None)[0]
    return res.tolist()

def warp_panel(image, src_points, dst_points, size):
    matrix = cv2.getPerspectiveTransform(np.float32(src_points), np.float32(dst_points))
    return cv2.warpPerspective(image, matrix, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_TRANSPARENT)

def split_artwork_by_ratios(artwork_img, ratios):
    total_width, height = artwork_img.size

    if len(ratios) == 3:
        lhs_ratio, mid_ratio, rhs_ratio = ratios
        lhs_width = round(total_width * lhs_ratio)
        mid_width = round(total_width * mid_ratio)
        rhs_width = total_width - lhs_width - mid_width

        lhs = artwork_img.crop((0, 0, lhs_width, height))
        mid = artwork_img.crop((lhs_width, 0, lhs_width + mid_width, height))
        rhs = artwork_img.crop((lhs_width + mid_width, 0, total_width, height))

        return [lhs, mid, rhs]

    elif len(ratios) == 2:
        lhs_ratio, rhs_ratio = ratios
        lhs_width = round(total_width * lhs_ratio)
        rhs_width = total_width - lhs_width

        lhs = artwork_img.crop((0, 0, lhs_width, height))
        rhs = artwork_img.crop((lhs_width, 0, total_width, height))

        return [lhs, rhs]

    else:
        raise ValueError("split_ratios must have 2 or 3 values")

def generate_multi_panel_mockup(template_path, artwork_path, output_path, coords):
    try:
        template = Image.open(template_path).convert("RGBA")
        artwork = Image.open(artwork_path).convert("RGBA")

        panels = [k for k in ("LHS", "MID", "RHS") if k in coords]
        split_ratios = coords.get("split_ratios")
        if not split_ratios or len(split_ratios) != len(panels):
            raise ValueError("Mismatch between split_ratios and panel keys.")

        artwork_pieces = split_artwork_by_ratios(artwork, split_ratios)
        base = Image.new("RGBA", template.size, (0, 0, 0, 0))

        for piece, key in zip(artwork_pieces, panels):
            dst = coords[key]
            src = [(0, 0), (piece.width, 0), (piece.width, piece.height), (0, piece.height)]
            piece_np = np.array(piece)
            transformed = warp_panel(piece_np, src, dst, template.size)
            transformed_img = Image.fromarray(transformed)
            base.paste(transformed_img, (0, 0), transformed_img)

        base.paste(template, (0, 0), template)
        base.convert("RGB").save(output_path, "JPEG", quality=95)

    except Exception as e:
        raise RuntimeError(f"Error generating multi-panel mockup: {e}")
