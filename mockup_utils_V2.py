from PIL import Image
import numpy as np
import cv2
import gc


def generate_filename(template_name, client_name, campaign_name, live_date):
    site = template_name.replace(".png", "")
    return f"{site} - {client_name} - {campaign_name} - {live_date} - Mock.jpg"


def warp_panel(image, src_points, dst_points, size):
    matrix = cv2.getPerspectiveTransform(np.float32(src_points), np.float32(dst_points))
    warped = cv2.warpPerspective(
        image,
        matrix,
        size,
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    del matrix
    return warped


def generate_mockup(template_path, artwork_path, output_path, coords):
    """
    Single-panel mockup using OpenCV warp for best quality + consistency with multi-panel.
    Logic:
      - artwork warped into coords
      - artwork under template
      - saved as JPEG
    """
    template = None
    artwork = None
    warped_img = None
    base = None
    rgb = None
    artwork_np = None
    warped = None

    try:
        if not isinstance(coords, (list, tuple)) or len(coords) != 4:
            raise ValueError("Template coordinates must contain exactly 4 points.")

        with Image.open(template_path) as template_src, Image.open(artwork_path) as artwork_src:
            template = template_src.convert("RGBA")
            artwork = artwork_src.convert("RGBA")

        src = [
            (0, 0),
            (artwork.width, 0),
            (artwork.width, artwork.height),
            (0, artwork.height),
        ]
        dst = coords

        artwork_np = np.array(artwork, dtype=np.uint8)
        warped = warp_panel(artwork_np, src, dst, template.size)
        warped_img = Image.fromarray(warped, mode="RGBA")

        base = Image.new("RGBA", template.size, (0, 0, 0, 0))
        base.paste(warped_img, (0, 0), warped_img)
        base.paste(template, (0, 0), template)

        rgb = base.convert("RGB")
        try:
            rgb.save(output_path, "JPEG", quality=98, subsampling=0, optimize=True)
        except TypeError:
            rgb.save(output_path, "JPEG", quality=98, optimize=True)

    except Exception as e:
        raise RuntimeError(f"Error generating mockup: {e}")

    finally:
        if rgb is not None:
            rgb.close()
        if base is not None:
            base.close()
        if warped_img is not None:
            warped_img.close()
        if artwork is not None:
            artwork.close()
        if template is not None:
            template.close()

        del artwork_np
        del warped
        gc.collect()


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

    if len(ratios) == 2:
        lhs_ratio, rhs_ratio = ratios
        lhs_width = round(total_width * lhs_ratio)
        rhs_width = total_width - lhs_width

        lhs = artwork_img.crop((0, 0, lhs_width, height))
        rhs = artwork_img.crop((lhs_width, 0, total_width, height))
        return [lhs, rhs]

    raise ValueError("split_ratios must have 2 or 3 values")


def generate_multi_panel_mockup(template_path, artwork_path, output_path, coords):
    template = None
    artwork = None
    base = None
    rgb = None
    artwork_pieces = []

    try:
        with Image.open(template_path) as template_src, Image.open(artwork_path) as artwork_src:
            template = template_src.convert("RGBA")
            artwork = artwork_src.convert("RGBA")

        split_ratios = coords.get("split_ratios")
        if not split_ratios:
            raise ValueError("Missing split_ratios for multi-panel template.")

        if len(split_ratios) == 3:
            panels = ["LHS", "MID", "RHS"]
        elif len(split_ratios) == 2:
            panels = ["LHS", "RHS"]
        else:
            raise ValueError("split_ratios must have 2 or 3 values")

        for k in panels:
            if k not in coords:
                raise ValueError(f"Missing panel coordinates for {k}")

        artwork_pieces = split_artwork_by_ratios(artwork, split_ratios)
        base = Image.new("RGBA", template.size, (0, 0, 0, 0))

        for piece, key in zip(artwork_pieces, panels):
            warped = None
            piece_np = None
            warped_img = None

            try:
                dst = coords[key]
                src = [
                    (0, 0),
                    (piece.width, 0),
                    (piece.width, piece.height),
                    (0, piece.height),
                ]

                piece_np = np.array(piece, dtype=np.uint8)
                warped = warp_panel(piece_np, src, dst, template.size)
                warped_img = Image.fromarray(warped, mode="RGBA")
                base.paste(warped_img, (0, 0), warped_img)

            finally:
                if warped_img is not None:
                    warped_img.close()
                del piece_np
                del warped
                gc.collect()

        base.paste(template, (0, 0), template)

        rgb = base.convert("RGB")
        try:
            rgb.save(output_path, "JPEG", quality=98, subsampling=0, optimize=True)
        except TypeError:
            rgb.save(output_path, "JPEG", quality=98, optimize=True)

    except Exception as e:
        raise RuntimeError(f"Error generating multi-panel mockup: {e}")

    finally:
        if rgb is not None:
            rgb.close()
        if base is not None:
            base.close()

        for piece in artwork_pieces:
            try:
                piece.close()
            except Exception:
                pass

        if artwork is not None:
            artwork.close()
        if template is not None:
            template.close()

        gc.collect()
