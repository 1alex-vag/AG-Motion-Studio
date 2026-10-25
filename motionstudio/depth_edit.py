"""Non-destructive depth versions and patch-based per-stroke undo/redo."""
from dataclasses import dataclass
import math
import numpy as np
import cv2


def checked_depth(value,shape=None):
    value=np.asarray(value,np.float32)
    if value.ndim!=2 or not np.isfinite(value).all() or (shape is not None and value.shape!=shape):
        raise ValueError('Depth data must be a finite map matching the image dimensions')
    if np.any(value<0) or np.any(value>1):raise ValueError('Depth values must be between 0 and 1')
    return value.copy()

@dataclass
class DepthVersions:
    generated: np.ndarray
    refined: np.ndarray | None = None
    manual: np.ndarray | None = None

    def __post_init__(self):
        self.generated=checked_depth(self.generated)
        for key in ('refined','manual'):
            value=getattr(self,key)
            if value is not None:setattr(self,key,checked_depth(value,self.generated.shape))
        self.generated.setflags(write=False)
        if self.refined is not None:self.refined.setflags(write=False)

    @property
    def current(self):
        return self.manual if self.manual is not None else self.refined if self.refined is not None else self.generated

    def refined_copy(self,value):
        value=checked_depth(value,self.generated.shape)
        # Preserve manually painted corrections when the refinement preset changes.
        base=self.refined if self.refined is not None else self.generated
        manual=None if self.manual is None else np.clip(value+(self.manual-base),0,1)
        return DepthVersions(self.generated,value,manual)

    def arrays(self):
        return {key:getattr(self,key) for key in ('generated','refined','manual') if getattr(self,key) is not None}

@dataclass
class Patch:
    box: tuple
    before: np.ndarray
    after: np.ndarray

    @property
    def bytes(self):return self.before.nbytes+self.after.nbytes


class DepthPaint:
    def __init__(self,versions,history_bytes=128*1024**2):
        self.generated=versions.generated
        self.depth=versions.current.copy()
        self.undo_stack=[];self.redo_stack=[]
        self.history_bytes=history_bytes
        self._box=None;self._before=None;self._last=None

    def begin(self):
        self._box=None;self._before=None;self._last=None

    def _capture(self,box):
        x0,y0,x1,y1=box
        if self._box is None:
            self._box=box;self._before=self.depth[y0:y1,x0:x1].copy();return
        a,b,c,d=self._box
        new=(min(x0,a),min(y0,b),max(x1,c),max(y1,d))
        if new!=self._box:
            x0,y0,x1,y1=new;before=self.depth[y0:y1,x0:x1].copy()
            before[b-y0:d-y0,a-x0:c-x0]=self._before
            self._before=before;self._box=new

    def stroke(self,x,y,tool='Raise',size=100,strength=.3,softness=.7):
        if tool not in ('Raise','Lower','Smooth','Restore','Flatten'):raise ValueError('Unknown depth brush')
        size=float(np.clip(size,10,1000));strength=float(np.clip(strength,.01,1));softness=float(np.clip(softness,0,1))
        current=(float(x),float(y))
        if self._last is None:points=[current]
        else:
            distance=math.hypot(x-self._last[0],y-self._last[1]);steps=max(1,math.ceil(distance/max(1,size*.15)))
            points=[(self._last[0]+(x-self._last[0])*i/steps,self._last[1]+(y-self._last[1])*i/steps) for i in range(1,steps+1)]
        self._last=current
        for px,py in points:self._stamp(px,py,tool,size,strength,softness)

    def _stamp(self,x,y,tool,size,strength,softness):
        radius=size/2;h,w=self.depth.shape
        x0=max(0,int(math.floor(x-radius)));x1=min(w,int(math.ceil(x+radius))+1)
        y0=max(0,int(math.floor(y-radius)));y1=min(h,int(math.ceil(y+radius))+1)
        if x0>=x1 or y0>=y1:return
        self._capture((x0,y0,x1,y1))
        yy,xx=np.mgrid[y0:y1,x0:x1].astype(np.float32)
        dist=np.sqrt((xx-x)**2+(yy-y)**2)/radius
        if softness<=1e-6:mask=(dist<=1).astype(np.float32)
        else:
            u=np.clip((1-dist)/softness,0,1);mask=u*u*(3-2*u)
        amount=mask*strength;area=self.depth[y0:y1,x0:x1]
        if tool=='Raise':area[:]=np.clip(area+.15*amount,0,1)
        elif tool=='Lower':area[:]=np.clip(area-.15*amount,0,1)
        elif tool=='Restore':area[:]=area*(1-amount)+self.generated[y0:y1,x0:x1]*amount
        elif tool=='Flatten':area[:]=area*(1-amount)+float(area.mean())*amount
        else:
            # Include a halo, so smoothing does not create a rectangular ROI border.
            halo=12;xa=max(0,x0-halo);ya=max(0,y0-halo);xb=min(w,x1+halo);yb=min(h,y1+halo)
            smooth=cv2.GaussianBlur(self.depth[ya:yb,xa:xb],(0,0),3.)
            area[:]=area*(1-amount)+smooth[y0-ya:y1-ya,x0-xa:x1-xa]*amount

    def end(self):
        if self._box is None:return False
        x0,y0,x1,y1=self._box;after=self.depth[y0:y1,x0:x1].copy()
        changed=not np.array_equal(self._before,after)
        if changed:
            self.undo_stack.append(Patch(self._box,self._before,after));self.redo_stack.clear()
            # Always keep the newest complete action, even if one giant stroke exceeds the budget.
            while len(self.undo_stack)>1 and sum(p.bytes for p in self.undo_stack)>self.history_bytes:self.undo_stack.pop(0)
        self.begin();return changed

    def undo(self):
        if not self.undo_stack:return
        patch=self.undo_stack.pop();x0,y0,x1,y1=patch.box
        self.depth[y0:y1,x0:x1]=patch.before;self.redo_stack.append(patch)

    def redo(self):
        if not self.redo_stack:return
        patch=self.redo_stack.pop();x0,y0,x1,y1=patch.box
        self.depth[y0:y1,x0:x1]=patch.after;self.undo_stack.append(patch)

    def reset(self):
        self.begin();h,w=self.depth.shape;self._capture((0,0,w,h))
        self.depth[:]=self.generated;self.end()
