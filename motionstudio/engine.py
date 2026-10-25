"""AG Astro Motion Studio V1: image, depth and 2.5-D rendering engine.

The output is an artistic depth simulation, not measured astronomical distance.
This module intentionally has no Qt dependency and can be tested headlessly.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import math
import json
import numpy as np
import cv2
from PIL import Image

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.fit', '.fits', '.fts'}


def load_image(path: str | Path) -> np.ndarray:
    path = Path(path)
    if path.suffix.lower() not in IMAGE_EXTS:
        raise ValueError('Supported formats: PNG, JPG, TIFF and FITS')
    if path.suffix.lower() in {'.fit', '.fits', '.fts'}:
        try:
            from astropy.io import fits
        except ImportError as exc:
            raise RuntimeError('FITS support requires: pip install astropy') from exc
        source = fits.getdata(path)
        data = np.asarray(source,dtype=np.float32)
        if data.ndim == 3 and data.shape[0] in (3, 4):
            data = np.moveaxis(data[:3], 0, -1)
        elif data.ndim == 3 and data.shape[-1] in (3, 4):
            data = data[..., :3]
        elif data.ndim != 2:
            raise ValueError(f'Unsupported FITS dimensions: {data.shape}')
        if not np.isfinite(data).any():
            raise ValueError('FITS contains no finite pixels')
        # FITS float data convention: normalized 0..1. Integer-like data uses
        # one common range for all RGB channels, preserving component colors.
        hi = float(np.nanmax(data))
        if hi > 1:
            if np.issubdtype(source.dtype,np.integer):
                scale = float(np.iinfo(source.dtype).max)
            else:
                scale = 255. if hi <= 255 else (65535. if hi <= 65535 else hi)
            data /= max(scale,1.)
        image = np.clip(np.nan_to_num(data,nan=0.,posinf=1.,neginf=0.),0,1)
        image = np.flipud(image)
        if image.ndim == 2:
            image = np.repeat(image[...,None],3,axis=2)
        return np.ascontiguousarray(image,dtype=np.float32)
    if path.suffix.lower() in {'.tif','.tiff'}:
        import tifffile
        data = tifffile.imread(path)
        if data.ndim == 3 and data.shape[0] in (3,4) and data.shape[-1] not in (3,4):
            data = np.moveaxis(data,0,-1)
        from .stars import normalized_rgb
        return normalized_rgb(data)
    with Image.open(path) as im:
        if im.mode in ('I;16','I','F'):
            from .stars import normalized_rgb
            data=np.asarray(im)
            if im.mode == 'I' and path.suffix.lower() == '.png':
                data=data.astype(np.uint16)
            return normalized_rgb(data)
        return np.array(im.convert('RGB'),dtype=np.uint8)


def validate_pair(starless: np.ndarray, stars: np.ndarray) -> None:
    if starless.ndim != 3 or starless.shape[-1] != 3:
        raise ValueError('Starless image must have 3 RGB channels')
    if stars.shape != starless.shape:
        raise ValueError(f'Image dimensions do not match: Starless {starless.shape[1]}×{starless.shape[0]}; Stars {stars.shape[1]}×{stars.shape[0]}. Export both with the SAME crop and resolution.')


def nebula_depth(starless: np.ndarray, smooth: float = 1.0) -> np.ndarray:
    """Generate editable *relative* nebula depth using multiscale luminosity/structure."""
    from .stars import normalized_rgb
    rgb = normalized_rgb(starless)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    lum = lab[..., 0] / 100.0
    h, w = lum.shape
    broad = cv2.GaussianBlur(lum, (0, 0), max(3., min(h, w) / 26.))
    medium = cv2.GaussianBlur(lum, (0, 0), max(1.5, min(h, w) / 130.))
    fine = np.clip(medium - broad, -.35, .35)
    # We make no claim that luminosity is distance: only an artistic guess.
    raw = .58 * medium + .25 * broad + .17 * np.clip(fine * 2.0 + .5, 0, 1)
    lo, hi = np.percentile(raw, [1, 99])
    if hi - lo < 1e-5:
        return np.full((h, w), .5, dtype=np.float32)
    depth = np.clip((raw - lo) / (hi - lo), 0, 1)
    if smooth > 0:
        depth = cv2.bilateralFilter(depth.astype(np.float32), 7, max(.005, .05 * smooth), max(2., 7. * smooth))
    return np.ascontiguousarray(depth, dtype=np.float32)


def star_depth(stars: np.ndarray, seed: int = 42) -> np.ndarray:
    from .stars import detect_stars, depth_map, DetectionSettings
    return depth_map(detect_stars(stars,DetectionSettings(seed=seed)))


def refine_nebula_depth(starless, initial, strength=.6, status=None, progress=None):
    """Deterministic structure/local-contrast refinement. Entirely offline."""
    from .star_catalog import normalized_rgb
    if status:status('Refining nebula depth: image structure…')
    if progress:progress(10)
    rgb=normalized_rgb(starless)
    lum=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    local=lum-cv2.GaussianBlur(lum,(0,0),max(2.,min(lum.shape)/80))
    scale=max(float(np.percentile(np.abs(local),95)),1e-5)
    structure=np.clip(local/scale,-1,1)*.5+.5
    if progress:progress(45)
    if status:status('Refining nebula depth: edge-aware smoothing…')
    smooth=cv2.bilateralFilter(np.asarray(initial,np.float32),9,.07,7.)
    candidate=np.clip(.80*smooth+.20*structure,0,1)
    candidate=cv2.bilateralFilter(candidate.astype(np.float32),7,.05,4.)
    if progress:progress(85)
    amount=float(np.clip(strength,0,1))
    return np.clip((1-amount)*initial+amount*candidate,0,1).astype(np.float32)


def save_depth(depth: np.ndarray, path: str | Path, bit_depth: int = 16) -> None:
    path = Path(path)
    depth = np.clip(depth, 0, 1)
    if bit_depth == 16:
        Image.fromarray(np.uint16(depth * 65535 + .5)).save(path)
    elif bit_depth == 8:
        Image.fromarray(np.uint8(depth * 255 + .5)).save(path)
    else:
        raise ValueError('Use 8 or 16 bits')


def preview_depth(depth: np.ndarray) -> np.ndarray:
    return cv2.applyColorMap(np.uint8(np.clip(depth, 0, 1) * 255), cv2.COLORMAP_TURBO)[..., ::-1].copy()


@dataclass
class MotionSettings:
    mode: str = 'Parallax'
    duration: int = 8
    fps: int = 24
    intensity: float = .5
    width: int = 1280
    height: int = 720


def _fit_rgb(rgb: np.ndarray, w: int, h: int) -> np.ndarray:
    # Center-crop to requested output AR without distorting the artwork.
    ih, iw = rgb.shape[:2]
    source_ar = iw / ih
    target_ar = w / h
    if source_ar > target_ar:
        crop_w = max(1, round(ih*target_ar))
        off = (iw - crop_w)//2
        rgb = rgb[:, off:off+crop_w]
    else:
        crop_h = max(1, round(iw/target_ar))
        off = (ih - crop_h)//2
        rgb = rgb[off:off+crop_h]
    return cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA if iw > w else cv2.INTER_CUBIC)


def _prepared(starless, stars, neb_depth, star_depth, w, h):
    # Same center-crop on every input, including the depth maps. Never register
    # a cropped RGB star to a full-frame resized depth map.
    return tuple(_fit_rgb(x, w, h) if x.ndim == 3 else
                 _fit_rgb(x[...,None].repeat(3,axis=-1),w,h)[...,0]
                 for x in (starless, stars, neb_depth, star_depth))


def render_frame(starless: np.ndarray, stars: np.ndarray, neb_depth: np.ndarray,
                 star_depth_map: np.ndarray, t: float, settings: MotionSettings,
                 prepared: bool = False) -> np.ndarray:
    """CPU-friendly artistic 2.5-D motion. Not true volumetric reconstruction."""
    from .scene3d import Scene, camera_at, default_keyframes
    scene=Scene(starless,stars,neb_depth,star_depth_map,settings.width,settings.height)
    frames=default_keyframes(settings.mode,settings.duration)
    frames[1].x *= settings.intensity
    frames[1].y *= settings.intensity
    frames[1].z *= settings.intensity
    return scene.render(camera_at(frames,np.clip(t,0,1)*settings.duration))


def render_video(starless, stars, neb_depth_map, star_depth_map, path, settings: MotionSettings,
                 progress: Callable[[int,int],None] | None = None) -> None:
    from .scene3d import Scene, default_keyframes, render_video_scene
    scene=Scene(starless,stars,neb_depth_map,star_depth_map,settings.width,settings.height)
    frames=default_keyframes(settings.mode,settings.duration)
    for k in ('x','y','z'):setattr(frames[1],k,getattr(frames[1],k)*settings.intensity)
    render_video_scene(scene,frames,path,settings.duration,settings.fps,progress=progress)


def save_project(path, starless_path, star_mask_path, settings: MotionSettings, ai_model_used=False):
    import dataclasses
    Path(path).write_text(json.dumps({
        'schema': 1, 'application':'AG Astro Motion Studio V1',
        'starless': str(Path(starless_path).resolve()),
        'star_mask': str(Path(star_mask_path).resolve()),
        'animation': dataclasses.asdict(settings),
        'ai_model_used': bool(ai_model_used),
        'note': 'Artistic relative depth only, not astronomical distance',
    }, indent=2), encoding='utf-8')
