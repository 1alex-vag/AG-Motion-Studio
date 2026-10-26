"""Offline artistic multiscale depth; source image pixels remain unchanged."""
import cv2
import numpy as np
PROFILES={'Soft':(.75,.65,.65,1.,.7,.4),'Balanced':(1.,1.,1.,1.,.5,.4),
          'Dusty':(1.1,1.5,1.5,1.3,.65,.25),'Dramatic':(1.5,1.7,1.7,1.5,.75,.25)}
def combine(image,depth,overall=1.,fine=1.,dust=1.,local=1.,bias=.5,smoothing=.4):
    from .star_catalog import normalized_rgb
    rgb=normalized_rgb(image);lum=rgb@np.array([.2126,.7152,.0722],np.float32)
    scale=max(1.,min(depth.shape)/45)
    broad=cv2.GaussianBlur(depth,(0,0),scale)
    structure=cv2.GaussianBlur(lum,(0,0),max(.6,scale/5))
    fine_signal=structure-cv2.GaussianBlur(structure,(0,0),scale)
    # Robust amplitude normalization; flat input never invents structure.
    amplitude=max(.05,float(np.percentile(np.abs(fine_signal),98)))
    detail=np.clip(fine_signal/amplitude,-1,1)*.10+(depth-broad)
    dust_map=np.clip((cv2.GaussianBlur(lum,(0,0),scale*2)-structure)/amplitude,0,1)
    result=.5+(broad-.5)*overall+detail*fine*local+dust_map*dust*(bias-.5)*.5
    # No global re-stretch: independent controls keep stable meanings.
    result=np.clip(result,0,1).astype(np.float32)
    smooth=cv2.bilateralFilter(result,7,.06,2.)
    return np.clip(result*(1-smoothing)+smooth*smoothing,0,1).astype(np.float32),broad,detail
