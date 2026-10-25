"""Artistic 2.5D controls and stateless, periodic camera evaluation.

All percentages are stored as fractions. No source image or catalog is mutated.
"""
from dataclasses import dataclass, replace
import math
import cv2
import numpy as np

PRESETS = {
    'Gentle': (.70, .60, .70, .15, .10),
    'Cinematic': (1.10, 1., 1., .30, .25),
    'Deep 3D': (1.50, 1.10, 1.30, .40, .40),
    'Fly-through': (1.70, 1.50, 1.60, .35, .50),
}

@dataclass(frozen=True)
class CinematicSettings:
    enabled: bool = False
    strength: float = 1.
    camera_motion: float = 1.
    star_motion: float = 1.
    atmosphere: float = .25
    loop: str = 'Off'
    path: str = 'Cinematic'
    centered: bool = True
    drift: bool = True
    layer_split: bool = True
    contrast: float = 1.
    smoothing: float = .40
    foreground_limit: float = .50
    motion_blur: float = .15
    depth_haze: float = 1.
    volumetric: bool = False
    volumetric_strength: float = .25
    anchor_x: float = .5
    anchor_y: float = .5

    def __post_init__(self):
        for name, hi in [('strength',2),('camera_motion',2),('star_motion',2),('atmosphere',1),
                         ('volumetric_strength',1),('anchor_x',1),('anchor_y',1),('contrast',2),('smoothing',1),('foreground_limit',1),('motion_blur',1),('depth_haze',1)]:
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0 <= value <= hi:
                raise ValueError(f'Invalid cinematic {name}')
        if self.loop not in ('Off','Ping-Pong','Seamless Orbit','Seamless Drift'):
            raise ValueError('Invalid loop mode')
        if self.path not in ('Linear','Smooth','Cinematic'):
            raise ValueError('Invalid camera path')


def prepared_depth(depth, config):
    """Bounded bilateral filtering preserves edges; contrast changes Z, not RGB."""
    result = np.asarray(depth, np.float32)
    if not config.enabled:
        return result
    if config.smoothing:
        filtered = cv2.bilateralFilter(result, 9, .08, 2 + 7*config.smoothing)
        result = result*(1-config.smoothing) + filtered*config.smoothing
    return np.clip(.5+(result-.5)*config.contrast, 0, 1).astype(np.float32)


def depth_z(depth, config):
    # Stronger range than the legacy surface, centered at the same reference Z.
    amount = 1.20*config.strength if config.enabled else .48
    return 3. - amount*(depth-.5)


def soft_bands(depth):
    """Partition of unity: overlapping, feathered background / middle / foreground."""
    values = np.stack([np.exp(-.5*((depth-c)/.20)**2) for c in (.12,.50,.88)])
    return values / np.maximum(values.sum(axis=0), 1e-9)


def evaluate_camera(keyframes, seconds, duration, config):
    from .scene3d import Pose, camera_at
    if not config.enabled:
        return camera_at(keyframes, seconds)
    frames = sorted(keyframes, key=lambda k:k.time) or [Pose()]
    origin = frames[0]
    seconds = float(seconds)
    duration = max(float(duration), 1e-6)
    # Modulo gives exactly identical transforms at t=0 and t=duration.
    phase = 2*math.pi*((seconds % duration)/duration)
    if config.loop == 'Ping-Pong':
        progress=(seconds % duration)/duration
        # Cubic paths already stop smoothly at each end; avoid double easing.
        travel=(.5-.5*math.cos(phase)) if config.path=='Linear' else (1-abs(2*progress-1))
        sample = origin.time + (frames[-1].time-origin.time)*travel
    else:
        sample = seconds
    pose = camera_at(frames, sample, config.path)
    if config.loop in ('Seamless Orbit','Seamless Drift'):
        # Closed paths use the edited path's extent. Original keyframes stay intact.
        extent = {k:max(abs(getattr(f,k)-getattr(origin,k)) for f in frames)
                  for k in ('x','y','z','yaw','pitch','roll','fov')}
        if config.loop == 'Seamless Orbit':
            wave = dict(x=math.sin(phase), y=.5*math.sin(2*phase), z=1-math.cos(phase),
                        yaw=math.sin(phase),pitch=.5*math.sin(2*phase),roll=math.sin(phase),fov=1-math.cos(phase))
        else:
            wave = dict(x=math.sin(phase), y=.7*(math.sin(phase+.8)-math.sin(.8)),
                        z=.5*(1-math.cos(phase)),yaw=math.sin(phase+.4)-math.sin(.4),
                        pitch=.5*math.sin(2*phase),roll=.5*math.sin(phase),fov=.5*(1-math.cos(phase)))
        pose = Pose(time=seconds, **{k:getattr(origin,k)+extent[k]*wave[k] for k in extent})
    scale = config.camera_motion
    pose = replace(pose, time=seconds, **{k:getattr(origin,k)+(getattr(pose,k)-getattr(origin,k))*scale
                       for k in ('x','y','z','yaw','pitch','roll','fov')})
    if config.drift and scale:
        # Periodic drift also closes on ping-pong; zero camera motion is static.
        pose = replace(pose, x=pose.x+.008*scale*math.sin(phase),
                       y=pose.y+.005*scale*math.sin(2*phase),
                       yaw=pose.yaw+.08*scale*math.sin(phase),
                       pitch=pose.pitch+.05*scale*math.sin(2*phase))
    if config.centered:
        pose = center_camera(pose)
    return pose


def center_camera(pose,target_z=3.,target_x=0.,target_y=0.):
    """Aim the shared camera at the center of the reference nebula surface."""
    # Look-at controls yaw/pitch; roll and FOV remain editable.
    dx,dy,dz=float(target_x)-pose.x,float(target_y)-pose.y,float(target_z)-pose.z
    return replace(pose,yaw=math.degrees(math.atan2(dx,dz)),
                   pitch=math.degrees(math.atan2(dy,math.hypot(dx,dz))))
