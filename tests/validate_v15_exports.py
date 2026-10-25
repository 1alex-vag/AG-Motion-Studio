"""Real CPU MP4 encode/decode for every prescribed resolution and FPS.

Tiny synthetic source, one rendered frame per combination: verifies dimensions,
frame rate and full-quality render/encoder plumbing, not a long-duration stress test.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,gc,json,time
import numpy as np
import cv2
import imageio.v2 as imageio
from motionstudio.scene3d import Scene,default_keyframes,render_video_scene
from motionstudio.cinematic import CinematicSettings
from motionstudio.export_settings import RESOLUTIONS


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=args.output;root.mkdir(parents=True,exist_ok=True)
    yy,xx=np.mgrid[:90,:160];nd=(.5+.4*np.sin(xx/20)*np.cos(yy/15)).astype(np.float32)
    neb=np.stack([nd*.3,nd*.12,nd*.22],axis=2);stars=np.zeros((90,160,3),np.uint8)
    cv2.circle(stars,(55,40),2,(220,170,100),-1)
    records=[]
    for orientation,sizes in RESOLUTIONS.items():
        for w,h in sizes:
            scene=Scene(neb,stars,nd,out_w=w,out_h=h,cinematic=CinematicSettings(enabled=True,volumetric=True))
            for fps in [24,30,60]:
                start=time.perf_counter();path=root/f'{orientation}_{w}x{h}_{fps}fps.mp4'
                info=render_video_scene(scene,default_keyframes(duration=1/fps),path,1/fps,fps,encoder='cpu',workers=1)
                reader=imageio.get_reader(path);decoded=reader.get_data(0);meta=reader.get_meta_data();reader.close()
                assert decoded.shape==(h,w,3) and abs(meta['fps']-fps)<.1 and info['frames']==1
                record=dict(orientation=orientation,width=w,height=h,fps=fps,frames=1,seconds=time.perf_counter()-start,ok=True)
                records.append(record);print(json.dumps(record),flush=True)
            del scene;gc.collect()
    (root/'export_matrix_v15.json').write_text(json.dumps(records,indent=2))

if __name__=='__main__':main()
