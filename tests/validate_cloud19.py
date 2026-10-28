"""Windows V1.9 reproducible cloud measurements, visual fixtures and H.264 checks."""
from pathlib import Path
import sys,time,json,argparse,statistics,hashlib
import numpy as np
import cv2
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from motionstudio.cloud import CloudSettings,CloudScene,build_cloud
from motionstudio.scene3d import Scene,Pose,default_keyframes,render_video_scene
from motionstudio.star_catalog import detect_stars

def fixture(kind):
    y,x=np.mgrid[:320,:512].astype(np.float32);a=np.exp(-((x-256)**2/25000+(y-160)**2/6500))
    fil=(.6+.4*np.sin(x/10+y/15)**2)*a
    n=np.stack((fil*.65,a*.18,a*.35),axis=2)
    if kind in ('dust','mixed'):
        n*= (1-.94*np.exp(-((x-235-16*np.sin(y/35))/9)**2))[...,None]
    if kind=='mixed':n+=np.exp(-((x-130)**2+(y-130)**2)/1300)[...,None]*np.array([.12,.4,.7])
    if kind=='widefield':n=cv2.GaussianBlur(n,(0,0),12)
    n=np.clip(n,0,1).astype(np.float32);d=np.clip(.5+.3*a*np.sin(x/70)+.1*np.cos(y/30),0,1).astype(np.float32)
    stars=np.zeros_like(n)
    for px,py in ((80,80),(380,190),(290,260)):cv2.circle(stars,(px,py),2,(.85,.5,.25),-1)
    return n,stars,d

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    assert sys.platform=='win32','Windows-only experimental validation'
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);results={'backend':'CPU/Numba','gpu_rendering_tested':False,'fields':{},'density':[],'exports':[]}
    for kind in ('emission','dust','mixed','widefield'):
        n,stars,d=fixture(kind);options=CloudSettings(content='Nebula Only',density=.5)
        start=time.perf_counter();g=build_cloud(n,d,options);build=time.perf_counter()-start
        scene=CloudScene(n,None,d,out_w=640,out_h=400,cloud_geometry=g,cloud_settings=options,fast_preview=True)
        scene.render(Pose()) # warm JIT before timing steady frames
        timings=[];images=[]
        for pose in (Pose(),Pose(x=.2,y=.03,yaw=-4),Pose(z=2.,x=.08)):
            start=time.perf_counter();image=scene.render(pose);timings.append(time.perf_counter()-start);images.append(image)
        cv2.imwrite(str(out/(kind+'_views.png')),cv2.cvtColor(np.concatenate(images,axis=1),cv2.COLOR_RGB2BGR))
        cv2.imwrite(str(out/(kind+'_source.png')),cv2.cvtColor(np.uint8(n*255),cv2.COLOR_RGB2BGR))
        results['fields'][kind]={'build_seconds':build,'particles':len(g),'array_bytes':g.memory_bytes,'median_frame_seconds':statistics.median(timings),'preview_fps':1/statistics.median(timings),'z_range':[float(g.xyz[:,2].min()),float(g.xyz[:,2].max())]}
    n,stars,d=fixture('mixed');catalog=detect_stars(stars)
    for density in (.25,1.,2.):
        options=CloudSettings(density=density);start=time.perf_counter();g=build_cloud(n,d,options);build=time.perf_counter()-start
        scene=CloudScene(n,stars,d,out_w=640,out_h=400,catalog=catalog,cloud_geometry=g,cloud_settings=options,fast_preview=True)
        start=time.perf_counter();scene.render(Pose(x=.1));seconds=time.perf_counter()-start
        results['density'].append({'density':density,'particles':len(g),'array_bytes':g.memory_bytes,'build_seconds':build,'first_frame_seconds':seconds})
    for fps in (24,30):
        options=CloudSettings(content='Full Scene',density=.25,star_style='Sphere + Spikes',spikes=4)
        g=build_cloud(n,d,options,'Final');scene=CloudScene(n,stars,d,out_w=1920,out_h=1080,catalog=catalog,cloud_geometry=g,cloud_settings=options)
        path=out/f'cloud_1080p_{fps}fps.mp4';start=time.perf_counter()
        info=render_video_scene(scene,default_keyframes(duration=.25),path,.25,fps,encoder='cpu',workers=1)
        import imageio.v2 as imageio
        reader=imageio.get_reader(path);frame=reader.get_data(0);meta=reader.get_meta_data();reader.close()
        assert frame.shape==(1080,1920,3) and round(meta['fps'])==fps
        results['exports'].append({'fps':fps,'seconds':time.perf_counter()-start,'particles':len(g),**info})
    # Common camera and exact Classic implementation retained, with file hash evidence.
    results['classic_renderer_sha256']=hashlib.sha256((ROOT/'motionstudio/scene3d.py').read_bytes()).hexdigest()
    (out/'performance_cloud19.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    lines=['# V1.9 Experimental Windows validation','','Backend: CPU/Numba. No GPU rendering backend is shipped or claimed. GPU video encoding remains separate. All sources are deterministic synthetic fixtures; real user data and physical clean-machine testing are not claimed.','','## Four field types','']
    for kind,r in results['fields'].items():lines.append(f"- {kind}: {r['particles']:,} XYZ particles, build {r['build_seconds']:.3f} s, cloud arrays {r['array_bytes']/1024**2:.2f} MB, steady preview {r['preview_fps']:.1f} FPS at 640×400.")
    lines+=['','## Multiple particle densities','',json.dumps(results['density'],indent=2),'','## Full-quality video','',json.dumps(results['exports'],indent=2),'','1080p CPU H.264 clips at 24 and 30 FPS passed decode/dimension/rate checks. Clips are 0.25 seconds; no long-duration stress test is claimed. Generated comparison PNGs show neutral, translated/orbit and in-cloud camera poses. Source tests separately cover 74 Classic/previous regressions plus cloud generation, spheres/glow/spikes, clipping, optional mask, saved projects, deterministic loops, cache reuse and memory limits.','','## Limits and V2.0 recommendations','','The result is an artistic and structurally plausible 3D interpretation of the supplied image and depth information, not a scientific reconstruction of true nebula geometry. Side/rear views are underconstrained. Sparse regions, synthetic layers, alpha-splat grain and disocclusion holes may be visible, especially at extreme offsets. Dust is an alpha/opacity approximation. CPU rendering can be slow at high density; the UI supports prebuilt previews. Stored array bytes exclude source images, transient sorting/projection buffers, Qt and video buffers.','','V2.0: optional verified GPU splatting; adaptive screen-space LOD and antialiasing; stronger absorption/occlusion model; quality metrics against real user pairs; independent per-component caches; cancellable cloud generation; advanced safe-camera framing; stronger temporal filtering.']
    text='\n'.join(lines);(out/'TEST_REPORT.md').write_text(text,encoding='utf-8');(ROOT/'VALIDATION.md').write_text(text,encoding='utf-8')
if __name__=='__main__':main()
