"""Artistic XYZ cloud from image + depth. CPU/Numba, not scientific reconstruction."""
from dataclasses import dataclass,asdict
import math,os
import cv2
import numpy as np
from .scene3d import Pose,rotation
from .sprites import njit

@dataclass(frozen=True)
class CloudSettings:
    content:str='Full Scene'
    depth_source:str='Hybrid'
    density:float=1.
    thickness:float=.6
    softness:float=.4
    opacity:float=1.
    dust_bias:float=.5
    star_style:str='Sphere'
    star_size:float=1.
    glow:float=.15
    spikes:int=0
    spike_length:float=1.
    spike_width:float=1.
    spike_intensity:float=.3
    spike_rotation:float=0.
    def __post_init__(self):
        if self.content not in ('Full Scene','Nebula Only','Stars Only'):raise ValueError('Unknown scene content')
        if self.depth_source not in ('Hybrid','Luminance','Current Depth Map'):raise ValueError('Unknown depth source')
        if self.star_style not in ('Sphere','Sphere + Glow','Sphere + Spikes','Original Sprite'):raise ValueError('Unknown star style')
        for key,lo,hi in [('density',.1,2),('thickness',0,2),('softness',0,1),('opacity',0,2),('dust_bias',0,1),('star_size',.5,1.5),('glow',0,1),('spike_length',.1,3),('spike_width',.2,3),('spike_intensity',0,2),('spike_rotation',0,360)]:
            v=getattr(self,key)
            if not np.isfinite(v) or not lo<=v<=hi:raise ValueError('Invalid cloud setting: '+key)
        if self.spikes not in (0,4,6,8):raise ValueError('Spikes must be Off, 4, 6 or 8')

@dataclass
class Geometry:
    xyz:np.ndarray
    rgb:np.ndarray
    opacity:np.ndarray
    size:np.ndarray
    density:np.ndarray
    dust:np.ndarray
    requested:int
    quality:str
    source_shape:tuple
    @property
    def memory_bytes(self):return sum(getattr(self,k).nbytes for k in ('xyz','rgb','opacity','size','density','dust'))
    def __len__(self):return len(self.xyz)

def available_ram():
    try:
        if os.name=='nt':
            import ctypes
            class Memory(ctypes.Structure):
                _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('total','available','page','availpage','virtual','availvirtual','extended')]
            m=Memory();m.length=ctypes.sizeof(m)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):return m.available
        return os.sysconf('SC_AVPHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')
    except (ValueError,OSError,AttributeError):return 512*1024**2

def empty_catalog(shape):
    from .star_catalog import StarCatalog,DetectionSettings
    e=np.zeros(0,np.float32)
    return StarCatalog(e,e,e,e,e,e,np.zeros((0,3),np.float32),e,np.zeros(0,np.int32),shape[1],shape[0],DetectionSettings(),0.,(),np.zeros((0,2),np.float32),0)

def build_cloud(image,depth,settings=None,quality='Fast',status=lambda _:None,progress=lambda _:None):
    from .star_catalog import normalized_rgb
    settings=settings or CloudSettings()
    if image is None:raise ValueError('Load a Starless image first')
    if depth is None or depth.shape!=image.shape[:2] or not np.isfinite(depth).all() or depth.min()<0 or depth.max()>1:raise ValueError('A finite matching depth map in [0,1] is required')
    if quality not in ('Fast','High','Final'):raise ValueError('Unknown cloud quality')
    status('Preparing hybrid depth and density…');progress(10)
    h,w=image.shape[:2];scale=min(1.,1200/max(h,w));gw=max(2,round(w*scale));gh=max(2,round(h*scale))
    rgb=normalized_rgb(cv2.resize(image,(gw,gh),interpolation=cv2.INTER_AREA))
    d=cv2.resize(depth,(gw,gh),interpolation=cv2.INTER_AREA).astype(np.float32)
    lum=rgb@np.array([.2126,.7152,.0722],np.float32)
    broad=cv2.GaussianBlur(lum,(0,0),max(2,gw/80));fine=lum-cv2.GaussianBlur(lum,(0,0),1.5)
    dust=np.clip((broad-lum)/max(.04,float(np.percentile(broad,90))),0,1)
    structure=np.abs(fine);signal=np.maximum(lum-.003,0)
    density=(np.sqrt(signal)+2*structure+.8*dust)*(broad>.004)
    density[ (lum<.002)&(dust<.025) ]=0
    if settings.depth_source=='Hybrid':d=np.clip(d+np.clip(fine,-.15,.15)*.25,0,1)
    elif settings.depth_source=='Luminance':d=np.clip(.5+(broad-float(broad.mean()))*.8+fine,0,1)
    d=np.clip(d+dust*(settings.dust_bias-.5)*.5,0,1)
    requested=round({'Fast':75000,'High':180000,'Final':450000}[quality]*settings.density)
    cap=max(1000,min(900000,int(min(192*1024**2,available_ram()*.15)/300)))
    count=min(requested,cap,max(0,int(np.count_nonzero(density))*6))
    if settings.content=='Stars Only':count=0
    if not density.any():count=0
    if count<requested:status('Preview particle density reduced for available memory / source information.')
    rng=np.random.default_rng(1901)
    status('Sampling coherent XYZ volume…');progress(35)
    if count:
        # Adaptive probability sampling; all static data generated once with a fixed seed.
        probability=density.ravel().astype(np.float64);probability/=probability.sum()
        indices=rng.choice(gw*gh,count,p=probability,replace=True)
        iy,ix=indices//gw,indices%gw
        u=(ix+rng.random(count))/gw;v=(iy+rng.random(count))/gh
        noise_rng=np.random.default_rng(1902)
        coherent=np.zeros((gh,gw),np.float32)
        for resolution,weight in ((7,.6),(19,.28),(47,.12)):
            coherent+=cv2.resize(noise_rng.uniform(-1,1,(resolution,resolution)).astype(np.float32),(gw,gh),interpolation=cv2.INTER_CUBIC)*weight
        # Multiple correlated strata, never independent white Z noise.
        layer=(np.arange(count)%5-2)/2
        z=3.-(d[iy,ix]-.5)*2.4+settings.thickness*(layer*.38+coherent[iy,ix]*.45)
        z=np.clip(z,.45,5.8).astype(np.float32)
        tan=math.tan(math.radians(55)/2)
        xyz=np.c_[(u-.5)*2*tan*z,(v-.5)*2*tan*z*h/w,z].astype(np.float32)
        color=rgb[iy,ix].copy();weights=density[iy,ix].astype(np.float32)
        # Sampling-weight compensation keeps local coverage balanced across budgets.
        size=(z*2*tan/np.sqrt(count)*1.35/np.sqrt(np.maximum(weights/float(density.mean()),.25))).astype(np.float32)
        alpha=np.clip(.32+.35*np.sqrt(lum[iy,ix])+.35*dust[iy,ix],.25,.85).astype(np.float32)
        absorption=dust[iy,ix].astype(np.float32)
    else:
        xyz=np.zeros((0,3),np.float32);color=xyz.copy();alpha=np.zeros(0,np.float32);size=alpha.copy();weights=alpha.copy();absorption=alpha.copy()
    geometry=Geometry(xyz,color,alpha,size,weights,absorption,requested,quality,(h,w))
    for field in ('xyz','rgb','opacity','size','density','dust'):getattr(geometry,field).setflags(write=False)
    progress(100);status(f'Cloud ready: {count:,} particles · CPU/Numba · {geometry.memory_bytes/1024**2:.1f} MB')
    return geometry

@njit(cache=True,nogil=True)
def raster_cloud(points,radii,colors,alpha,order,width,height,softness,opacity):
    out=np.zeros((height,width,3),np.float32)
    for j in range(len(order)):
        i=order[j];x=points[i,0];y=points[i,1];r=radii[i]
        if not np.isfinite(x+y+r):continue
        xa=max(0,int(math.floor(x-r*2)));xb=min(width,int(math.ceil(x+r*2))+1)
        ya=max(0,int(math.floor(y-r*2)));yb=min(height,int(math.ceil(y+r*2))+1)
        for py in range(ya,yb):
            for px in range(xa,xb):
                distance=((px-x)**2+(py-y)**2)/max(.2,r*r)
                if distance>4:continue
                a=min(.95,alpha[i]*opacity*math.exp(-distance*(1.6-softness*.7)))
                for c in range(3):out[py,px,c]=out[py,px,c]*(1-a)+colors[i,c]*a
    return out

@njit(cache=True,nogil=True)
def raster_stars(points,radii,colors,gains,width,height,glow,spikes,length,spike_width,intensity,angle):
    out=np.zeros((height,width,3),np.float32)
    for i in range(len(points)):
        x,y=points[i,0],points[i,1];r=radii[i];gain=gains[i]
        if not np.isfinite(x+y+r):continue
        extent=min(48.,max(2.,r*2+(length*16 if spikes and gain>.35 else r*glow*3)))
        for py in range(max(0,int(y-extent)),min(height,int(y+extent)+2)):
            for px in range(max(0,int(x-extent)),min(width,int(x+extent)+2)):
                dx=px-x;dy=py-y;distance=math.sqrt(dx*dx+dy*dy)
                # Projected sphere with antialiased compact limb. No per-frame randomness.
                coverage=max(0.,min(1.,r+.65-distance))
                core=coverage*(.72+.28*math.sqrt(max(0.,1-(distance/max(r,.1))**2)))
                if glow and gain>.35:core+=glow*.15*math.exp(-distance*distance/max(.5,r*r*5))
                if spikes and gain>.35:
                    for k in range(spikes):
                        a=angle+2*math.pi*k/spikes
                        along=dx*math.cos(a)+dy*math.sin(a);across=abs(-dx*math.sin(a)+dy*math.cos(a))
                        if along>r and along<length*16+r:core+=intensity*.18*math.exp(-across*across/max(.2,spike_width*.45)**2)*max(0.,1-along/(length*16+r))
                for c in range(3):out[py,px,c]+=colors[i,c]*gain*core
    return out

class CloudScene:
    """Separate scene adapter implementing the existing camera/video interface."""
    def __init__(self,starless,stars,nebdepth,stardepth=None,out_w=1280,out_h=720,catalog=None,cinematic=None,
                 fast_preview=False,cloud_geometry=None,cloud_settings=None,**unused):
        from .cinematic import CinematicSettings
        from .star_catalog import detect_stars
        self.settings=cloud_settings or CloudSettings();self.w=int(out_w);self.h=int(out_h)
        if self.settings.content!='Nebula Only' and stars is None:raise ValueError('Load a Star Mask for Full Scene / Stars Only')
        self.geometry=cloud_geometry
        if self.geometry is None:raise ValueError('3D Cloud needs rebuild — click Build 3D Cloud')
        self.fast_preview=fast_preview;self.cinematic=cinematic or CinematicSettings();self.anchor_clamped=False
        self.xyz=self.geometry.xyz;self.cloud_sizes=self.geometry.size
        if self.cinematic.enabled and self.cinematic.strength!=1. and len(self.geometry):
            self.xyz=self.geometry.xyz.copy();new_z=np.maximum(.25,3.+(self.xyz[:,2]-3.)*self.cinematic.strength)
            ratio=new_z/self.xyz[:,2];self.xyz[:,:2]*=ratio[:,None];self.xyz[:,2]=new_z
            self.cloud_sizes=self.geometry.size*ratio
        self.catalog=empty_catalog(starless.shape[:2]) if self.settings.content=='Nebula Only' else catalog if catalog is not None else detect_stars(stars)
        self.original=None
        if self.settings.star_style=='Original Sprite' and len(self.catalog):
            from .scene3d import Scene
            self.original=Scene(starless,stars,nebdepth,stardepth,self.w,self.h,catalog=self.catalog,cinematic=self.cinematic)
            self.original.neb=np.zeros_like(self.original.neb);self.original.bands=None
        h,w=starless.shape[:2];self.aspect=h/w;self.fref=.5/math.tan(math.radians(55)/2)
        self.star_xy=np.c_[(self.catalog.x+.5)/w-.5,(self.catalog.y+.5)/h-.5].astype(np.float32)
        self.anchor_z=float(3.-(nebdepth[min(h-1,round(self.cinematic.anchor_y*(h-1))),min(w-1,round(self.cinematic.anchor_x*(w-1)))]-.5)*2.4)
        self.star_ids=np.arange(len(self.catalog),dtype=np.int64)
        self.star_radius=np.maximum(.12/w,self.catalog.radius/w*self.settings.star_size)
        self.star_color=self.catalog.color.copy();self.star_brightness=self.catalog.peak.copy()
    def prepare_sprites(self,bloom=False):
        return self.original.prepare_sprites(bloom) if self.original is not None else None
    def center_pose(self,pose):
        from .cinematic import center_camera
        if self.cinematic.enabled and self.cinematic.centered:
            x=(self.cinematic.anchor_x-.5)*self.anchor_z/self.fref;y=(self.cinematic.anchor_y-.5)*self.aspect*self.anchor_z/self.fref
            return center_camera(pose,max(self.anchor_z,pose.z+.8),x,y)
        return pose
    def pose_at(self,frames,seconds,duration):
        from .cinematic import evaluate_camera
        return self.center_pose(evaluate_camera(frames,seconds,duration,self.cinematic))
    @staticmethod
    def outside_safe_range(pose):return abs(pose.yaw)>35 or abs(pose.pitch)>30 or abs(pose.x)>1.2 or abs(pose.y)>1.
    def project(self,xyz,pose):
        q=(xyz-np.array([pose.x,pose.y,pose.z],np.float32))@rotation(pose).T
        # Preserve source aspect by a centered crop, as Classic does.
        focal=max(self.w,self.h/self.aspect)*self.fref*math.tan(math.radians(55)/2)/math.tan(math.radians(np.clip(pose.fov,15,120))/2)
        z=q[:,2];safe=np.maximum(z,.12)
        xy=np.c_[(self.w-1)/2+focal*q[:,0]/safe,(self.h-1)/2+focal*q[:,1]/safe]
        return xy,z,focal
    def render(self,pose,star_parallax=1.,depth_spread=.6,movement=True,brightness_boost=1.,bloom=False,motion_over_nebula=.35,star_intensity=1.,previous_pose=None):
        g=self.geometry;s=self.settings
        image=np.zeros((self.h,self.w,3),np.float32)
        if s.content!='Stars Only' and len(g):
            xy,z,focal=self.project(self.xyz,pose)
            radius=np.clip(self.cloud_sizes*focal/np.maximum(z,.12)*(1+.6*s.softness),.55,5. if self.fast_preview else 8.)
            visible=(z>.12)&(xy[:,0]>-16)&(xy[:,0]<self.w+16)&(xy[:,1]>-16)&(xy[:,1]<self.h+16)
            indices=np.flatnonzero(visible);order=indices[np.argsort(z[indices])[::-1]]
            image=raster_cloud(xy,radius,g.rgb,g.opacity*np.clip((z-.12)/.18,0,1),order,self.w,self.h,s.softness,s.opacity)
        if s.content!='Nebula Only' and star_intensity>0 and len(self.catalog):
            if self.original is not None:
                overlay=self.original.render(pose,star_parallax,depth_spread,movement,brightness_boost,bloom,motion_over_nebula,star_intensity,previous_pose).astype(np.float32)/255
            else:
                amount=(self.cinematic.strength*self.cinematic.star_motion if self.cinematic.enabled else 1.)
                z=3.-(self.catalog.depth-.5)*3.8*depth_spread*amount
                xyz=np.c_[self.star_xy[:,0]*z/self.fref,self.star_xy[:,1]*z*self.aspect/self.fref,z]
                xy,cz,focal=self.project(xyz,pose)
                # Star parallax remains continuous; zero spread still shares the camera.
                if (star_parallax if movement else 0.)!=1:
                    locked=xyz.copy();locked[:,2]=3.;locked[:,:2]=np.c_[self.star_xy[:,0]*3/self.fref,self.star_xy[:,1]*3*self.aspect/self.fref]
                    base,_,_=self.project(locked,pose);xy=base+(xy-base)*(star_parallax if movement else 0.)
                radius=np.clip(self.star_radius*focal*z/self.fref/np.maximum(cz,.12),.18,10)
                valid=(cz>.12)&(xy[:,0]>-50)&(xy[:,0]<self.w+50)&(xy[:,1]>-50)&(xy[:,1]<self.h+50)
                glow=s.glow if s.star_style=='Sphere + Glow' else 0.
                spikes=s.spikes if s.star_style=='Sphere + Spikes' else 0
                overlay=raster_stars(xy[valid],radius[valid],self.star_color[valid],self.star_brightness[valid]*star_intensity*brightness_boost,self.w,self.h,glow,spikes,s.spike_length,s.spike_width,s.spike_intensity,math.radians(s.spike_rotation))
            image=1-(1-np.clip(image,0,1))*(1-np.clip(overlay,0,1))
        return np.uint8(np.clip(image,0,1)*255+.5)
    def debug_view(self,depth=False,spread=.6):
        return self.render(Pose(),star_intensity=1.)
    def top_view(self,pose,w=900,h=520,depth_spread=.6):
        image=np.zeros((h,w,3),np.uint8);g=self.geometry
        for point,color in zip(g.xyz[::max(1,len(g)//12000)],g.rgb[::max(1,len(g)//12000)]):
            x=round(w/2+point[0]*100);y=round(h*.9-point[2]*65)
            if 0<=x<w and 0<=y<h:image[y,x]=np.uint8(color*255)
        cv2.circle(image,(round(w/2+pose.x*100),round(h*.9-pose.z*65)),5,(255,220,60),-1)
        return image
