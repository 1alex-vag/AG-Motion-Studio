"""Soft, cached subject protection derived only from the starless image."""
import cv2
import numpy as np
from .star_catalog import normalized_rgb


def nebula_protection(starless):
    rgb=normalized_rgb(starless)
    h,w=rgb.shape[:2]
    # Compute broad subject structure at bounded size, then feather at source scale.
    scale=min(1.,1000/max(h,w))
    small=cv2.resize(rgb,(max(2,round(w*scale)),max(2,round(h*scale))),interpolation=cv2.INTER_AREA)
    # Luminance plus strongest color channel protects faint red/blue emission too.
    lum=small@np.array([.2126,.7152,.0722],np.float32)
    signal=.65*lum+.35*np.max(small,axis=2)
    smooth=cv2.GaussianBlur(signal,(0,0),max(1.,min(signal.shape)/100))
    lo,hi=np.percentile(smooth,[30,97])
    if hi-lo<1e-6:return np.zeros((h,w),np.float32)
    t=np.clip((smooth-lo)/(hi-lo),0,1)
    mask=t*t*(3-2*t)
    mask=cv2.GaussianBlur(mask,(0,0),max(1.,min(signal.shape)/90))
    return np.clip(cv2.resize(mask,(w,h),interpolation=cv2.INTER_LINEAR),0,1).astype(np.float32)
