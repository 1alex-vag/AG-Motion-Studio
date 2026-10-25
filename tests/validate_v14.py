"""Reproducible synthetic fixture, performance and periodic continuity evidence.

Run from the project directory: python tests/validate_v14.py --output /tmp/astro-v14
Synthetic artwork is a renderer exercise, not a real astronomical observation.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,json,time
from dataclasses import asdict
import cv2
import numpy as np
from PIL import Image
from motionstudio.scene3d import Scene,default_keyframes,render_video_scene
from motionstudio.cinematic import CinematicSettings
from motionstudio.star_catalog import detect_stars


def fixture(w=1280,h=720):
    rng=np.random.default_rng(34)
    yy,xx=np.mgrid[:h,:w].astype(np.float32);x=(xx-w/2)/w;y=(yy-h/2)/h
    broad=np.exp(-((x*2.5)**2+(y*2.3)**2))*np.exp(-((y-.12*np.sin(x*15))/.19)**2)
    noise=np.zeros((h,w),np.float32)
    for scale,weight in [(10,.45),(35,.3),(110,.16),(250,.09)]:
        field=rng.random((max(2,h//scale),max(2,w//scale))).astype(np.float32)
        noise+=cv2.resize(field,(w,h),interpolation=cv2.INTER_CUBIC)*weight
    dust=.6+.4*np.sin(x*15+y*12+noise*10)
    nd=np.clip(.15+.8*broad*(.4+.6*noise),0,1).astype(np.float32)
    neb=np.stack([.008+broad*noise*.55*dust,.009+broad*noise*.16*dust,
                  .018+broad*noise*.38],axis=2).astype(np.float32)
    stars=np.zeros_like(neb)
    for _ in range(1500):
        x1,y1=rng.integers(5,w-5),rng.integers(5,h-5);r=int(rng.choice([1,1,1,2,3]))
        color=np.array([1,.8,.7]) if rng.random()<.5 else np.array([.7,.85,1])
        cv2.circle(stars,(int(x1),int(y1)),r,tuple(color*rng.uniform(.05,.9)),-1)
    return neb,stars,nd


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=args.output;root.mkdir(parents=True,exist_ok=True)
    neb,stars,nd=fixture();catalog=detect_stars(stars)
    config=CinematicSettings(enabled=True,strength=1.1,atmosphere=.30,loop='Seamless Drift')
    frames=default_keyframes(duration=5)
    metrics={'fixture':'seeded synthetic nebula and 1500 drawn stars','detected_stars':len(catalog),'configuration':asdict(config)}
    scenes={}
    for name,w,h,fast in [('fast_preview',640,360,True),('final',1280,720,False)]:
        start=time.perf_counter();sc=Scene(neb,stars,nd,out_w=w,out_h=h,catalog=catalog,fast_preview=fast,cinematic=config)
        scenes[name]=sc;build=time.perf_counter()-start
        sc.render(sc.pose_at(frames,1,5),previous_pose=sc.pose_at(frames,.98,5))
        samples=[]
        for t in [1,1.5,2,2.5,3]:
            start=time.perf_counter();sc.render(sc.pose_at(frames,t,5),previous_pose=sc.pose_at(frames,t-1/60,5));samples.append(time.perf_counter()-start)
        metrics[name]={'build_seconds':build,'median_frame_seconds':float(np.median(samples)),'width':w,'height':h}
    metrics['final_over_fast_ratio']=metrics['final']['median_frame_seconds']/metrics['fast_preview']['median_frame_seconds']
    sc=scenes['fast_preview'];sampled=[]
    for t in [0,1.25,2.5,3.75]:sampled.append(sc.render(sc.pose_at(frames,t,5)))
    Image.fromarray(np.concatenate([np.concatenate(sampled[:2],axis=1),np.concatenate(sampled[2:],axis=1)])).save(root/'cinematic_contact_sheet.png')
    first=sc.render(sc.pose_at(frames,0,5),previous_pose=sc.pose_at(frames,-1/60,5))
    exact=sc.render(sc.pose_at(frames,5,5),previous_pose=sc.pose_at(frames,5-1/60,5))
    last=sc.render(sc.pose_at(frames,5-1/24,5),previous_pose=sc.pose_at(frames,5-1/24-1/60,5))
    next_frame=sc.render(sc.pose_at(frames,1/24,5),previous_pose=sc.pose_at(frames,1/24-1/60,5))
    metrics['exact_endpoint_max_channel_error']=int(np.abs(first.astype(int)-exact.astype(int)).max())
    metrics['wrap_mean_channel_step']=float(np.abs(first.astype(float)-last).mean())
    metrics['first_regular_mean_channel_step']=float(np.abs(next_frame.astype(float)-first).mean())
    export=Scene(neb,stars,nd,out_w=640,out_h=360,catalog=catalog,cinematic=config)
    metrics['encoded_demo']=render_video_scene(export,frames,root/'cinematic_loop_demo.mp4',5,24,encoder='cpu',workers=2)
    (root/'benchmark_v14.json').write_text(json.dumps(metrics,indent=2))
    print(json.dumps(metrics,indent=2))

if __name__=='__main__':main()
