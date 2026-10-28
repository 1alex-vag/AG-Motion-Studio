"""Offline packaged-runtime smoke test. No system Python or external FFmpeg needed."""
from pathlib import Path
import argparse,json,os,sys,tempfile,time
import numpy as np
import cv2
from . import __version__
from .runtime import app_data_dir


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true');parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();report={'version':__version__,'frozen':bool(getattr(sys,'frozen',False))}
    try:
        from PyQt6.QtWidgets import QApplication
        from .gui import Main
        from . import engine
        from .scene3d import Scene,default_keyframes,render_video_scene
        from .cinematic import CinematicSettings
        from .depth_edit import DepthPaint,DepthVersions
        from .sprites import COMPILED,draw_atlas
        import imageio_ffmpeg,imageio.v2 as imageio
        from astropy.io import fits
        import tifffile
        app=QApplication.instance() or QApplication([])
        neb=np.full((48,80,3),.05,np.float32);neb[10:38,18:62]=[.3,.06,.2]
        stars=np.zeros((48,80,3),np.uint8);cv2.circle(stars,(25,25),2,(220,160,100),-1)
        window=Main();window.show();app.processEvents();window.starless=neb;window.stars=stars
        window.make_depth();deadline=time.monotonic()+90
        while window.worker is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
        if window.worker is not None:raise RuntimeError('Packaged depth generation timed out')
        assert window.nd is not None and len(window.catalog)==1
        versions=DepthVersions(window.nd);paint=DepthPaint(versions);paint.begin();paint.stroke(30,22,size=20);paint.end()
        changed=paint.depth.copy();paint.undo();np.testing.assert_array_equal(paint.depth,versions.generated);paint.redo();np.testing.assert_array_equal(paint.depth,changed)
        config=CinematicSettings(enabled=True,volumetric=True,loop='Seamless Drift')
        scene=Scene(neb,stars,paint.depth,out_w=80,out_h=48,cinematic=config)
        frames=default_keyframes(duration=1)
        first=scene.render(scene.pose_at(frames,0,1));last=scene.render(scene.pose_at(frames,1,1))
        np.testing.assert_array_equal(first,last)
        assert COMPILED and len(draw_atlas.signatures)>0,'Compiled Numba renderer unavailable'
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'smoke.mp4'
            info=render_video_scene(scene,frames,path,1,2,workers=1,encoder='cpu')
            reader=imageio.get_reader(path);assert reader.get_data(0).shape==(48,80,3);reader.close()
            fits.writeto(root/'sample.fits',np.ones((12,20),np.float32),overwrite=True)
            assert engine.load_image(root/'sample.fits').shape==(12,20,3)
            tifffile.imwrite(root/'sample.tif',np.ones((12,20,3),np.uint16)*1000)
            assert engine.load_image(root/'sample.tif').dtype==np.float32
        from .cloud import CloudSettings,CloudScene,build_cloud,raster_cloud,raster_stars
        options=CloudSettings(density=.1,star_style='Sphere + Spikes',spikes=4)
        geometry=build_cloud(neb,window.nd,options)
        cloud=CloudScene(neb,stars,window.nd,out_w=80,out_h=48,cloud_geometry=geometry,cloud_settings=options,catalog=window.catalog)
        assert cloud.render(default_keyframes()[0]).max()>0
        assert len(raster_cloud.signatures)>0 and len(raster_stars.signatures)>0
        with tempfile.TemporaryDirectory() as tmp:
            cloud_video=render_video_scene(cloud,frames,Path(tmp)/'cloud.mp4',.1,30,workers=1,encoder='cpu')
        only=CloudSettings(content='Nebula Only',density=.1)
        nebula=CloudScene(neb,None,window.nd,out_w=80,out_h=48,cloud_geometry=geometry,cloud_settings=only)
        assert nebula.render(default_keyframes()[0]).max()>0 and len(nebula.catalog)==0
        report.update(experimental_cloud=True,cloud_particles=len(geometry),cloud_video=cloud_video,nebula_only_without_mask=True)
        executable=Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
        if report['frozen']:
            executable.relative_to(Path(sys._MEIPASS).resolve())
            assert Path(os.environ['NUMBA_CACHE_DIR']).is_relative_to(app_data_dir())
        window.timeline.setValue(2);window._timeline_released()
        def idle():
            deadline=time.monotonic()+30
            while (window._preview_worker is not None or window._preview_latest is not None or window.preview_debounce.isActive()) and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
            assert window._preview_worker is None
        idle();window.timeline.setValue(3);window._timeline_released();idle()
        hits=window.preview_cache.hits;window.timeline.setValue(2);idle()
        assert window.preview_cache.hits>hits and 'Cached' in window.preview_status.text()
        window.toggle_playback();assert window.playback_timer.isActive();window.pause_playback();idle()
        window.close();app.processEvents()
        report.update(ok=True,qt=True,compiled_renderer=True,ffmpeg=str(executable),video=info,
                      depth_editor=True,volumetric_loop=True,fits=True,tiff=True,preview_cache=True,play_pause=True)
    except BaseException as exc:
        import traceback
        report.update(ok=False,error=str(exc),traceback=traceback.format_exc())
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2),encoding='utf-8')
    if not report.get('ok'):raise SystemExit(1)

if __name__=='__main__':main()
