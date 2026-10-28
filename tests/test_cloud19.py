"""Isolated experimental engine plus real GUI/project/export integration."""
import os,dataclasses
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
import numpy as np
import cv2
import pytest
from PyQt6.QtWidgets import QApplication,QFileDialog
from motionstudio.cloud import CloudSettings,CloudScene,build_cloud
from motionstudio.scene3d import Scene,Pose,default_keyframes,render_video_scene
from motionstudio.cinematic import CinematicSettings
from motionstudio.gui import Main
from motionstudio.star_catalog import detect_stars
from gui_wait import wait_idle
APP=QApplication.instance() or QApplication([])

def fixture(kind='emission'):
    y,x=np.mgrid[:96,:144].astype(np.float32);a=np.exp(-((x-72)**2/1000+(y-48)**2/380))
    b=np.exp(-((x-38)**2+(y-42)**2)/90)
    n=np.stack((a*.65+b*.15,a*.18+b*.45,a*.35+b*.7),axis=2).astype(np.float32)
    if kind=='dust':n[:,66:75]*=.025
    if kind=='widefield':n=cv2.GaussianBlur(n,(0,0),8)
    d=np.clip(.5+.25*np.sin(x/17)*a,0,1).astype(np.float32)
    st=np.zeros(n.shape,np.uint8);cv2.circle(st,(40,40),1,(220,130,60),-1);cv2.circle(st,(105,60),3,(255,170,90),-1)
    return n,st,d

def cloud(settings=None,kind='emission'):
    n,st,d=fixture(kind);settings=settings or CloudSettings(density=.1)
    geometry=build_cloud(n,d,settings)
    return CloudScene(n,st,d,out_w=144,out_h=96,catalog=detect_stars(st),cloud_geometry=geometry,cloud_settings=settings),geometry

@pytest.mark.parametrize('kind',['emission','dust','mixed','widefield'])
def test_geometry_real_volume_colors_and_determinism(kind):
    n,st,d=fixture(kind);settings=CloudSettings(density=.1,content='Nebula Only')
    a=build_cloud(n,d,settings);b=build_cloud(n,d,settings)
    assert len(a)>0 and len(a)<=7500
    np.testing.assert_array_equal(a.xyz,b.xyz);np.testing.assert_array_equal(a.rgb,b.rgb)
    assert np.ptp(a.xyz[:,2])>.3 and a.memory_bytes>0
    assert not a.xyz.flags.writeable and np.isfinite(a.xyz).all()
    # Every RGB value is sampled from the input, not globally recolored.
    palette={tuple(row) for row in n.reshape(-1,3)}
    assert all(tuple(row) in palette for row in a.rgb[::50])

def test_thickness_scatter_and_camera_clipping():
    n,st,d=fixture();d[:]=.5
    surface=build_cloud(n,d,CloudSettings(density=.1,thickness=0,depth_source='Current Depth Map'))
    volume=build_cloud(n,d,CloudSettings(density=.1,thickness=1.6,depth_source='Current Depth Map'))
    assert np.ptp(surface.xyz[:,2])==0 and np.ptp(volume.xyz[:,2])>1
    scene,_=cloud();geometry=scene.geometry
    for pose in (Pose(),Pose(x=.1,y=.05),Pose(z=2.),Pose(z=5.),Pose(z=10),Pose(yaw=40,pitch=20,roll=5,fov=70)):
        image=scene.render(pose);assert image.shape==(96,144,3) and image.dtype==np.uint8
        assert scene.geometry is geometry
    assert not scene.render(Pose(z=10)).any()

def test_black_empty_and_invalid_inputs():
    image=np.zeros((40,60,3),np.float32);depth=np.full((40,60),.5,np.float32)
    assert len(build_cloud(image,depth))==0
    with pytest.raises(ValueError):build_cloud(image,depth+np.nan)
    with pytest.raises(ValueError):build_cloud(image,np.ones((3,4)))
    with pytest.raises(ValueError):CloudSettings(density=3)
    with pytest.raises(ValueError):CloudSettings(spikes=5)

def test_nebula_only_without_mask_and_stars_only():
    n,st,d=fixture();s=CloudSettings(content='Nebula Only',density=.1);g=build_cloud(n,d,s)
    scene=CloudScene(n,None,d,out_w=144,out_h=96,cloud_geometry=g,cloud_settings=s)
    np.testing.assert_array_equal(scene.render(Pose(),star_intensity=0),scene.render(Pose(),star_intensity=2))
    assert len(scene.catalog)==0 and scene.render(Pose()).max()>0
    with pytest.raises(ValueError):CloudScene(n,None,d,cloud_geometry=g)
    stars,_=cloud(CloudSettings(content='Stars Only',density=.1))
    assert not stars.render(Pose(),star_intensity=0).any()
    assert stars.render(Pose()).max()>0

@pytest.mark.parametrize('spikes',[0,4,6,8])
def test_star_styles_and_spikes_are_stable(spikes):
    scene,g=cloud(CloudSettings(content='Stars Only',density=.1,star_style='Sphere + Spikes',spikes=spikes))
    a=scene.render(Pose(x=.03));b=scene.render(Pose(x=.03));np.testing.assert_array_equal(a,b)
    assert len(np.unique(scene.catalog.depth))>1
    np.testing.assert_array_equal(scene.star_ids,np.arange(len(scene.catalog)))
    baseline,_=cloud(CloudSettings(content='Stars Only',density=.1,star_style='Sphere'))
    if spikes:assert a.sum()>baseline.render(Pose(x=.03)).sum()

def test_glow_and_sprite_modes_and_dust():
    sphere,_=cloud(CloudSettings(content='Stars Only',density=.1,star_style='Sphere'))
    glow,_=cloud(CloudSettings(content='Stars Only',density=.1,star_style='Sphere + Glow',glow=1.))
    assert glow.render(Pose()).sum()>sphere.render(Pose()).sum()
    sprite,_=cloud(CloudSettings(content='Stars Only',density=.1,star_style='Original Sprite'))
    assert sprite.render(Pose()).sum()>0
    dust,g=cloud(kind='dust');assert g.dust.max()>.1
    assert CloudScene.outside_safe_range(Pose(yaw=40))

def test_loop_and_geometry_not_rebuilt():
    scene,g=cloud();scene.cinematic=CinematicSettings(enabled=True,loop='Seamless Orbit')
    frames=default_keyframes(duration=1)
    with patch('motionstudio.cloud.build_cloud',side_effect=AssertionError('Camera regenerated cloud')):
        a=scene.render(scene.pose_at(frames,0,1));b=scene.render(scene.pose_at(frames,1,1));np.testing.assert_array_equal(a,b)

def test_gui_nebula_only_build_preview_reset_and_classic_default(tmp_path):
    win=Main();assert win.render_engine.currentText()=='Classic 2.5D'
    n,st,d=fixture();win.starless=n;win.starless_path=str(tmp_path/'neb.tif')
    win.render_engine.setCurrentText('Experimental 3D Cloud');win.scene_content.setCurrentText('Nebula Only');win.cloud_values['density'].setValue(10)
    assert win.btn_depth.isEnabled();win.make_depth();wait_idle(win);assert win.stars is None and win.nd is not None
    win.build_3d_cloud();wait_idle(win);assert win.cloud_cache is not None
    geometry=win.cloud_cache[1];win.timeline.setValue(20);win._timeline_released();wait_idle(win)
    assert win.views['3D Preview'].rgb is not None and win.cloud_cache[1] is geometry
    win.cloud_values['thickness'].setValue(80);win.motion_preview();assert 'rebuild' in win.cloud_status.text()
    win.build_3d_cloud();wait_idle(win);assert win.cloud_cache[1] is not geometry
    win.reset_project();assert win.cloud_cache is None;win.close()

def test_project_roundtrip_optional_mask_and_old_defaults(tmp_path):
    import tifffile
    n,st,d=fixture();path=tmp_path/'neb.tif';tifffile.imwrite(path,n)
    win=Main();win.starless=n;win.starless_path=str(path);win.render_engine.setCurrentText('Experimental 3D Cloud');win.scene_content.setCurrentText('Nebula Only')
    win.make_depth();wait_idle(win);win.cloud_values['thickness'].setValue(130);win.write_project(tmp_path/'project.json')
    other=Main()
    with patch.object(QFileDialog,'getOpenFileName',return_value=(str(tmp_path/'project.json'),'JSON')),patch('motionstudio.gui.QMessageBox.critical') as errors:
        other.load_scene_project();wait_idle(other);errors.assert_not_called()
    assert other._nebula_only() and other.stars is None and other.cloud_settings().thickness==1.3 and other.cloud_cache is None
    fresh=Main();assert fresh.render_engine.currentText()=='Classic 2.5D';fresh.close()
    win.close();other.close()

def test_memory_budget_and_video_cpu(tmp_path):
    n,st,d=fixture()
    with patch('motionstudio.cloud.available_ram',return_value=2*1024**2):
        g=build_cloud(n,d,CloudSettings(density=2.),'Final');assert len(g)<=1100
    scene,g=cloud();scene.fast_preview=False
    path=tmp_path/'cloud.mp4';info=render_video_scene(scene,default_keyframes(duration=.1),path,.1,30,encoder='cpu',workers=1)
    import imageio.v2 as imageio
    reader=imageio.get_reader(path);assert reader.get_data(0).shape==(96,144,3);reader.close();assert info['frames']==3


def test_centered_flythrough_keeps_forward_heading():
    scene,_=cloud();scene.cinematic=CinematicSettings(enabled=True,centered=True)
    for z in (0,2.5,3.,3.5,4.):
        pose=scene.center_pose(Pose(z=z));assert abs(pose.yaw)<45 and abs(pose.pitch)<45
