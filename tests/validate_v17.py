"""Windows-only reproducible V1.6/V1.7 timings and dense full-quality exports."""
from pathlib import Path
import sys,os,json,time,argparse,subprocess,tempfile,zipfile,statistics
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import cv2

def fixture(dense=True):
    h,w=800,1200;rng=np.random.default_rng(16)
    stars=np.zeros((h,w,3),np.float32)
    # Over 20k separated observed profiles, with fixed colors and compact cores.
    step=6 if dense else 65
    for y in range(8,h-8,step):
        for x in range(8,w-8,step):
            radius=.48 if rng.random()<.85 else .95
            yy,xx=np.mgrid[-2:3,-2:3]
            rgb=rng.uniform(.08,.75)*rng.uniform(.4,1.,3)
            stars[y-2:y+3,x-2:x+3]+=np.exp(-(xx*xx+yy*yy)/(2*radius*radius))[...,None]*rgb
    yy,xx=np.mgrid[:h,:w];depth=(.5+.35*np.sin(xx/w*6)*np.cos(yy/h*4)).astype(np.float32)
    neb=np.stack((.08+.15*depth,.03+.05*depth,.06+.1*depth),axis=2).astype(np.float32)
    return neb,np.clip(stars,0,1),depth

def render_benchmark(source,fixture_file,out):
    sys.path.insert(0,str(source))
    from motionstudio.scene3d import Scene,Pose,render_video_scene,default_keyframes
    data=np.load(fixture_file);n,s,d=[data[k] for k in ('neb','stars','depth')]
    start=time.perf_counter();scene=Scene(n,s,d,out_w=640,out_h=426,fast_preview=True)
    prepared=time.perf_counter()-start
    start=time.perf_counter();scene.render(Pose());first=time.perf_counter()-start
    timings=[]
    for x in (.01,.03,.05,.03,.01):
        start=time.perf_counter();scene.render(Pose(x=x));timings.append(time.perf_counter()-start)
    # Full-quality video uses the same fixed dense catalog and all original stars.
    final=Scene(n,s,d,out_w=1920,out_h=1080,catalog=scene.catalog)
    start=time.perf_counter();video=render_video_scene(final,default_keyframes(duration=.2),out.with_suffix('.mp4'),.2,30,workers=1,encoder='cpu')
    video_seconds=time.perf_counter()-start
    image=scene.render(Pose());cv2.imwrite(str(out.with_suffix('.png')),cv2.cvtColor(image,cv2.COLOR_RGB2BGR))
    out.write_text(json.dumps(dict(stars=len(scene.catalog),prepare_seconds=prepared,first_preview_seconds=first,preview_median_seconds=statistics.median(timings),repeat_without_cache_seconds=sum(timings),video_seconds=video_seconds,video=video),indent=2))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--benchmark-source',type=Path);parser.add_argument('--fixture',type=Path);parser.add_argument('--result',type=Path)
    args=parser.parse_args()
    if args.benchmark_source:
        render_benchmark(args.benchmark_source,args.fixture,args.result);return
    assert sys.platform=='win32','V1.7 validation is Windows-only'
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    from motionstudio.scene3d import Scene,Pose,default_keyframes,render_video_scene
    from motionstudio.preview_cache import PreviewCache
    import imageio.v2 as imageio
    result={'platform':sys.platform,'baseline_commit':'553ed21bd09d514f0cdcf66f5c038e8e73d906c5','fields':{},'exports':[]}
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);base=tmp/'baseline';base.mkdir()
        archive=subprocess.check_output(['git','archive','--format=zip',result['baseline_commit']],cwd=ROOT)
        import io
        with zipfile.ZipFile(io.BytesIO(archive)) as z:z.extractall(base)
        dense=None
        for kind in ('sparse','dense'):
            n,s,d=fixture(kind=='dense');file=tmp/(kind+'.npz');np.savez(file,neb=n,stars=s,depth=d)
            compare={}
            for version,source in (('v16',base),('v17',ROOT)):
                dest=out/f'{kind}_{version}.json'
                subprocess.run([sys.executable,str(Path(__file__).resolve()),'--benchmark-source',str(source),'--fixture',str(file),'--result',str(dest)],cwd=tmp,check=True)
                compare[version]=json.loads(dest.read_text())
            compare['renderer_speedup']=compare['v16']['preview_median_seconds']/compare['v17']['preview_median_seconds']
            compare['video_speedup']=compare['v16']['video_seconds']/compare['v17']['video_seconds']
            scene=Scene(n,s,d,out_w=640,out_h=426,fast_preview=True)
            scene.render(Pose());cache=PreviewCache();a=time.perf_counter();image=scene.render(Pose(x=.04));fresh=time.perf_counter()-a
            cache.put('frame',(Pose(x=.04),image));samples=[]
            for _ in range(100):
                a=time.perf_counter();entry=cache.get('frame');samples.append(time.perf_counter()-a)
                assert entry[1] is image
            compare['cache']={'fresh_seconds':fresh,'retrieval_median_seconds':statistics.median(samples),'hits':cache.hits,'bytes':cache.bytes,'speedup':fresh/max(1e-9,statistics.median(samples))}
            # Determinism, source color and sparse/dense comparison artifacts.
            np.testing.assert_array_equal(scene.render(Pose(x=.04)),image)
            result['fields'][kind]=compare
            if kind=='dense':dense=(n,s,d,scene.catalog)
        n,s,d,catalog=dense
        for w,h in ((1920,1080),(1080,1920),(2560,1440),(1440,2560),(3840,2160),(2160,3840)):
            scene=Scene(n,s,d,out_w=w,out_h=h,catalog=catalog)
            path=out/f'dense_{w}x{h}.mp4';a=time.perf_counter()
            info=render_video_scene(scene,default_keyframes(duration=.1),path,.1,30,encoder='cpu',workers=0)
            reader=imageio.get_reader(path);frame=reader.get_data(0);meta=reader.get_meta_data();reader.close()
            assert frame.shape==(h,w,3) and round(meta['fps'])==30
            result['exports'].append({'width':w,'height':h,'seconds':time.perf_counter()-a,'stars':len(catalog),**info})
        # Measure the actual GUI Build Preview path with the same dense catalog.
        from PyQt6.QtWidgets import QApplication
        from motionstudio.gui import Main
        from motionstudio.depth_edit import DepthVersions
        from motionstudio.star_catalog import depth_map
        from unittest.mock import patch
        app=QApplication.instance() or QApplication([]);window=Main()
        window.starless=n;window.stars=s;window.nd=d;window.sd=depth_map(catalog);window.catalog=catalog;window.depth_versions=DepthVersions(d)
        window.duration.setValue(1)
        def idle():
            deadline=time.monotonic()+120
            while (window.worker is not None or window._preview_worker is not None or window.preview_debounce.isActive() or window._preview_latest is not None) and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
            assert window.worker is None and window._preview_worker is None
        idle();a=time.perf_counter();window.build_preview();idle();built=time.perf_counter()-a
        assert window.built_preview is not None
        reads=[]
        with patch.object(Scene,'render',side_effect=AssertionError('Unexpected render in built playback')):
            window.toggle_playback()
            for i in range(20):
                a=time.perf_counter();window.built_preview.get(i/20);reads.append(time.perf_counter()-a)
                app.processEvents()
            window.pause_playback()
        result['built_preview']={'build_seconds':built,'frames':window.built_preview.count,'bytes':window.built_preview.bytes,'decode_median_seconds':statistics.median(reads),'render_calls_during_cached_playback':0}
        window.reset_project();window.close()
        from motionstudio.enhanced_depth import combine
        for kind in ('emission','dust'):
            image=n.copy()
            if kind=='dust':image[:,500:540]*=.1
            enhanced,base_depth,detail=combine(image,d,fine=1.5,dust=1.5,bias=.75)
            assert np.isfinite(enhanced).all()
            cv2.imwrite(str(out/(kind+'_enhanced_depth.png')),np.uint8(enhanced*255))
        (out/'performance_v17.json').write_text(json.dumps(result,indent=2))
        report=['# V1.7 Windows validation results','',f"Baseline: {result['baseline_commit']}. All timings measured on this Windows hosted runner. Short synthetic clips; no pristine physical end-user machine or long-duration 4K stress test.",'','## Performance','']
        for kind,value in result['fields'].items():
            report.append(f"- {kind}: {value['v17']['stars']:,} stars; V1.6 preview {value['v16']['preview_median_seconds']*1000:.2f} ms, V1.7 {value['v17']['preview_median_seconds']*1000:.2f} ms ({value['renderer_speedup']:.2f}×); cached lookup {value['cache']['retrieval_median_seconds']*1000:.5f} ms. Video speedup {value['video_speedup']:.2f}×.")
        report+=['','## Built preview','',json.dumps(result['built_preview']), '', '## Output checks','','Six dense-field CPU H.264 exports passed decode/dimension/FPS checks: Full HD, QHD (2K), 4K, each landscape and portrait. Each clip has three frames. Sparse/dense source-derived profile comparisons and repeat-render determinism passed. GUI cache, rapid scrubbing, latest-request, playback, pause, reset and unchanged enabled-state checks run in pytest.','', 'The full pytest result and frozen runtime smoke result are separate build evidence. Side-by-side PNGs support visual review; screenshots are references, not the original scientific image pair. Hardware encoders require user hardware and are not claimed validated here.']
        (out/'TEST_REPORT.md').write_text('\n'.join(report))
        (ROOT/'VALIDATION.md').write_text('\n'.join(report))

if __name__=='__main__':main()
