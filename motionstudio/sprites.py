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


def prepare_atlas(catalog,sx,sy,bloom=False,style=None):
    style=style or {}
    preserve=style.get('preserve_size',True)
    size=float(style.get('size_scale',1.))
    glow=float(style.get('bloom',0.))+( .06 if bloom else 0.)
    sharp=float(style.get('sharpness',.7))
    pixels=[];meta=[];offset=0
    for i,sprite in enumerate(catalog.sprites):
        sh,sw=sprite.shape[:2]
        # Use the true source/output scale, rather than stretching each rounded
        # patch to a different effective scale. Profiles remain observed RGB data.
        tx=sx*size;ty=sy*size
        nw=max(1,int(math.ceil(sw*tx)));nh=max(1,int(math.ceil(sh*ty)))
        if preserve:
            # Area prefilter once for minification; exact affine pixel-center map.
            source=sprite
            if min(tx,ty)<.65:
                source=cv2.GaussianBlur(source,(0,0),max(.01,.35/min(tx,ty)))
            transform=np.array([[tx,0,(tx-1)/2],[0,ty,(ty-1)/2]],np.float32)
            data=cv2.warpAffine(source,transform,(nw,nh),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            ax=(catalog.x[i]-catalog.sprite_origins[i,0]+.5)*tx-.5
            ay=(catalog.y[i]-catalog.sprite_origins[i,1]+.5)*ty-.5
        else:
            nw=max(1,round(sw*tx));nh=max(1,round(sh*ty))
            data=cv2.resize(sprite,(nw,nh),interpolation=cv2.INTER_AREA if min(tx,ty)<1 else cv2.INTER_LINEAR)
            ax=(catalog.x[i]-catalog.sprite_origins[i,0]+.5)*nw/sw-.5
            ay=(catalog.y[i]-catalog.sprite_origins[i,1]+.5)*nh/sh-.5
        if abs(sharp-.7)>.001:
            soft=cv2.GaussianBlur(data,(0,0),.55)
            # Monotonic bounded core adjustment: no negative ringing or new peaks.
            if sharp>.7:data=np.clip(data+(data-soft)*(sharp-.7)*.5,0,data.max(axis=(0,1)))
            else:data=data*(1-(.7-sharp)*.4)+soft*((.7-sharp)*.4)
        # Faint stars receive no synthetic envelope. Only truly bright observed
        # peaks acquire a small added halo; intensity never enters atlas creation.
        halo=glow*float(np.clip((catalog.peak[i]-.35)/.5,0,1))
        if halo>0:
            data=data+cv2.GaussianBlur(data,(0,0),max(.5,min(nw,nh)/16))*(halo*.18)
        # Trim empty source support before the compiled per-frame pixel loop.
        support=np.max(data,axis=2)>0
        ys,xs=np.nonzero(support)
        if len(xs):
            x0=max(0,int(xs.min())-1);y0=max(0,int(ys.min())-1)
            data=data[y0:min(nh,int(ys.max())+2),x0:min(nw,int(xs.max())+2)]
            ax-=x0;ay-=y0
        else:data=np.zeros((1,1,3),np.float32);ax=ay=0.
        nh,nw=data.shape[:2]
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
        # Subpixel points below one projected pixel use a compact flux-conserving
        # bilinear kernel. No visibility threshold changes between frames.
        if max(sw-2,sh-2)*scale<=1.:
            ix=int(math.floor(x));iy=int(math.floor(y));fx=x-ix;fy=y-iy
            for c in range(3):
                flux=0.
                for j in range(sw*sh):flux+=atlas[offset+j,c]
                flux*=gain*scale*scale
                for dy in range(2):
                    py=iy+dy
                    if py<0 or py>=height:continue
                    for dx in range(2):
                        px=ix+dx
                        if 0<=px<width:output[py,px,c]+=flux*(fy if dy else 1-fy)*(fx if dx else 1-fx)
            continue
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
