from gui_wait import wait_idle
"""Behavioral V1.4 regression: depth geometry, continuity, frame sampling and import lifecycle."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import replace, asdict
from pathlib import Path
import tempfile
from unittest.mock import patch
import numpy as np
import cv2
from PIL import Image
import imageio.v2 as imageio
from PyQt6.QtWidgets import QApplication,QFileDialog
from motionstudio.cinematic import CinematicSettings as Config, prepared_depth, soft_bands, evaluate_camera
from motionstudio.scene3d import Scene,Pose,default_keyframes,camera_at,rotation,render_video_scene
from motionstudio.gui import Main

APP=QApplication.instance() or QApplication([])


def pair(w=200,h=120):
    yy,xx=np.mgrid[:h,:w]
    nd=(.5+.45*np.sin(xx/20)*np.cos(yy/17)).astype(np.float32)
    neb=np.stack([nd*.45+.02,nd*.12+.01,nd*.32+.02],axis=2).astype(np.float32)
    stars=np.zeros((h,w,3),np.uint8)
    for x,y,r in [(45,35,3),(90,60,2),(160,80,4)]:
        cv2.circle(stars,(min(x,w-5),min(y,h-5)),r,(220,180,150),-1)
    return neb,stars,nd


def scene(config=Config(enabled=True),**kw):
    return Scene(*pair(),out_w=200,out_h=120,cinematic=config,**kw)


def test_strength_changes_z_not_camera_or_count_and_zero_is_flat():
    a=scene(Config(enabled=True,strength=0,atmosphere=0,centered=False))
    b=scene(Config(enabled=True,strength=1,atmosphere=0,centered=False))
    c=scene(Config(enabled=True,strength=2,atmosphere=0,centered=False))
    np.testing.assert_allclose(a.surface_z,3)
    np.testing.assert_allclose(c.surface_z-3,2*(b.surface_z-3),atol=1e-6)
    np.testing.assert_allclose(a.project_stars(Pose())[3],3)
    assert np.ptp(c.project_stars(Pose())[3])>np.ptp(b.project_stars(Pose())[3])
    assert len(a.catalog)==len(b.catalog)==len(c.catalog)
    paths=default_keyframes()
    for t in [0,3,8]:assert a.pose_at(paths,t,8)==b.pose_at(paths,t,8)==c.pose_at(paths,t,8)
    pos=a.project_stars(Pose(x=.2),motion_over_nebula=1)[0]
    shift=pos[:,0]-a.x
    np.testing.assert_allclose(shift,shift[0],atol=1e-5)


def test_soft_split_neutral_reconstruction_and_differential_motion():
    config=Config(enabled=True,atmosphere=0,smoothing=0)
    sc=scene(config);bands=soft_bands(sc.nd)
    np.testing.assert_allclose(bands.sum(axis=0),1,atol=1e-6)
    assert np.all(bands>0)
    np.testing.assert_allclose(sc.render_nebula(Pose()),sc.neb,atol=1e-6)
    # Different depth bands undergo different perspective translations.
    focal=sc.f0
    dx=[abs(focal*.2/z) for z in sc.band_z]
    assert dx[-1]>dx[0]*1.2
    moved=sc.render_nebula(Pose(x=.2,y=.01))
    assert np.isfinite(moved).all() and moved.max()<=1
    assert np.abs(moved-sc.neb).mean()>.005


def test_star_motion_changes_continuous_depth_without_catalog_mutation():
    a=scene(Config(enabled=True,star_motion=.5))
    b=scene(Config(enabled=True,star_motion=1.5))
    assert np.ptp(b.project_stars(Pose())[3])>np.ptp(a.project_stars(Pose())[3])
    np.testing.assert_array_equal(a.catalog.depth,b.catalog.depth)
    np.testing.assert_array_equal(a.catalog.x,b.catalog.x)


def test_spline_velocity_is_continuous_at_internal_keyframes():
    frames=[Pose(),Pose(time=2,x=.2,yaw=2),Pose(time=5,x=.25,yaw=3),Pose(time=8,x=.5)]
    eps=1e-4
    for field in ['x','yaw']:
        middle=getattr(camera_at(frames,2,'Cinematic'),field)
        left=(middle-getattr(camera_at(frames,2-eps,'Cinematic'),field))/eps
        right=(getattr(camera_at(frames,2+eps,'Cinematic'),field)-middle)/eps
        assert abs(left-right)<.001
    assert abs(camera_at(frames,1,'Linear').x-.1)<1e-10


def test_loops_exact_transforms_pixels_and_wrap_velocity():
    frames=[Pose(),Pose(time=4,x=.1,y=.04,z=.12,yaw=-1),Pose(time=8,x=.25,y=.08,z=.2,yaw=-2)]
    for loop in ['Ping-Pong','Seamless Orbit','Seamless Drift']:
        config=Config(enabled=True,loop=loop)
        sc=scene(config)
        a=sc.pose_at(frames,0,8);b=sc.pose_at(frames,8,8)
        for k in ['x','y','z','yaw','pitch','roll','fov']:assert getattr(a,k)==getattr(b,k)
        np.testing.assert_array_equal(sc.render(a),sc.render(b))
        eps=.0001
        prev=sc.pose_at(frames,8-eps,8);nxt=sc.pose_at(frames,eps,8)
        for k in ['x','y','z','yaw','pitch']:
            left=(getattr(a,k)-getattr(prev,k))/eps;right=(getattr(nxt,k)-getattr(a,k))/eps
            assert abs(left-right)<.001


def test_subject_centered_shared_projection_and_static_camera_slider():
    paths=default_keyframes('Fly-through')
    config=Config(enabled=True,loop='Seamless Orbit')
    for t in np.linspace(0,8,12):
        pose=evaluate_camera(paths,t,8,config)
        q=rotation(pose)@np.array([-pose.x,-pose.y,3-pose.z])
        np.testing.assert_allclose(q[:2],0,atol=1e-7)
    sc=scene(config)
    for t in np.linspace(0,8,12):
        pose=sc.pose_at(paths,t,8)
        q=rotation(pose)@np.array([-pose.x,-pose.y,sc.anchor_z-pose.z])
        np.testing.assert_allclose(q[:2],0,atol=1e-7)
    config=replace(config,camera_motion=0)
    for t in [0,2,5,8]:
        pose=evaluate_camera(paths,t,8,config)
        assert pose.x==pose.y==pose.z==pose.yaw==pose.pitch==0


def test_contrast_smoothing_edge_preservation_and_atmosphere_detail():
    depth=np.zeros((60,80),np.float32);depth[:,40:]=1
    depth[10:15,10:15]=.2
    a=prepared_depth(depth,Config(enabled=True,smoothing=1))
    assert a[30,39]<.05 and a[30,40]>.95
    b=prepared_depth(np.array([[.3,.7]],np.float32),Config(enabled=True,smoothing=0,contrast=2))
    np.testing.assert_allclose(b,[[.1,.9]],atol=1e-6)
    clear=scene(Config(enabled=True,atmosphere=0)).render_nebula(Pose())
    haze=scene(Config(enabled=True,atmosphere=1)).render_nebula(Pose())
    assert 0<np.abs(haze-clear).mean()<.035
    assert np.std(haze)>.8*np.std(clear)


def test_foreground_limit_and_depth_aware_blur_determinism():
    a=scene(Config(enabled=True,strength=2,star_motion=2,foreground_limit=0))
    b=scene(Config(enabled=True,strength=2,star_motion=2,foreground_limit=1))
    assert np.min(b.project_stars(Pose())[3])>=np.min(a.project_stars(Pose())[3])
    pose=Pose(x=.1);old=Pose(x=.08)
    first=b.render(pose,previous_pose=old,motion_over_nebula=1)
    np.testing.assert_array_equal(first,b.render(pose,previous_pose=old,motion_over_nebula=1))
    assert np.abs(first.astype(float)-b.render(pose,motion_over_nebula=1)).sum()>0


def test_real_loop_encode_parallel_and_no_duplicate_endpoint():
    config=Config(enabled=True,loop='Seamless Drift')
    sc=scene(config);frames=default_keyframes(duration=1)
    observed=[];original=sc.render
    def capture(pose,**kw):observed.append(pose.time);return original(pose,**kw)
    with tempfile.TemporaryDirectory() as tmp:
        a=Path(tmp)/'a.mp4';b=Path(tmp)/'b.mp4'
        with patch.object(sc,'render',side_effect=capture):render_video_scene(sc,frames,a,1,8,encoder='cpu',workers=1)
        np.testing.assert_allclose(observed,np.arange(8)/8)
        render_video_scene(sc,frames,b,1,8,encoder='cpu',workers=2)
        r1=imageio.get_reader(a);r2=imageio.get_reader(b)
        for i in range(8):np.testing.assert_array_equal(r1.get_data(i),r2.get_data(i))
        first=r1.get_data(0);last=r1.get_data(7)
        assert np.abs(first.astype(float)-last).mean()>0
        r1.close();r2.close()


def load(win,path,neb):
    with patch.object(QFileDialog,'getOpenFileName',return_value=(str(path),'')),patch('motionstudio.gui.QMessageBox.warning') as warning:
        win.load_file(neb);warning.assert_not_called()


def test_import_reset_and_both_incompatible_directions_leave_sources_intact():
    win=Main()
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);paths=[]
        for name,shape in [('n',(120,200)),('s',(120,200)),('big',(160,240))]:
            path=root/(name+'.png');Image.fromarray(np.full((*shape,3),65,np.uint8)).save(path);paths.append(path)
        original=[p.read_bytes() for p in paths]
        n,s,big=paths
        load(win,n,True);assert not win.btn_depth.isEnabled()
        load(win,s,False);assert win.btn_depth.isEnabled()
        win.make_depth();wait_idle(win);assert win.nd is not None
        load(win,big,True)
        assert win.stars is None and win.star_path is None and win.starless.shape[:2]==(160,240)
        assert win.nd is win.sd is win.catalog is win.protection is win.scene_cache is None
        assert win.views['Star mask'].rgb is win.views['3D Preview'].rgb is None
        assert not win.btn_depth.isEnabled() and 'different resolution' in win.status.text()
        load(win,s,False)
        assert win.starless is None and win.stars.shape[:2]==(120,200)
        load(win,n,True);win.make_depth();wait_idle(win)
        win.keyframes=[Pose(x=1),Pose(time=8,x=2)];win.cam['x'].setValue(1);wait_idle(win)
        win.reset_project()
        assert win.starless is win.stars is win.nd is win.sd is win.catalog is win.protection is win.scene_cache is None
        assert win.starless_path is win.star_path is None
        assert win.keyframes==default_keyframes(duration=8)
        assert win.cam['x'].value()==0 and win.timeline.value()==0
        assert win.status.text()=='No project loaded' and win.progress.value()==0
        assert all(view.rgb is None for view in win.views.values())
        assert [p.read_bytes() for p in paths]==original
    win.close()


def test_invalid_input_keeps_existing_pair_and_busy_reset_is_guarded():
    win=Main();n,st,nd=pair();win.starless=n;win.stars=st;win.nd=nd
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'bad.png';path.write_bytes(b'not image')
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(path),'')),patch('motionstudio.gui.QMessageBox.warning'):
            win.load_file(True)
        assert win.starless is n and win.stars is st and win.nd is nd
    class Busy:
        def isRunning(self):return True
    win.worker=Busy();win.reset_project();assert win.starless is n
    win.worker=None;win.close()


def test_cinematic_project_roundtrip_and_legacy_opt_out():
    win=Main();win.cinematic_mode.setChecked(True);win.cine_preset.setCurrentText('Deep 3D')
    assert win.cine_sliders['strength'].value()==150
    assert win.advanced_boxes[0].isHidden() and win.cine_advanced.isHidden()
    win.advanced_settings.setChecked(True);assert not win.advanced_boxes[0].isHidden()
    win.loop_mode.setCurrentText('Seamless Drift');win.duration.setValue(15)
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);n,st,nd=pair()
        for name,image in [('n',n),('s',st)]:Image.fromarray(np.uint8(image*255) if image.dtype!=np.uint8 else image).save(root/(name+'.png'))
        load(win,root/'n.png',True);load(win,root/'s.png',False);win.make_depth();wait_idle(win)
        path=root/'project.json';win.write_project(path)
        fresh=Main()
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(path),'')):
            fresh.load_scene_project();wait_idle(fresh)
        assert fresh.cinematic_settings()==win.cinematic_settings()
        assert fresh.duration.value()==15 and fresh.loop_duration.currentText()=='15'
        a=win._get_scene(200,120);b=fresh._get_scene(200,120)
        np.testing.assert_array_equal(a.render(a.pose_at(win.render_keyframes(),4,15)),b.render(b.pose_at(fresh.render_keyframes(),4,15)))
        import json
        doc=json.loads(path.read_text());doc.pop('cinematic');path.write_text(json.dumps(doc))
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(path),'')):fresh.load_scene_project();wait_idle(fresh)
        assert not fresh.cinematic_mode.isChecked()
        fresh.close()
    win.close()


def test_flat_depth_does_not_invent_nebula_separation():
    neb,stars,nd=pair();nd[:]=.5
    sc=Scene(neb,stars,nd,out_w=200,out_h=120,cinematic=Config(enabled=True,atmosphere=0))
    np.testing.assert_allclose(sc.band_z,3,atol=1e-6)
    layered=sc.render_nebula(Pose(x=.2))
    single=Scene(neb,stars,nd,out_w=200,out_h=120,cinematic=Config(enabled=True,atmosphere=0,layer_split=False))
    np.testing.assert_allclose(layered,single.render_nebula(Pose(x=.2)),atol=1e-6)


def test_real_preview_loop_worker_playback_and_reset_lifecycle():
    import time
    win=Main();neb,stars,nd=pair()
    win.starless=neb;win.stars=stars;win.make_depth();wait_idle(win)
    win.cinematic_mode.setChecked(True);win.loop_mode.setCurrentText('Seamless Drift');win.duration.setValue(1);wait_idle(win)
    win.preview_loop()
    assert win.worker is not None and not win.btn_reset.isEnabled()
    deadline=time.monotonic()+15
    while win.worker is not None and time.monotonic()<deadline:
        APP.processEvents();time.sleep(.001)
    assert win.worker is None and win.loop_timer.isActive()
    assert len(win.loop_frames)==24
    win.loop_index=23;win._play_loop_frame();assert win.loop_index==0
    assert win.btn_reset.isEnabled()
    win.reset_project()
    assert not win.loop_timer.isActive() and not win.loop_frames
    assert win.views['3D Preview'].rgb is None
    win.close()
