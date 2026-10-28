import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json,threading,time,shutil
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import numpy as np
import cv2
import pytest
from PIL import Image
from PyQt6.QtCore import QTimer,Qt,QPoint
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication,QFileDialog,QLabel,QAbstractButton,QDialog,QDialogButtonBox
from motionstudio import engine
from motionstudio.depth_edit import DepthVersions,DepthPaint
from motionstudio.depth_editor import DepthEditor
from motionstudio.cinematic import CinematicSettings,PRESETS
from motionstudio.scene3d import Scene,Pose,rotation,default_keyframes,render_video_scene
from motionstudio.gui import Main
from motionstudio.export_settings import RESOLUTIONS,validate_resolution
from motionstudio.projects import resolve_reference,portable_reference
from gui_wait import wait_idle

APP=QApplication.instance() or QApplication([])

def pair():
    yy,xx=np.mgrid[:100,:180]
    d=(.5+.4*np.sin(xx/24)*np.cos(yy/19)).astype(np.float32)
    n=np.stack([d*.5,d*.12,d*.3],axis=2)
    s=np.zeros((100,180,3),np.uint8);cv2.circle(s,(45,45),3,(220,140,80),-1)
    return n,s,d


def ready():
    win=Main();win.starless,win.stars,_=pair();win.make_depth();wait_idle(win);return win


def test_offline_refinement_is_deterministic_bounded_and_keeps_input():
    neb,_,nd=pair();before=nd.copy();stages=[]
    a=engine.refine_nebula_depth(neb,nd,.8,progress=stages.append)
    b=engine.refine_nebula_depth(neb,nd,.8)
    np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(nd,before)
    assert np.isfinite(a).all() and a.min()>=0 and a.max()<=1
    assert np.abs(a-nd).mean()>.001 and stages==[10,45,85]
    np.testing.assert_array_equal(engine.refine_nebula_depth(neb,nd,0),nd)


def test_depth_versions_and_refinement_preserve_manual_delta():
    generated=np.full((40,60),.4,np.float32)
    versions=DepthVersions(generated,np.full_like(generated,.5),np.full_like(generated,.6))
    updated=versions.refined_copy(np.full_like(generated,.55))
    np.testing.assert_allclose(updated.current,.65,atol=1e-6)
    assert not versions.generated.flags.writeable and not versions.refined.flags.writeable
    np.testing.assert_array_equal(versions.generated,generated)
    with pytest.raises(ValueError):DepthVersions(np.array([[np.nan]],np.float32))
    with pytest.raises(ValueError):DepthVersions(generated,np.zeros((2,2),np.float32))


def test_raise_lower_restore_softness_and_continuous_stroke():
    generated=np.full((100,180),.5,np.float32);model=DepthPaint(DepthVersions(generated))
    model.begin();model.stroke(25,50,'Raise',20,1,1);model.stroke(140,50,'Raise',20,1,1);model.end()
    assert len(model.undo_stack)==1 and np.all(model.depth[50,25:141]>.5)
    assert model.depth[50,140]>model.depth[50,149] and model.depth[10,10]==.5
    raised=model.depth.copy();model.undo();np.testing.assert_array_equal(model.depth,generated)
    model.redo();np.testing.assert_array_equal(model.depth,raised)
    model.begin();model.stroke(140,50,'Lower',20,1,0);model.end();assert model.depth[50,140]<raised[50,140]
    model.begin();model.stroke(70,50,'Restore',20,1,0);model.end();assert model.depth[50,70]==.5
    np.testing.assert_array_equal(generated,np.full_like(generated,.5))


def test_smooth_flatten_undo_redo_reset_and_redo_branch():
    generated=np.zeros((60,90),np.float32);generated[:,45:]=1
    model=DepthPaint(DepthVersions(generated))
    model.begin();model.stroke(45,30,'Smooth',40,1,.5);model.end()
    assert 0<model.depth[30,44]<1
    smooth=model.depth.copy();model.begin();model.stroke(45,30,'Flatten',25,.6,.3);model.end()
    assert np.abs(model.depth-smooth).sum()>0
    model.reset();np.testing.assert_array_equal(model.depth,generated)
    model.undo();assert np.abs(model.depth-generated).sum()>0
    model.redo();np.testing.assert_array_equal(model.depth,generated)
    model.undo();model.begin();model.stroke(15,15,'Raise',10,.5,.5);model.end();assert not model.redo_stack


def test_undo_history_uses_local_patches_and_is_bounded():
    model=DepthPaint(DepthVersions(np.full((600,800),.5,np.float32)),history_bytes=20000)
    for x in range(30,200,20):model.begin();model.stroke(x,80,size=30);model.end()
    assert sum(p.bytes for p in model.undo_stack)<=20000
    assert all(p.before.shape[0]<=32 and p.before.shape[1]<=32 for p in model.undo_stack)
    while model.undo_stack:model.undo()
    while model.redo_stack:model.redo()
    assert np.isfinite(model.depth).all()


def test_canvas_painting_coordinates_cursor_compare_and_editor_controls():
    editor=DepthEditor(DepthVersions(np.full((100,180),.5,np.float32)));editor.show();APP.processEvents()
    editor.size.setValue(20);editor.strength.setValue(100)
    rect=editor.canvas.image_rect();point=QPoint(round(rect.center().x()),round(rect.center().y()))
    QTest.mouseMove(editor.canvas,point);assert editor.canvas.pointer is not None
    QTest.mousePress(editor.canvas,Qt.MouseButton.LeftButton,pos=point);QTest.mouseRelease(editor.canvas,Qt.MouseButton.LeftButton,pos=point)
    assert editor.model.depth[50,90]>.5 and editor.undo_button.isEnabled()
    editor.undo();np.testing.assert_array_equal(editor.model.depth,editor.model.generated)
    editor.redo();before=editor.model.depth.copy()
    editor.compare.setChecked(True)
    QTest.mouseClick(editor.canvas,Qt.MouseButton.LeftButton,pos=point);np.testing.assert_array_equal(editor.model.depth,before)
    editor.compare.setChecked(False);editor.reset_depth()
    deadline=time.monotonic()+5
    while editor.worker is not None and time.monotonic()<deadline:APP.processEvents();QTest.qWait(1)
    assert editor.worker is None
    np.testing.assert_array_equal(editor.model.depth,editor.model.generated)
    editor.undo();np.testing.assert_array_equal(editor.model.depth,before)
    editor.reject();assert editor.result()==QDialog.DialogCode.Rejected


def test_depth_jobs_are_async_show_progress_prevent_duplicates_and_keep_qt_alive():
    win=Main();win.starless,win.stars,_=pair();gate=threading.Event();original=engine.nebula_depth
    count=[];ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(5)
    def delayed(value):count.append(1);gate.wait(10);return original(value)
    try:
        with patch('motionstudio.gui.e.nebula_depth',side_effect=delayed):
            started=time.monotonic();win.make_depth();assert time.monotonic()-started<.2
            worker=win.worker;assert worker is not None and not win.btn_depth.isEnabled()
            progress=[];status=[];worker.progress.connect(progress.append);worker.status.connect(status.append)
            win.make_depth();assert win.worker is worker
            deadline=time.monotonic()+1
            while len(ticks)<2 and time.monotonic()<deadline:APP.processEvents();QTest.qWait(5)
            assert len(ticks)>=2 and win.progress.maximum()==0
            gate.set();wait_idle(win)
            assert count==[1] and win.nd is not None and win.progress.value()==100
            assert 35 in progress and 95 in progress
            assert any('Detecting stars' in value for value in status)
            assert win.btn_depth.isEnabled() and win.btn_edit_depth.isEnabled()
    finally:
        gate.set();timer.stop();wait_idle(win);win.close()


def test_failed_processing_reenables_controls_and_preserves_previous_project():
    win=ready();old=win.nd
    with patch('motionstudio.gui.e.nebula_depth',side_effect=RuntimeError('test depth failure')),patch('motionstudio.gui.QMessageBox.critical') as errors:
        win.make_depth();wait_idle(win);errors.assert_called_once()
    assert win.nd is old and win.btn_depth.isEnabled() and win.progress.value()==0
    assert 'test depth failure' in win.status.text();win.close()


def test_manual_apply_and_cancel_are_non_destructive():
    win=ready();generated=win.depth_versions.generated.copy();old=win.nd.copy()
    class Editor:
        def __init__(self,versions,parent):self.model=type('Model',(),{'depth':np.clip(versions.current+.1,0,1)})()
        def exec(self):return QDialog.DialogCode.Accepted
    with patch('motionstudio.gui.DepthEditor',Editor):win.edit_depth_map();wait_idle(win)
    assert win.depth_versions.manual is not None and np.abs(win.nd-old).mean()>.01
    np.testing.assert_array_equal(win.depth_versions.generated,generated)
    class Cancel(Editor):
        def exec(self):return QDialog.DialogCode.Rejected
    before=win.nd.copy()
    with patch('motionstudio.gui.DepthEditor',Cancel):win.edit_depth_map()
    np.testing.assert_array_equal(win.nd,before);win.close()


def test_refinement_and_manual_versions_portable_project_roundtrip(tmp_path):
    win=ready();neb,stars,_=pair()
    for name,img in [('neb',neb),('stars',stars)]:Image.fromarray(np.uint8(img*255) if img.dtype!=np.uint8 else img).save(tmp_path/(name+'.png'))
    win.starless_path=str(tmp_path/'neb.png');win.star_path=str(tmp_path/'stars.png')
    generated=win.depth_versions.generated.copy();win.refine();wait_idle(win)
    assert win.depth_versions.refined is not None
    versions=win.depth_versions;win.depth_versions=DepthVersions(versions.generated,versions.refined,np.clip(versions.current+.025,0,1));win.nd=win.depth_versions.current
    win.cinematic_mode.setChecked(True);win.volumetric.setChecked(True);win.subject_anchor=(.3,.7)
    win.orientation.setCurrentText('Portrait');win.preset.setCurrentText('1440×2560');win.video_quality.setValue(22);wait_idle(win)
    path=tmp_path/'project.json';win.write_project(path)
    doc=json.loads(path.read_text());assert doc['schema']==6 and doc['starless']=='neb.png' and doc['star_mask']=='stars.png'
    assert '\\' not in doc['starless']
    moved=tmp_path/'moved';moved.mkdir()
    for name in ['neb.png','stars.png','project.json','project.depth.npz']:shutil.copy2(tmp_path/name,moved/name)
    fresh=Main()
    with patch.object(QFileDialog,'getOpenFileName',return_value=(str(moved/'project.json'),'')):
        fresh.load_scene_project();wait_idle(fresh)
    for key in ('generated','refined','manual'):np.testing.assert_array_equal(getattr(fresh.depth_versions,key),getattr(win.depth_versions,key))
    assert fresh.subject_anchor==(.3,.7) and fresh.volumetric.isChecked()
    assert (fresh._settings().width,fresh._settings().height)==(1440,2560) and fresh.video_quality.value()==22
    np.testing.assert_array_equal(fresh.depth_versions.generated,generated)
    fresh.close();win.close()


def test_all_orientation_presets_fps_and_custom_validation():
    win=Main()
    for orientation,sizes in RESOLUTIONS.items():
        win.orientation.setCurrentText(orientation)
        assert [win.preset.itemText(i) for i in range(4)]==[f'{w}×{h}' for w,h in sizes]
        for w,h in sizes:
            win.preset.setCurrentText(f'{w}×{h}')
            for fps in [24,30,60]:
                win.fps.setCurrentText(str(fps));settings=win._settings()
                assert (settings.width,settings.height,settings.fps)==(w,h,fps)
    win.preset.setCurrentText('Custom');win.custom_width.setValue(1536);win.custom_height.setValue(2048)
    assert win._settings().width==1536
    win.custom_width.setValue(1537)
    with pytest.raises(ValueError):win._settings()
    assert win.export_advanced.isHidden();win.close()


def test_volumetric_off_identity_and_on_subtlety_depth_and_loops():
    neb,stars,nd=pair();base=CinematicSettings(enabled=True,volumetric=False)
    a=Scene(neb,stars,nd,out_w=180,out_h=100,cinematic=base)
    off=Scene(neb,stars,nd,out_w=180,out_h=100,cinematic=replace(base,volumetric=True,volumetric_strength=0))
    np.testing.assert_array_equal(a.render(Pose()),off.render(Pose()))
    config=replace(base,volumetric=True,volumetric_strength=.5,loop='Seamless Drift')
    on=Scene(neb,stars,nd,out_w=180,out_h=100,cinematic=config)
    assert len(on.catalog)==len(a.catalog) and np.ptp(on.band_z)>np.ptp(a.band_z)
    clear=a.render(Pose()).astype(float);enhanced=on.render(Pose()).astype(float)
    assert 0<np.abs(clear-enhanced).mean()<6
    frames=default_keyframes()
    np.testing.assert_array_equal(on.render(on.pose_at(frames,0,8)),on.render(on.pose_at(frames,8,8)))


def test_selected_anchor_shared_camera_projection_and_click_selection():
    neb,stars,nd=pair();config=CinematicSettings(enabled=True,anchor_x=.3,anchor_y=.7)
    scene=Scene(neb,stars,nd,out_w=180,out_h=100,cinematic=config)
    for time_value in [0,2,5,8]:
        pose=scene.pose_at(default_keyframes(),time_value,8)
        target=np.asarray(scene.anchor_world)-[pose.x,pose.y,pose.z]
        np.testing.assert_allclose((rotation(pose)@target)[:2],0,atol=1e-7)
    win=ready();win.cinematic_mode.setChecked(True);wait_idle(win)
    win.anchor_button.setChecked(True);win.views['Starless'].clicked.emit(.3,.7);wait_idle(win)
    assert win.subject_anchor==(.3,.7) and not win.anchor_button.isChecked()
    win.reset_anchor();wait_idle(win);assert win.subject_anchor==(.5,.5);win.close()


def test_cinematic_presets_set_volumetric_strength_without_enabling_effect():
    win=Main();win.cinematic_mode.setChecked(True)
    for preset,expected in [('Gentle',10),('Cinematic',25),('Deep 3D',40),('Fly-through',50)]:
        win.cine_preset.setCurrentText(preset)
        assert win.cine_sliders['volumetric_strength'].value()==expected and not win.volumetric.isChecked()
    win.close()


def test_no_misleading_model_wording_in_ui_and_version_about():
    win=Main();texts=[]
    for widget in win.findChildren(QLabel)+win.findChildren(QAbstractButton):texts.append(widget.text())
    joined=' '.join(texts).lower()
    assert 'ai not installed' not in joined and 'with ai' not in joined and 'model download' not in joined
    assert win.btn_refine.text()=='Refine Nebula Depth' and 'V1.9' in win.windowTitle()
    with patch('motionstudio.gui.QMessageBox.about') as about:
        win.about_dialog();assert '1.9.0' in about.call_args.args[2]
    win.close()


def test_path_recovery_from_legacy_windows_and_slash_normalization(tmp_path):
    (tmp_path/'neb.png').write_bytes(b'x')
    assert resolve_reference('C:\\Old\\Folder\\neb.png',tmp_path)==tmp_path/'neb.png'
    folder=tmp_path/'sources';folder.mkdir();(folder/'stars.png').write_bytes(b'x')
    assert resolve_reference('sources\\stars.png',tmp_path)==folder/'stars.png'
    assert portable_reference(folder/'stars.png',tmp_path)=='sources/stars.png'


def test_video_quality_and_frame_status_propagation(tmp_path):
    neb,stars,nd=pair();scene=Scene(neb,stars,nd,out_w=180,out_h=100)
    status=[];progress=[]
    info=render_video_scene(scene,default_keyframes(duration=1),tmp_path/'quality.mp4',1,3,
        quality=23,encoder='cpu',workers=1,status=status.append,progress=lambda i,n:progress.append((i,n)))
    assert info['quality']==23 and progress[-1]==(3,3)
    assert any('Rendering frame 3 / 3' in item and 'Encoder: libx264' in item for item in status)


def test_odd_custom_dimensions_do_not_break_depth_generation_or_preview_actions():
    win=Main();win.starless,win.stars,_=pair()
    win.preset.setCurrentText('Custom');win.custom_width.setValue(1537)
    win.make_depth();wait_idle(win)
    assert win.nd is not None and win.btn_depth.isEnabled()
    win.motion_preview();assert win.worker is None and 'even numbers' in win.status.text()
    win.cinematic_mode.setChecked(True);win.loop_mode.setCurrentText('Seamless Drift');wait_idle(win)
    win.preview_loop();assert win.worker is None and 'even numbers' in win.status.text()
    win.debug_stars();assert win.worker is None and 'even numbers' in win.status.text()
    win.close()
