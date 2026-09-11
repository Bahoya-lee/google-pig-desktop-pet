# -*- coding: utf-8 -*-
r"""把原始谷歌猪图片整理成桌宠可用的透明状态图。

只使用 Pillow 做确定性的裁切、抠图和缩放，不调用外部图片 API。
运行：
    python tools\prepare_assets.py
"""

from __future__ import annotations

import argparse
import json
import math
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageSequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(r"D:\Downloads\谷歌猪")
DEFAULT_OUT = PROJECT_ROOT / "assets"
WALK_GIF = "Image_1789121424123_278.gif"

# 每张状态图都保留原始画风，只做裁切和背景去除。
# corner 后的两个数字会在右下角清除小红书水印。
STATES = {
    "idle": {
        "file": "Camera_1040g3k0322rnqs727k005ofqjq440jdb367ljio.jpg",
        "crop": (0, 0, 512, 512),
        "mode": "color",
        "color": (245, 163, 165),
        "corner": (0.78, 0.82),
    },
    "walk": {
        "file": "Image_1789118031514_864.jpg",
        "crop": (0, 0, 1012, 1024),
        "mode": "white",
        "remove_colors": [(84, 71, 101)],
        "mask_ellipse": (0.52, 0.54, 0.38, 0.40),
        "mask_bottom": 0.82,
    },
    "sleepy": {
        "file": "Camera_1040g3k0324i5e4csn42g5q51aeb6c5mr79h8b18.jpg",
        "crop": (0, 0, 1440, 1440),
        "mode": "white",
        "mask_bottom": 0.74,
    },
    "happy": {
        "alias": "idle",
        "rotate": 4.0,
        "scale_x": 1.02,
        "scale_y": 0.98,
    },
    "angry": {
        "alias": "idle",
        "mirror": True,
        "rotate": -4.0,
        "scale_x": 1.01,
        "scale_y": 0.97,
    },
    "music": {
        "file": "Image_1789118038521_893.png",
        "crop": (0, 0, 900, 900),
        "mode": "white",
    },
    "patrol": {
        "file": "Image_1789137468057_720.jpg",
        "crop": (250, 250, 950, 950),
        "mode": "white",
    },
    "love": {
        "file": "Image_1789137465672_836.jpg",
        "crop": (300, 100, 900, 740),
        "mode": "white",
        "remove_colors": [(84, 71, 101)],
    },
    "bless": {
        "file": "Image_1789137460401_515.jpg",
        "crop": (110, 250, 900, 740),
        "mode": "white",
        "remove_colors": [(84, 71, 101)],
    },
    "surprised": {
        "file": "Image_1789137463515_55.png",
        "crop": (280, 450, 1250, 1312),
        "mode": "white",
    },
    "tired": {
        "file": "Camera_XHS_17891373611621040g008320kpuq9elm005o7.jpg",
        "crop": (650, 40, 1440, 786),
        "mode": "white",
        "corner": (0.80, 0.80),
    },
    "grumpy": {
        "file": "Camera_XHS_17891373592861040g2sg320kptnhn5m6g5o7.jpg",
        "crop": (650, 40, 1440, 786),
        "mode": "white",
        "corner": (0.80, 0.80),
    },
}

SIZE_HEIGHTS = {"small": 190, "medium": 240, "large": 300}


def _remove_white(image: Image.Image) -> Image.Image:
    """去掉纯白/浅灰背景，同时保留深色眼睛、耳机和黑线。"""
    arr = np.asarray(image.convert("RGBA")).astype(np.float32)
    rgb = arr[:, :, :3]
    high = rgb.max(axis=2)
    low = rgb.min(axis=2)
    saturation = high - low
    soft_start = 224.0
    soft_end = 245.0
    blend = np.clip((high - soft_start) / (soft_end - soft_start), 0.0, 1.0)
    alpha = 1.0 - blend * (saturation < 24)
    arr[:, :, 3] *= alpha
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def _remove_gif_background(image: Image.Image) -> Image.Image:
    """从边框泛洪，去掉 GIF 背景和边缘残留的白色/灰色杂点。"""
    arr = np.asarray(image.convert("RGBA")).astype(np.uint8)
    rgb = arr[:, :, :3].astype(np.int16)
    high = rgb.max(axis=2)
    low = rgb.min(axis=2)
    background = (high > 170) & ((high - low) < 70)
    height, width = background.shape
    outside = np.zeros_like(background, dtype=bool)
    queue = deque()

    def add(x, y):
        if background[y, x] and not outside[y, x]:
            outside[y, x] = True
            queue.append((x, y))

    for x in range(width):
        add(x, 0)
        add(x, height - 1)
    for y in range(height):
        add(0, y)
        add(width - 1, y)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < width and 0 <= ny < height:
                add(nx, ny)

    alpha = np.where(outside, 0, 255).astype(np.uint8)
    arr[:, :, 3] = np.minimum(arr[:, :, 3], alpha)
    return Image.fromarray(arr, "RGBA")


def _fill_alpha_holes(mask: np.ndarray) -> np.ndarray:
    """Fill internal transparent holes, including frames touching crop edges."""
    height, width = mask.shape
    padded = np.zeros((height + 4, width + 4), dtype=bool)
    padded[2:-2, 2:-2] = mask
    inverse = ~padded
    outside = np.zeros_like(inverse, dtype=bool)
    queue = deque([(0, 0)])
    outside[0, 0] = True
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < padded.shape[1] and 0 <= ny < padded.shape[0]:
                if inverse[ny, nx] and not outside[ny, nx]:
                    outside[ny, nx] = True
                    queue.append((nx, ny))
    return ~outside[2:-2, 2:-2]


def _keep_large_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    """Remove isolated dithering specks while keeping eyes and facial strokes."""
    remaining = mask.copy()
    kept = np.zeros_like(mask, dtype=bool)
    height, width = mask.shape
    for y0, x0 in zip(*np.where(remaining)):
        if not remaining[y0, x0]:
            continue
        queue = deque([(int(x0), int(y0))])
        remaining[y0, x0] = False
        points = []
        while queue:
            x, y = queue.popleft()
            points.append((x, y))
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < width and 0 <= ny < height and remaining[ny, nx]:
                    remaining[ny, nx] = False
                    queue.append((nx, ny))
        if len(points) >= min_area:
            for x, y in points:
                kept[y, x] = True
    return kept


def _extract_gif_layers(image: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Return a flat pig body plus a fixed facial-feature layer."""
    arr = np.asarray(image.convert("RGBA")).astype(np.uint8)
    rgb = arr[:, :, :3].astype(np.int16)
    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    warm = (
        (red > 180)
        & (green > 105)
        & (blue > 65)
        & (red > green + 4)
        & (green > blue - 22)
    )
    height, width = warm.shape
    seed_x, seed_y = int(width * 0.55), int(height * 0.42)
    if not warm[seed_y, seed_x]:
        ys, xs = np.where(warm)
        index = int(np.argmin((xs - seed_x) ** 2 + (ys - seed_y) ** 2))
        seed_x, seed_y = int(xs[index]), int(ys[index])

    component = np.zeros_like(warm, dtype=bool)
    queue = deque([(seed_x, seed_y)])
    component[seed_y, seed_x] = True
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < width and 0 <= ny < height and warm[ny, nx] and not component[ny, nx]:
                component[ny, nx] = True
                queue.append((nx, ny))

    solid = np.array(
        Image.fromarray((component * 255).astype(np.uint8))
        .filter(ImageFilter.MaxFilter(21))
        .filter(ImageFilter.MinFilter(21))
    ) > 0
    solid = _fill_alpha_holes(solid)

    body_rgb = np.zeros_like(arr)
    body_rgb[solid, :3] = [255, 210, 177]
    body_rgba = body_rgb.copy()
    body_rgba[:, :, 3] = (solid * 255).astype(np.uint8)
    body = Image.fromarray(body_rgba, "RGBA")

    ys = np.indices(solid.shape)[0]
    near = np.array(
        Image.fromarray((solid * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(9))
    ) > 0
    xs = np.indices(solid.shape)[1]
    upper = ys < height * 0.64
    face_zone = xs < width * 0.56
    dark = (red < 145) & (green < 145) & (blue < 145) & near & upper & face_zone
    pink = (red > 180) & (blue > green + 20) & (green < 195) & near & upper & face_zone
    white = (red > 225) & (green > 225) & (blue > 225) & near & upper & face_zone

    def clean_mask(mask: np.ndarray) -> np.ndarray:
        image = Image.fromarray((mask * 255).astype(np.uint8))
        image = image.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
        return np.array(image) > 0

    dark = _keep_large_components(clean_mask(dark), 24)
    pink = _keep_large_components(clean_mask(pink), 18)
    white = _keep_large_components(clean_mask(white), 4)

    feature_rgb = np.zeros_like(arr)
    feature_rgb[pink, :3] = [229, 79, 143]
    feature_rgb[dark, :3] = [35, 35, 35]
    feature_rgb[white, :3] = [255, 255, 255]
    feature_rgba = feature_rgb.copy()
    feature_rgba[:, :, 3] = ((pink | dark | white) * 255).astype(np.uint8)
    features = Image.fromarray(feature_rgba, "RGBA")
    return body.filter(ImageFilter.GaussianBlur(0.25)), features.filter(
        ImageFilter.GaussianBlur(0.2)
    )


def _remove_color(image: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """去掉单色背景，适合粉色底的站立猪。"""
    arr = np.asarray(image.convert("RGBA")).astype(np.float32)
    distance = np.sqrt(
        ((arr[:, :, :3] - np.array(color, dtype=np.float32)) ** 2).sum(axis=2)
    )
    alpha = np.clip((distance - 26.0) / 26.0, 0.0, 1.0)
    arr[:, :, 3] *= alpha
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def _clean_corner(image: Image.Image, x_ratio: float, y_ratio: float) -> None:
    """清掉右下角来源水印，避免在小尺寸桌宠上出现杂字。"""
    alpha = np.array(image.getchannel("A"), copy=True)
    h, w = alpha.shape
    alpha[int(h * y_ratio) :, int(w * x_ratio) :] = 0
    image.putalpha(Image.fromarray(alpha, "L"))


def _mask_edge(image: Image.Image, *, top: float = 0.0, bottom: float = 1.0) -> None:
    alpha = np.array(image.getchannel("A"), copy=True)
    h = alpha.shape[0]
    if top:
        alpha[: int(h * top), :] = 0
    if bottom < 1:
        alpha[int(h * bottom) :, :] = 0
    image.putalpha(Image.fromarray(alpha, "L"))


def _mask_ellipse(image: Image.Image, cx: float, cy: float, rx: float, ry: float) -> None:
    alpha = np.array(image.getchannel("A"), copy=True)
    h, w = alpha.shape
    ys, xs = np.indices((h, w), dtype=np.float32)
    outside = (((xs / w) - cx) / rx) ** 2 + (((ys / h) - cy) / ry) ** 2 > 1.0
    alpha[outside] = 0
    image.putalpha(Image.fromarray(alpha, "L"))


def _harden_alpha(image: Image.Image) -> Image.Image:
    """把抗锯齿边缘变成干净的二值透明区域，避免 Tk 透明色出现彩边。"""
    alpha = image.getchannel("A")
    alpha = alpha.point(lambda value: 255 if value >= 185 else 0)
    alpha = alpha.filter(ImageFilter.MinFilter(3))
    alpha = alpha.filter(ImageFilter.MinFilter(3))
    image.putalpha(alpha)
    return image


def _trim_and_pad(image: Image.Image, target_height: int) -> Image.Image:
    bbox = image.getchannel("A").getbbox()
    if bbox:
        image = image.crop(bbox)
    max_width = round(image.height * 2.1)
    if image.width > max_width:
        left = max(0, (image.width - max_width) // 2)
        image = image.crop((left, 0, left + max_width, image.height))
    width = max(1, round(image.width * target_height / image.height))
    image = image.resize((width, target_height), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", (image.width + 40, image.height + 40), (0, 0, 0, 0))
    out.alpha_composite(image, (20, 20))
    return out


def _make_preview(renders: dict[str, Image.Image], path: Path) -> None:
    cols = 3
    cell_w, cell_h = 360, 360
    rows = math.ceil(len(renders) / cols)
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (232, 234, 240))
    draw = ImageDraw.Draw(sheet)
    for y in range(0, sheet.height, 20):
        for x in range(0, sheet.width, 20):
            if ((x // 20) + (y // 20)) % 2 == 0:
                draw.rectangle((x, y, x + 19, y + 19), fill=(246, 247, 249))
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 20)
    except OSError:
        font = ImageFont.load_default()
    for index, (name, image) in enumerate(renders.items()):
        thumb = image.copy()
        thumb.thumbnail((cell_w - 40, cell_h - 68), Image.Resampling.LANCZOS)
        x = (index % cols) * cell_w
        y = (index // cols) * cell_h
        sheet.paste(thumb, (x + (cell_w - thumb.width) // 2, y + 12), thumb)
        draw.text((x + 18, y + cell_h - 42), name, fill=(25, 30, 45), font=font)
    sheet.save(path)


def build(source: Path, out_dir: Path) -> None:
    if not source.is_dir():
        raise SystemExit(f"素材目录不存在：{source}")
    state_dir = out_dir / "states"
    state_dir.mkdir(parents=True, exist_ok=True)

    base_images: dict[str, Image.Image] = {}
    for state, spec in STATES.items():
        if spec.get("alias"):
            image = base_images[spec["alias"]].copy()
            if spec.get("mirror"):
                image = ImageOps.mirror(image)
            if spec.get("rotate"):
                image = image.rotate(
                    spec["rotate"],
                    resample=Image.Resampling.BICUBIC,
                    expand=True,
                    fillcolor=(0, 0, 0, 0),
                )
            scale_x = spec.get("scale_x", 1.0)
            scale_y = spec.get("scale_y", 1.0)
            if scale_x != 1.0 or scale_y != 1.0:
                image = image.resize(
                    (max(1, round(image.width * scale_x)), max(1, round(image.height * scale_y))),
                    Image.Resampling.BICUBIC,
                )
            base_images[state] = image
            continue
        source_file = source / spec["file"]
        if not source_file.exists():
            raise SystemExit(f"缺少素材：{source_file}")
        image = Image.open(source_file).convert("RGBA").crop(spec["crop"])
        if spec["mode"] == "color":
            image = _remove_color(image, spec["color"])
        else:
            image = _remove_white(image)
        for color in spec.get("remove_colors", []):
            image = _remove_color(image, color)
        if spec.get("mask_top") or spec.get("mask_bottom"):
            _mask_edge(
                image,
                top=spec.get("mask_top", 0.0),
                bottom=spec.get("mask_bottom", 1.0),
            )
        if spec.get("mask_ellipse"):
            _mask_ellipse(image, *spec["mask_ellipse"])
        if spec.get("corner"):
            _clean_corner(image, *spec["corner"])
        # 保留素材原始肤色和粉色点缀；透明只在分层窗口里处理。
        base_images[state] = image

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "sizes": {},
    }
    medium_preview: dict[str, Image.Image] = {}
    for size_name, target_height in SIZE_HEIGHTS.items():
        size_dir = state_dir / size_name
        size_dir.mkdir(parents=True, exist_ok=True)
        entries: dict[str, dict[str, str]] = {}
        rendered_widths: list[int] = []
        rendered_heights: list[int] = []
        idle_rendered = None
        walk_rendered = None
        for state, image in base_images.items():
            rendered = _trim_and_pad(image, target_height)
            rendered_widths.append(rendered.width)
            rendered_heights.append(rendered.height)
            if state == "walk":
                walk_rendered = rendered
            if state == "idle":
                idle_rendered = rendered
            if size_name == "medium":
                medium_preview[state] = rendered
            normal_path = size_dir / f"{state}.png"
            flipped_path = size_dir / f"{state}_flip.png"
            rendered.save(normal_path)
            ImageOps.mirror(rendered).save(flipped_path)
            entries[state] = {
                "normal": str(normal_path.relative_to(out_dir)).replace("\\", "/"),
                "flipped": str(flipped_path.relative_to(out_dir)).replace("\\", "/"),
            }

        # 根据实际图片边界留出气泡和拖动空间。
        canvas_w = max(rendered_widths) + 44
        canvas_h = max(rendered_heights) + 98
        # 飘动模式直接使用静止高清 pose，不再生成腿帧。
        walk_frames = []
        manifest["sizes"][size_name] = {
            "canvas": [canvas_w, canvas_h],
            "states": entries,
            "walk_frames": walk_frames,
        }

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _make_preview(medium_preview, out_dir / "preview_sheet.png")

    icon_source = medium_preview["idle"]
    icon = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    icon_source.thumbnail((226, 226), Image.Resampling.LANCZOS)
    icon.alpha_composite(
        icon_source, ((256 - icon_source.width) // 2, (256 - icon_source.height) // 2)
    )
    icon.save(out_dir / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (128, 128), (256, 256)])
    print(f"已生成：{out_dir}")
    print(f"状态数：{len(base_images)}，尺寸：{', '.join(SIZE_HEIGHTS)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成谷歌猪桌宠透明状态素材")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="原始图片目录")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="输出目录")
    args = parser.parse_args()
    build(args.source, args.out)


if __name__ == "__main__":
    main()
