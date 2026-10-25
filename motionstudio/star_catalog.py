"""Compact deterministic star catalog. Real isolated sprites preserve the observed mask profiles."""
from dataclasses import dataclass
import numpy as np
import cv2

@dataclass(frozen=True)
class DetectionSettings:
    sigma: float = 3.5
    min_area: int = 2
    randomness: float = .55
    foreground_bias: float = 0.
    seed: int = 42

@dataclass
class StarCatalog:
    # Coordinates and radius are in ORIGINAL image pixels, independent of output size.
    x: np.ndarray
    y: np.ndarray
    radius: np.ndarray
    peak: np.ndarray
    flux: np.ndarray
    brightness: np.ndarray
    color: np.ndarray
    depth: np.ndarray
    area: np.ndarray
    width: int
    height: int
    settings: DetectionSettings
    threshold: float
    sprites: tuple = ()
    sprite_origins: np.ndarray | None = None
    original_count: int = -1

    def __len__(self):
        return len(self.x)


def normalized_rgb(image):
    a = np.asarray(image)
    if a.ndim == 2:
        a = np.repeat(a[..., None], 3, axis=2)
    if a.ndim != 3 or a.shape[-1] not in (3, 4):
        raise ValueError('Image must be grayscale or RGB')
    rgb = a[..., :3].astype(np.float32)
    if np.issubdtype(a.dtype, np.integer):
        rgb /= np.iinfo(a.dtype).max
    return np.clip(np.nan_to_num(rgb, nan=0., posinf=1., neginf=0.), 0, 1)


def detect_stars(image, settings=None):
    settings = settings or DetectionSettings()
    rgb = normalized_rgb(image)
    h, w = rgb.shape[:2]
    lum = rgb @ np.array([.2126, .7152, .0722], np.float32)
    sample = lum[::max(1, h//1000), ::max(1, w//1000)]
    background = float(np.median(sample))
    noise = float(1.4826*np.median(np.abs(sample-background)))
    # Quantization-aware floor, also for perfectly black masks where MAD=0.
    floor = 1/np.iinfo(image.dtype).max if np.issubdtype(image.dtype, np.integer) else 1e-6
    threshold = background + settings.sigma * max(noise, floor)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        np.uint8(lum > threshold), connectivity=8)
    flat = labels.ravel()
    weight = np.maximum(lum-background, 0).ravel()
    flux = np.bincount(flat, weights=weight, minlength=count)
    # Moments without allocating full float64 coordinate grids.
    mx = np.zeros(count); my = np.zeros(count)
    for start in range(0, h, 128):
        end = min(h, start+128)
        lab = labels[start:end].ravel()
        val = weight[start*w:end*w].reshape(end-start, w)
        mx += np.bincount(lab, weights=(val*np.arange(w)[None,:]).ravel(), minlength=count)
        my += np.bincount(lab, weights=(val*np.arange(start,end)[:,None]).ravel(), minlength=count)
    area = stats[:, cv2.CC_STAT_AREA]
    widths, heights = stats[:,2], stats[:,3]
    valid = (area >= max(1,settings.min_area)) & (area <= max(64,lum.size*.002))
    valid &= (np.maximum(widths,heights) <= np.minimum(widths,heights)*5)
    valid &= (flux > 0)
    valid[0] = False
    ids = np.flatnonzero(valid)
    peaks = np.zeros(count, np.float32)
    np.maximum.at(peaks, flat, weight)
    colors = np.column_stack([np.bincount(flat, weights=(rgb[...,c].ravel()*weight), minlength=count)[ids]
                              for c in range(3)])
    if len(ids):
        colors /= np.maximum(colors.max(axis=1,keepdims=True),1e-12)
    f = flux[ids]
    # Robust flux reference keeps most ordinary stars visible beside saturated stars.
    bright = np.clip(f/max(float(np.percentile(f,95)) if len(f) else 1,1e-12),0,1)
    sizes = np.sqrt(area[ids]/np.pi)
    size_bias = np.clip(np.log1p(sizes)/max(float(np.percentile(np.log1p(sizes),95)) if len(sizes) else 1,1e-12),0,1)
    random = np.random.default_rng(settings.seed).random(len(ids))
    bias = .55*bright+.45*size_bias
    r = np.clip(settings.randomness,0,1)
    depth = np.clip((1-r)*bias+r*random+settings.foreground_bias,0,1)
    # Assign every halo pixel to its nearest source component: neighboring
    # stars cannot be duplicated into several rectangular patches.
    sprites=[];origins=[]
    if len(ids):
        distance, nearest = cv2.distanceTransformWithLabels(np.uint8(labels==0),cv2.DIST_L2,5,
                                                           labelType=cv2.DIST_LABEL_CCOMP)
        lookup=np.zeros(int(nearest.max())+1,np.int32)
        foreground=flat>0
        np.maximum.at(lookup,nearest.ravel()[foreground],flat[foreground])
        owner=lookup[nearest]
        bg=np.median(rgb[::max(1,h//1000),::max(1,w//1000)],axis=(0,1))
        for i in ids:
            x,y,bw,bh=stats[i,:4]
            pad=min(96,max(4,int(np.sqrt(area[i]/np.pi)*2+3)))
            xa=max(0,int(x)-pad);xb=min(w,int(x+bw)+pad)
            ya=max(0,int(y)-pad);yb=min(h,int(y+bh)+pad)
            dist=distance[ya:yb,xa:xb]
            # Soft irregular support, not a rectangular opaque image patch.
            fade=np.clip((pad-dist)/max(1,pad*.5),0,1)
            fade=fade*fade*(3-2*fade)
            alpha=fade*(owner[ya:yb,xa:xb]==i)
            sprite=np.maximum(rgb[ya:yb,xa:xb]-bg,0)*alpha[...,None]
            sprites.append(np.ascontiguousarray(sprite,np.float32));origins.append((xa,ya))
    return StarCatalog((mx[ids]/f).astype(np.float32),(my[ids]/f).astype(np.float32),
        np.clip(sizes,.6,max(2,min(w,h)*.015)).astype(np.float32),peaks[ids],f.astype(np.float32),
        bright.astype(np.float32),colors.astype(np.float32),depth.astype(np.float32),area[ids],
        w,h,settings,threshold,tuple(sprites),np.asarray(origins,dtype=np.float32).reshape(-1,2),len(ids))


def depth_map(catalog):
    result = np.zeros((catalog.height,catalog.width),np.float32)
    for x,y,r,d in zip(catalog.x,catalog.y,catalog.radius,catalog.depth):
        cv2.circle(result,(round(float(x)),round(float(y))),max(1,round(float(r))),float(d),-1)
    return result


def with_synthetic_background(catalog, density=300):
    """Separate opt-in, seeded, faint artistic background; never replaces originals."""
    from dataclasses import replace
    n=min(20000,max(0,round(density*catalog.width*catalog.height/1_000_000)))
    if n==0:return catalog
    rng=np.random.default_rng(catalog.settings.seed+7919)
    x=rng.uniform(0,catalog.width-1,n).astype(np.float32)
    y=rng.uniform(0,catalog.height-1,n).astype(np.float32)
    radius=rng.uniform(.65,1.4,n).astype(np.float32)
    peak=rng.uniform(.015,.07,n).astype(np.float32)
    colors=rng.uniform(.7,1.,(n,3)).astype(np.float32)
    yy,xx=np.mgrid[-5:6,-5:6].astype(np.float32)
    sprites=tuple(np.ascontiguousarray(np.exp(-(xx*xx+yy*yy)/(2*r*r))[...,None]*p*c,np.float32)
                  for r,p,c in zip(radius,peak,colors))
    def cat(a,b):return np.concatenate((a,b),axis=0)
    return replace(catalog,x=cat(catalog.x,x),y=cat(catalog.y,y),radius=cat(catalog.radius,radius),
       peak=cat(catalog.peak,peak),flux=cat(catalog.flux,peak*2*np.pi*radius**2),
       brightness=cat(catalog.brightness,peak),color=cat(catalog.color,colors),
       depth=cat(catalog.depth,rng.uniform(.03,.2,n).astype(np.float32)),area=cat(catalog.area,np.ones(n,np.int32)),
       sprites=catalog.sprites+sprites,sprite_origins=cat(catalog.sprite_origins,np.c_[x-5,y-5]),
       original_count=len(catalog) if catalog.original_count<0 else catalog.original_count)


def redistribute_depth(catalog,settings):
    from dataclasses import replace
    log=np.log1p(np.sqrt(catalog.area/np.pi))
    size_bias=np.clip(log/max(float(np.percentile(log,95)) if len(log) else 1,1e-12),0,1)
    bias=.55*catalog.brightness+.45*size_bias
    randomness=float(np.clip(settings.randomness,0,1))
    random=np.random.default_rng(settings.seed).random(len(catalog))
    depth=np.clip((1-randomness)*bias+randomness*random+settings.foreground_bias,0,1).astype(np.float32)
    return replace(catalog,depth=depth,settings=settings)
