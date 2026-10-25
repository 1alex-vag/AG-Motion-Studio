"""Cached sprite atlas and optional compiled, GIL-free compositing.

No per-frame star detection, sprite generation, exponentials or per-star GUI objects.
The pure-Python fallback uses the same algorithm when Numba is unavailable.
"""
import math
import numpy as np
import cv2
try:
    from numba import njit
    COMPILED = True
except ImportError:
    COMPILED = False
    def njit(*args,**kwargs):
        return lambda func:func


def prepare_atlas(catalog,sx,sy,bloom=False):
    pixels=[];meta=[];offset=0
    for i,sprite in enumerate(catalog.sprites):
        sh,sw=sprite.shape[:2]
        # Keep anchors in continuous coordinates to avoid neutral-position drift.
        nw=max(1,round(sw*sx));nh=max(1,round(sh*sy))
        data=cv2.resize(sprite,(nw,nh),interpolation=cv2.INTER_AREA if sx<1 or sy<1 else cv2.INTER_LINEAR)
        if bloom:
            # Optional glow is subtle and derived from this actual star.
            data=data+cv2.GaussianBlur(data,(0,0),max(.5,min(nh,nw)/12))*.06
        # Pixel-center transform, including fractional stars and synthetic origins.
        ax=(catalog.x[i]-catalog.sprite_origins[i,0]+.5)*nw/sw-.5
        ay=(catalog.y[i]-catalog.sprite_origins[i,1]+.5)*nh/sh-.5
        meta.append((offset,nw,nh,ax,ay));pixels.append(data.reshape(-1,3));offset+=nw*nh
    return (np.concatenate(pixels).astype(np.float32) if pixels else np.zeros((0,3),np.float32),
            np.asarray(meta,np.float64).reshape(-1,5))


@njit(cache=True,nogil=True)
def draw_atlas(atlas,meta,centers,scales,visible,width,height,gain):
    output=np.zeros((height,width,3),np.float32)
    for i in range(len(meta)):
        if not visible[i]:continue
        offset=int(meta[i,0]);sw=int(meta[i,1]);sh=int(meta[i,2]);ax=meta[i,3];ay=meta[i,4]
        x=centers[i,0];y=centers[i,1];scale=scales[i]
        left=x-(ax+.5)*scale;top=y-(ay+.5)*scale
        xa=max(0,int(math.floor(left)));ya=max(0,int(math.floor(top)))
        xb=min(width,int(math.ceil(left+sw*scale)));yb=min(height,int(math.ceil(top+sh*scale)))
        if xa>=xb or ya>=yb:continue
        # Inverse bilinear resampling has no splatting holes. Black pixels carry
        # zero emitted light; support is already isolated/feathered in the atlas.
        for py in range(ya,yb):
            v=(py-y)/scale+ay;v0=int(math.floor(v));fy=v-v0
            for px in range(xa,xb):
                u=(px-x)/scale+ax;u0=int(math.floor(u));fx=u-u0
                for c in range(3):
                    value=0.
                    for dy in range(2):
                        iy=v0+dy
                        if iy<0 or iy>=sh:continue
                        wy=fy if dy else 1-fy
                        for dx in range(2):
                            ix=u0+dx
                            if ix<0 or ix>=sw:continue
                            wx=fx if dx else 1-fx
                            value+=atlas[offset+iy*sw+ix,c]*wy*wx
                    output[py,px,c]+=value*gain
    return output
