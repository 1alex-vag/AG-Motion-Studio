"""V1.6 cache, latest-only GUI scheduling, playback and observed-star regressions."""
import os,time,threading
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from motionstudio.gui import Main
from motionstudio.scene3d import Scene,Pose
from motionstudio.preview_cache import PreviewCache
from gui_wait import wait_idle

APP=QApplication.instance() or QApplication([])

def window():
    win=Main();win.starless=np.zeros((48,80,3),np.float32);win.stars=np.zeros((48,80,3),np.uint8)
    win.stars[20:23,30:33]=[220,130,70];win.make_depth();wait_idle(win)
    return win

def pump(predicate,timeout=10):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:APP.processEvents();QTest.qWait(2)
    assert predicate()

def test_byte_lru_eviction_and_readonly():
    cache=PreviewCache(.0001)
    a=np.zeros((4,4,3),np.uint8)
    cache.put('a',(None,a));cache.put('b',(None,a.copy()));assert cache.get('a') is not None
    cache.put('c',(None,a.copy()));assert cache.get('b') is None
    assert cache.bytes<=cache.maximum_bytes and not a.flags.writeable
    cache.resize(0);assert not cache.frames and cache.bytes==0

def test_revisit_cached_frame_and_setting_invalidation():
    win=window()
    try:
        win.timeline.setValue(10);wait_idle(win)
        win.timeline.setValue(30);wait_idle(win)
        with patch.object(Scene,'render',side_effect=AssertionError('duplicate render')):
            win.timeline.setValue(10);wait_idle(win)
            assert 'Cached' in win.preview_status.text()
        count=win.preview_cache.hits
        win.star_intensity.setValue(70);wait_idle(win)
        assert win.preview_cache.hits==count
        assert len(win.preview_cache.frames)==1
    finally:wait_idle(win);win.close()

def test_obsolete_result_latest_only_and_no_sidebar_enable_flicker():
    win=window();entered=threading.Event();release=threading.Event();original=Scene.render;calls=[]
    enabled=[g.isEnabled() for g in win.edit_groups]
    def slow(scene,pose,*args,**kwargs):
        calls.append(pose.time)
        if len(calls)==1:entered.set();assert release.wait(10)
        return original(scene,pose,*args,**kwargs)
    try:
        with patch.object(Scene,'render',slow):
            win.timeline.setValue(1);win._timeline_released();pump(entered.is_set)
            assert win.timeline.isEnabled() and win.btn_reset.isEnabled()
            for frame in range(2,40):win.timeline.setValue(frame)
            win._timeline_released()
            assert [g.isEnabled() for g in win.edit_groups]==enabled
            # Newest request replaces all intermediate positions.
            release.set();wait_idle(win)
            assert len(calls)==2
            assert f'Frame {40} /' in win.preview_status.text()
            assert [g.isEnabled() for g in win.edit_groups]==enabled
    finally:release.set();wait_idle(win);win.close()

def test_reset_during_preview_discards_result_and_stops_playback():
    win=window();entered=threading.Event();release=threading.Event();original=Scene.render
    def slow(scene,*args,**kwargs):entered.set();assert release.wait(10);return original(scene,*args,**kwargs)
    try:
        with patch.object(Scene,'render',slow):
            win.timeline.setValue(3);win._timeline_released();pump(entered.is_set)
            win.toggle_playback();win.reset_project()
            assert not win.playback_timer.isActive() and not win.preview_cache.frames
            release.set();wait_idle(win)
            assert win.views['3D Preview'].rgb is None and win.nd is None
    finally:release.set();wait_idle(win);win.close()

def test_play_pause_fps_and_loop():
    win=window()
    try:
        export_fps=win.fps.currentText();win.playback_fps.setCurrentText('15')
        win.timeline.setValue(0);wait_idle(win);win.toggle_playback()
        pump(lambda:win.timeline.value()>1)
        win.pause_playback();position=win.timeline.value();QTest.qWait(40);APP.processEvents()
        assert win.timeline.value()==position and win.fps.currentText()==export_fps
        win.loop_mode.setCurrentText('Seamless Drift');assert win.loop_preview.isChecked()
        win.toggle_playback();win._playback_origin=time.monotonic()-win.duration.value()-.2;win._playback_tick()
        assert win.playback_timer.isActive() and win.timeline.value()<win.timeline.maximum()/2
        win.pause_playback();wait_idle(win)
    finally:win.pause_playback();wait_idle(win);win.close()

def test_duplicate_inflight_request_renders_once():
    win=window();entered=threading.Event();release=threading.Event();original=Scene.render;calls=[]
    def slow(scene,*args,**kwargs):calls.append(1);entered.set();assert release.wait(10);return original(scene,*args,**kwargs)
    try:
        with patch.object(Scene,'render',slow):
            win.timeline.setValue(2);win._timeline_released();pump(entered.is_set)
            win.motion_preview();win.motion_preview();release.set();wait_idle(win)
            assert len(calls)==1 and 'Cached' in win.preview_status.text()
    finally:release.set();wait_idle(win);win.close()

def test_original_color_stable_geometry_intensity_and_halo_gate():
    n=np.zeros((60,100,3),np.float32);stars=n.copy();stars[30,30]=[.15,.06,.03];stars[30,70]=[.9,.4,.2]
    from motionstudio.star_catalog import DetectionSettings
    low=Scene(n,stars,np.full(n.shape[:2],.5,np.float32),out_w=100,out_h=60,detection=DetectionSettings(min_area=1),star_style={'bloom':0.})
    high=Scene(n,stars,np.full(n.shape[:2],.5,np.float32),out_w=100,out_h=60,catalog=low.catalog,star_style={'bloom':1.})
    a=low.render(Pose());b=high.render(Pose())
    np.testing.assert_array_equal(a[:,20:40],b[:,20:40])
    assert b[:,60:80].sum()>a[:,60:80].sum()
    before=low.catalog.depth.copy();image=low.render(Pose(x=.001));np.testing.assert_array_equal(image,low.render(Pose(x=.001)))
    np.testing.assert_array_equal(before,low.catalog.depth)
    np.testing.assert_allclose(low.render(Pose(),star_intensity=.5),a*.5,atol=1)
    assert a[30,30,0]>a[30,30,1]>a[30,30,2]

def test_style_project_document_and_cache_limits():
    win=window()
    try:
        win.star_style_controls['size_scale'].setValue(85);win.star_style_controls['bloom'].setValue(8);wait_idle(win)
        assert win.project_document()['star_style']['size_scale']==.85
        win.cache_memory.setValue(64);assert win.preview_cache.maximum_bytes==64*1024**2
    finally:wait_idle(win);win.close()


def test_fractional_minification_preserves_observed_rgb_flux():
    from motionstudio.star_catalog import detect_stars,DetectionSettings
    from motionstudio.sprites import prepare_atlas
    stars=np.zeros((30,40,3),np.float32)
    stars[12:15,19:22]=np.array([[.01,.07,.01],[.07,.7,.07],[.01,.07,.01]])[...,None]*np.array([1.,.5,.2])
    catalog=detect_stars(stars,DetectionSettings(min_area=1))
    assert len(catalog)==1
    for scale in (.23,.5,.73):
        atlas,meta=prepare_atlas(catalog,scale,scale,style={'preserve_size':True,'bloom':0.,'sharpness':.7})
        expected=catalog.sprites[0].sum(axis=(0,1))*scale**2
        np.testing.assert_allclose(atlas.sum(axis=0),expected,rtol=2e-5,atol=1e-7)
