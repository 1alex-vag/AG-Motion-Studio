"""AG Astro Motion Studio: deterministic 3D star particles + depth-aware nebula camera.

3D star camera is perspective; nebula is a 2.5D depth surface (not volumetric).
Original star sprites are detected and isolated once at source resolution.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
import numpy as np
import cv2

@dataclass
class Pose:
    time: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    fov: float = 55.0


def default_keyframes(mode='Parallax', duration=8):
    begin = Pose(time=0)
    if mode == 'Fly-through':
        end = Pose(time=float(duration), x=.05, y=.025, z=.75, yaw=0, pitch=0, fov=55)
    elif mode == 'Push In':
        end = Pose(time=float(duration), z=.35)
    elif mode == 'Pull Out':
        end = Pose(time=float(duration), z=-.35)
    elif mode == 'Side Drift':
        end = Pose(time=float(duration), x=.24, y=.02)
    elif mode == 'Orbit':
        end = Pose(time=float(duration), x=.32, y=.09, z=.12, yaw=-4, pitch=1, fov=55)
    else:
        end = Pose(time=float(duration), x=.24, y=.07, z=.08, yaw=-1.5, pitch=.5, fov=55)
    return [begin, end]


def camera_at(keyframes, seconds, interpolation='Smooth'):
    """Time-aware cubic Hermite camera path; smoothstep remains the legacy default."""
    seconds=float(seconds)
    frames=sorted(keyframes,key=lambda p:p.time)
    if not frames:return Pose()
    if seconds<=frames[0].time:return Pose(**asdict(frames[0]))
    if seconds>=frames[-1].time:return Pose(**asdict(frames[-1]))
    for i,(a,b) in enumerate(zip(frames,frames[1:])):
        if a.time<=seconds<=b.time:
            dt=max(1e-9,b.time-a.time);u=(seconds-a.time)/dt
            values={}
            for k in ('x','y','z','yaw','pitch','roll','fov'):
                av,bv=getattr(a,k),getattr(b,k)
                if interpolation=='Cinematic':
                    prev=frames[max(0,i-1)];nxt=frames[min(len(frames)-1,i+2)]
                    m0=0. if i==0 else (bv-getattr(prev,k))/max(1e-9,b.time-prev.time)
                    m1=0. if i+2>=len(frames) else (getattr(nxt,k)-av)/max(1e-9,nxt.time-a.time)
                    values[k]=(2*u**3-3*u*u+1)*av+(u**3-2*u*u+u)*dt*m0+(-2*u**3+3*u*u)*bv+(u**3-u*u)*dt*m1
                else:
                    f=u if interpolation=='Linear' else u*u*(3-2*u)
                    values[k]=av*(1-f)+bv*f
            return Pose(time=seconds,**values)
    return Pose(**asdict(frames[-1]))


def _rotate(dx, dy, dz, pose):
    yaw, pitch, roll = map(math.radians, (pose.yaw, pose.pitch, pose.roll))
    co, si = math.cos(yaw), math.sin(yaw)
    x, z = co*dx-si*dz, si*dx+co*dz
    co, si = math.cos(pitch), math.sin(pitch)
    y, z = co*dy-si*z, si*dy+co*z
    co, si = math.cos(roll), math.sin(roll)
    return co*x-si*y, si*x+co*y, z


def rotation(pose):
    # Columns are rotated world basis vectors. Same camera for surface and stars.
    return np.column_stack([_rotate(*v, pose) for v in np.eye(3)]).astype(np.float32)


def _sample_map_points(image, xs, ys, interpolation=cv2.INTER_LINEAR, border_mode=cv2.BORDER_REFLECT_101):
    """Vectorized point sampler with no OpenCV source/destination SHRT_MAX limit."""
    xs=np.asarray(xs,np.float32).ravel();ys=np.asarray(ys,np.float32).ravel()
    if xs.size!=ys.size:raise ValueError('Point coordinate arrays must have identical lengths')
    h,w=image.shape[:2]
    def reflect(a,size):
        if size<2:return np.zeros_like(a)
        a=np.mod(a,2*(size-1));return np.minimum(a,2*(size-1)-a)
    xs=reflect(xs,w);ys=reflect(ys,h)
    if interpolation==cv2.INTER_NEAREST:return image[np.rint(ys).astype(int),np.rint(xs).astype(int)]
    x0=np.floor(xs).astype(int);y0=np.floor(ys).astype(int)
    x1=np.minimum(x0+1,w-1);y1=np.minimum(y0+1,h-1);fx=xs-x0;fy=ys-y0
    return ((image[y0,x0]*(1-fx)+image[y0,x1]*fx)*(1-fy)+
            (image[y1,x0]*(1-fx)+image[y1,x1]*fx)*fy).astype(np.float32)


class Scene:
    def __init__(self, starless, stars, nebdepth, stardepth=None, out_w=1280, out_h=720,
                 catalog=None, detection=None, protection=None, fast_preview=False, synthetic_density=0, cinematic=None, star_style=None, atlas_cache=None):
        from .engine import _fit_rgb
        from .star_catalog import detect_stars, normalized_rgb, with_synthetic_background
        from .protection import nebula_protection
        if starless.shape[:2] != stars.shape[:2]:
            raise ValueError('Starless and star mask dimensions do not match')
        self.w, self.h = int(out_w), int(out_h)
        self.catalog = catalog if catalog is not None else detect_stars(stars,detection)
        if synthetic_density:self.catalog=with_synthetic_background(self.catalog,synthetic_density)
        self.fast_preview=bool(fast_preview)
        from .cinematic import CinematicSettings, prepared_depth, depth_z, soft_bands
        self.cinematic=cinematic or CinematicSettings()
        self.source_nd=nebdepth
        self.protection=protection if protection is not None else nebula_protection(starless)
        self._atlas_cache={} if atlas_cache is None else atlas_cache
        self.star_style=dict(star_style or {})
        self.neb = normalized_rgb(_fit_rgb(starless,self.w,self.h))
        self.nd = prepared_depth(_fit_rgb(nebdepth,self.w,self.h).astype(np.float32),self.cinematic)
        if self.cinematic.enabled and not (self.cinematic.layer_split or self.cinematic.volumetric):
            haze=(self.cinematic.atmosphere*self.cinematic.depth_haze*(1-self.nd))[...,None]
            soft=cv2.GaussianBlur(self.neb,(0,0),max(.1,self.w/900))
            self.neb=self.neb*(1-.25*haze)+soft*(.25*haze)
            grey=self.neb.mean(axis=2,keepdims=True)
            self.neb=(self.neb*(1-.12*haze)+grey*(.12*haze))*(1-.08*haze)+.02*haze
        self.base_depth = 3.
        self.f0 = .5*self.w/math.tan(math.radians(55)/2)
        self.cx, self.cy = (self.w-1)/2, (self.h-1)/2
        ih, iw = starless.shape[:2]
        if iw/ih > self.w/self.h:
            cw, ch = max(1,round(ih*self.w/self.h)), ih
            ox, oy = (iw-cw)//2, 0
        else:
            cw, ch = iw, max(1,round(iw*self.h/self.w))
            ox, oy = 0, (ih-ch)//2
        c = self.catalog
        self.x = (c.x-ox+.5)*self.w/cw-.5
        self.y = (c.y-oy+.5)*self.h/ch-.5
        self.star_importance=np.clip(c.radius/max(1.,float(np.percentile(c.radius,75))) if len(c) else c.radius,0,1)
        self.radius = c.radius * .5*(self.w/cw+self.h/ch)
        self.crop=(ox,oy,cw,ch)
        self.sx,self.sy=self.w/cw,self.h/ch
        self.surface_z = depth_z(_sample_map_points(self.nd,self.x,self.y) if self.cinematic.enabled
                                  else _sample_map_points(nebdepth,c.x,c.y),self.cinematic)
        self.bands=soft_bands(self.nd) if self.cinematic.enabled and (self.cinematic.layer_split or self.cinematic.volumetric) else None
        values=np.array([float(np.sum(self.nd*mask)/max(float(mask.sum()),1e-9))
                         for mask in self.bands],np.float32) if self.bands is not None else np.array([.12,.50,.88],np.float32)
        self.band_z=depth_z(values,self.cinematic)
        volume=self.cinematic.volumetric_strength if self.cinematic.enabled and self.cinematic.volumetric else 0.
        self.band_z=3.+(self.band_z-3.)*(1+.18*volume)
        # A gentle distant-layer treatment; no new image structures are generated.
        self.layer_images=[]
        if self.bands is not None:
            for d in (.12,.50,.88):
                haze=self.cinematic.atmosphere*self.cinematic.depth_haze*(1-d)
                soft=cv2.GaussianBlur(self.neb,(0,0),max(.1,self.w/900)) if haze else self.neb
                image=self.neb*(1-.25*haze)+soft*(.25*haze)
                grey=image.mean(axis=2,keepdims=True)
                image=(image*(1-.12*haze)+grey*(.12*haze))*(1-.08*haze)+.02*haze
                if volume:
                    # Weak opacity, softness, haze and glow, all from existing pixels.
                    soft=cv2.GaussianBlur(image,(0,0),max(.4,self.w/500))
                    glow=cv2.GaussianBlur(np.maximum(image-.12,0),(0,0),max(1.,self.w/180))
                    distant=1-d
                    image=(image*(1-.2*volume*distant)+soft*(.2*volume*distant))*(1-.08*volume*distant)
                    image+=.008*volume*distant+.04*volume*glow
                self.layer_images.append(image.astype(np.float32))
        self.layer_premultiplied=[image*mask[...,None] for image,mask in zip(self.layer_images,self.bands)] if self.bands is not None else []
        ax=(self.cinematic.anchor_x*(iw-1)-ox+.5)*self.sx-.5
        ay=(self.cinematic.anchor_y*(ih-1)-oy+.5)*self.sy-.5
        self.anchor_clamped=not (0<=ax<self.w and 0<=ay<self.h)
        ax=float(np.clip(ax,0,self.w-1));ay=float(np.clip(ay,0,self.h-1))
        self.anchor_pixel=(ax,ay)
        center_depth=float(_sample_map_points(self.nd,[ax],[ay])[0])
        self.anchor_z=float(depth_z(center_depth,self.cinematic))
        if self.bands is not None:
            weights=np.array([_sample_map_points(mask,[ax],[ay])[0] for mask in self.bands])
            self.anchor_z=float(np.dot(weights,.7*self.band_z+.3*self.anchor_z))
        self.anchor_world=((ax-self.cx)*self.anchor_z/self.f0,(ay-self.cy)*self.anchor_z/self.f0,self.anchor_z)
        self.source_protection=_sample_map_points(self.protection,c.x,c.y)
        yy,xx = np.mgrid[:self.h,:self.w].astype(np.float32)
        self.ray_x=(xx-self.cx)/self.f0;self.ray_y=(yy-self.cy)/self.f0
        self.flat_depth=float(np.mean(self.nd)) if np.ptp(self.nd)<1e-6 else None
        # Prepare static templates once, before parallel workers start.
        self.prepare_sprites(False)

    def prepare_sprites(self,bloom=False):
        from .sprites import prepare_atlas
        if bloom not in self._atlas_cache:
            self._atlas_cache[bloom]=prepare_atlas(self.catalog,self.sx,self.sy,bloom,self.star_style)
        return self._atlas_cache[bloom]

    def _project(self, pose, depth):
        X = (self.x-self.cx)*depth/self.f0
        Y = (self.y-self.cy)*depth/self.f0
        q = rotation(pose) @ np.array([X-pose.x,Y-pose.y,depth-pose.z])
        focal = .5*self.w/math.tan(math.radians(np.clip(pose.fov,15,120))/2)
        safe = np.maximum(q[2],.08)
        return np.column_stack((self.cx+focal*q[0]/safe,self.cy+focal*q[1]/safe)), focal/self.f0*depth/safe, q[2]>.08

    def _inverse_surface_points(self,pose,points):
        """Where projected stars land on the nebula, in source-image coordinates."""
        focal=.5*self.w/math.tan(math.radians(np.clip(pose.fov,15,120))/2)
        rays=np.c_[(points[:,0]-self.cx)/focal,(points[:,1]-self.cy)/focal,np.ones(len(points))]
        world=rays@rotation(pose)
        safe=np.where(np.abs(world[:,2])>.0001,world[:,2],.0001)
        depth=np.full(len(points),3.,np.float32)
        ox,oy,cw,ch=self.crop
        for _ in range(4):
            dist=(depth-pose.z)/safe
            sx=self.cx+self.f0*(pose.x+dist*world[:,0])/depth
            sy=self.cy+self.f0*(pose.y+dist*world[:,1])/depth
            source_x=(sx+.5)/self.sx-.5+ox;source_y=(sy+.5)/self.sy-.5+oy
            depth=self._depth_z(_sample_map_points(self.nd,sx,sy) if self.cinematic.enabled
                                else _sample_map_points(self.source_nd,source_x,source_y))
        return source_x,source_y

    def project_stars(self, pose, star_parallax=1., depth_spread=.6, movement=True, motion_over_nebula=.35):
        spread = np.clip(depth_spread,0,1)
        config=self.cinematic
        amount=config.strength if config.enabled else 1.
        star_motion=config.star_motion if config.enabled else 1.
        depth = 3.+(self.catalog.depth-.5)*(-3.8)*spread*amount*star_motion
        if config.enabled:
            # Softly keep the largest observed stars out of the nearest plane.
            floor=.65+config.foreground_limit*self.star_importance*.85
            depth=np.maximum(depth,floor)
        depth=np.maximum(depth,.25)
        normal, scale, valid = self._project(pose,depth)
        locked, lockscale, lockvalid = self._project(pose,self.surface_z)
        par=float(np.clip(star_parallax*star_motion,0,3)) if movement else 0.
        protection=self.source_protection
        amount=float(np.clip(motion_over_nebula,0,1))
        if amount<1 and par>0 and len(normal):
            # Protect both origins and possible destinations. A faint field star
            # moving into a bright core also gets a smooth reduction in motion.
            destination=locked+par*(normal-locked)
            candidates=(destination[:,0]>=0)&(destination[:,0]<self.w)&(destination[:,1]>=0)&(destination[:,1]<self.h)&lockvalid
            xs,ys=self._inverse_surface_points(pose,destination[candidates])
            incoming=_sample_map_points(self.protection,xs,ys)
            ox,oy,cw,ch=self.crop
            inside=(xs>=ox)&(xs<ox+cw)&(ys>=oy)&(ys<oy+ch)
            protection=protection.copy()
            protection[candidates]=np.maximum(protection[candidates],np.where(inside,incoming,0))
        response=par*(1-protection*(1-amount))
        centers=locked+response[:,None]*(normal-locked)
        sizes=np.clip(lockscale+response*(scale-lockscale),.05,12)
        return centers,sizes,lockvalid & (valid | (response<1e-6)),depth

    def _depth_z(self, values):
        from .cinematic import depth_z
        return depth_z(values,self.cinematic)

    def pose_at(self,keyframes,seconds,duration):
        from .cinematic import evaluate_camera
        return self.center_pose(evaluate_camera(keyframes,seconds,duration,self.cinematic))

    def center_pose(self,pose):
        from .cinematic import center_camera
        return center_camera(pose,self.anchor_z,*self.anchor_world[:2]) if self.cinematic.enabled and self.cinematic.centered else pose

    def render_nebula(self, pose):
        if self.bands is not None:
            return self._render_layers(pose)
        return self._render_surface(pose)

    def _render_layers(self,pose):
        # Warp premultiplied soft masks and normalize coverage, avoiding dark seams.
        # Each band retains local depth variation rather than becoming a rigid card.
        factor=math.tan(math.radians(np.clip(pose.fov,15,120))/2)/math.tan(math.radians(55)/2)
        r=rotation(pose);rx=self.ray_x*factor;ry=self.ray_y*factor
        wx=rx*r[0,0]+ry*r[1,0]+r[2,0];wy=rx*r[0,1]+ry*r[1,1]+r[2,1]
        wz=rx*r[0,2]+ry*r[1,2]+r[2,2];safe=np.where(np.abs(wz)>.0001,wz,.0001)
        output=np.zeros_like(self.neb);coverage=np.zeros((self.h,self.w),np.float32)
        for index,(mask,image,z) in enumerate(zip(self.bands,self.layer_images,self.band_z)):
            depth=np.full((self.h,self.w),z,np.float32)
            for _ in range(1 if self.fast_preview else 3):
                distance=(depth-pose.z)/safe
                sx=(self.cx+self.f0*(pose.x+distance*wx)/depth).astype(np.float32)
                sy=(self.cy+self.f0*(pose.y+distance*wy)/depth).astype(np.float32)
                nd=cv2.remap(self.nd,sx,sy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
                depth=z+.30*(self._depth_z(nd)-z)
            distance=(depth-pose.z)/safe
            sx=(self.cx+self.f0*(pose.x+distance*wx)/depth).astype(np.float32)
            sy=(self.cy+self.f0*(pose.y+distance*wy)/depth).astype(np.float32)
            weight=cv2.remap(mask,sx,sy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
            weight=np.where((distance>.08)&(wz>0),weight,0)
            output+=cv2.remap(self.layer_premultiplied[index],sx,sy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)*((distance>.08)&(wz>0))[...,None]
            coverage+=weight
        return output/np.maximum(coverage[...,None],1e-6)

    def _render_surface(self, pose):
        if all(abs(getattr(pose,k))<1e-8 for k in ('x','y','z','yaw','pitch','roll')) and abs(pose.fov-55)<1e-8:
            return self.neb
        factor=math.tan(math.radians(np.clip(pose.fov,15,120))/2)/math.tan(math.radians(55)/2)
        r=rotation(pose)
        # Avoid a full HxWx3 rays/world allocation and per-pixel matrix multiply.
        rx=self.ray_x*factor;ry=self.ray_y*factor
        wx=rx*r[0,0]+ry*r[1,0]+r[2,0]
        wy=rx*r[0,1]+ry*r[1,1]+r[2,1]
        wz=rx*r[0,2]+ry*r[1,2]+r[2,2]
        safe=np.where(np.abs(wz)>.0001,wz,.0001)
        depth=self._depth_z(self.flat_depth) if self.flat_depth is not None else np.full((self.h,self.w),3.,np.float32)
        iterations=1 if self.flat_depth is not None else (2 if self.fast_preview else 5)
        for _ in range(iterations):
            distance=(depth-pose.z)/safe
            sx=self.cx+self.f0*(pose.x+distance*wx)/depth
            sy=self.cy+self.f0*(pose.y+distance*wy)/depth
            if self.flat_depth is None:
                nd=cv2.remap(self.nd,sx.astype(np.float32,copy=False),sy.astype(np.float32,copy=False),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
                depth=self._depth_z(nd)
        neb=cv2.remap(self.neb,sx.astype(np.float32,copy=False),sy.astype(np.float32,copy=False),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
        neb[(distance<=.08)|(wz<=0)]=0
        return neb

    def render(self, pose, star_parallax=1., depth_spread=.6, movement=True, brightness_boost=1., bloom=False,
               motion_over_nebula=.35, star_intensity=1., previous_pose=None):
        from .sprites import draw_atlas
        neb=self.render_nebula(pose)
        # Changing intensity never changes the catalog, sizes or depth.
        if star_intensity<=0:return np.uint8(np.clip(neb,0,1)*255+.5)
        centers,scales,valid,depth=self.project_stars(pose,star_parallax,depth_spread,movement,motion_over_nebula)
        atlas,meta=self.prepare_sprites(bloom)
        if len(meta):
            left=centers[:,0]-(meta[:,3]+.5)*scales;top=centers[:,1]-(meta[:,4]+.5)*scales
            valid &= (left<self.w)&(top<self.h)&(left+meta[:,1]*scales>0)&(top+meta[:,2]*scales>0)
        intensity=float(np.clip(star_intensity,0,2))*max(0,float(brightness_boost))
        over=draw_atlas(atlas,meta,centers,scales,valid,self.w,self.h,intensity)
        if self.cinematic.enabled and self.cinematic.motion_blur and previous_pose is not None:
            old,_,_,_=self.project_stars(previous_pose,star_parallax,depth_spread,movement,motion_over_nebula)
            delta=np.nan_to_num(centers-old)
            # Depth-weighted shutter span; distant stars remain sharp.
            weight=np.clip((3.-depth)/2.,0,1)*self.cinematic.motion_blur
            count=2 if self.fast_preview else 4
            for sample in range(1,count):
                point=centers-delta*(weight*sample/(count-1))[:,None]
                over+=draw_atlas(atlas,meta,point,scales,valid,self.w,self.h,intensity)
            over/=count

        return np.uint8(np.clip(1-(1-neb)*(1-np.clip(over,0,1)),0,1)*255+.5)

    def debug_view(self, depth=False, spread=.6):
        img = np.zeros((self.h,self.w,3),np.uint8)
        for i,(x,y,r) in enumerate(zip(self.x,self.y,self.radius)):
            if not (0<=x<self.w and 0<=y<self.h): continue
            d = .5+(self.catalog.depth[i]-.5)*spread
            color = (round(255*d),100,round(255*(1-d))) if depth else (110,230,160)
            cv2.circle(img,(round(float(x)),round(float(y))),max(2,round(float(r))),color,1)
        return img

    def top_view(self,pose,w=900,h=520,depth_spread=.6):
        img=np.full((h,w,3),(13,20,32),np.uint8)
        _,_,_,depth=self.project_stars(Pose(),1,depth_spread)
        for z in (1.,2.,3.,4.,5.):
            py=round(h*.85-z*70)
            cv2.line(img,(20,py),(w-20,py),(45,62,81),1)
            cv2.putText(img,f'Z {z:.0f}',(24,py-8),cv2.FONT_HERSHEY_SIMPLEX,.45,(156,180,202),1)
        stride=max(1,len(depth)//2800)
        for i in range(0,len(depth),stride):
            X=(self.x[i]-self.cx)*depth[i]/self.f0
            px=round(w/2+X*100); py=round(h*.85-depth[i]*70)
            if 0<=px<w and 0<=py<h:cv2.circle(img,(px,py),1,(190,220,240),-1)
        cx=round(w/2+pose.x*100);cy=round(h*.85-pose.z*70)
        cv2.circle(img,(cx,cy),8,(50,196,255),-1)
        cv2.putText(img,'TOP VIEW - artistic star depths / camera',(22,30),cv2.FONT_HERSHEY_SIMPLEX,.6,(214,223,240),1)
        return img


def render_video_scene(scene, keyframes, path, duration, fps, star_parallax=1., depth_spread=.6,
                       progress=None, movement=True, brightness_boost=1., bloom=False,
                       motion_over_nebula=.35, star_intensity=1., workers=0, encoder='auto',status=None,quality=18):
    from .video import render_video
    return render_video(scene,keyframes,path,duration,fps,star_parallax,depth_spread,progress,
                        movement,brightness_boost,bloom,motion_over_nebula,star_intensity,workers,encoder,status,quality)
