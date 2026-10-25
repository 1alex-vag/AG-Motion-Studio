import unittest,tempfile,dataclasses
from pathlib import Path
from unittest.mock import patch
import numpy as np
import cv2
import imageio.v2 as imageio
from motionstudio.scene3d import Scene,Pose,_sample_map_points,default_keyframes,render_video_scene
from motionstudio.star_catalog import detect_stars,redistribute_depth,DetectionSettings,with_synthetic_background
from motionstudio.protection import nebula_protection
from motionstudio.sprites import draw_atlas,COMPILED
from motionstudio import video


def input_pair():
    h,w=120,200
    neb=np.zeros((h,w,3),np.uint8);stars=np.zeros_like(neb)
    cv2.circle(stars,(50,50),3,(210,100,60),-1)
    # asymmetric observed spike and soft faint halo: never replace with a Gaussian.
    cv2.line(stars,(50,39),(50,61),(80,40,20),1)
    cv2.circle(stars,(145,70),2,(25,45,80),-1)
    return neb,stars,np.full((h,w),.5,np.float32)

class V13Tests(unittest.TestCase):
    def test_original_star_identity_and_relative_brightness(self):
        neb,stars,nd=input_pair();scene=Scene(neb,stars,nd,out_w=200,out_h=120)
        self.assertEqual(len(scene.catalog),2)
        rendered=scene.render(Pose(),bloom=False)
        np.testing.assert_allclose(rendered,stars,atol=1)
        self.assertEqual(rendered[39,50,0],stars[39,50,0])
        self.assertEqual(rendered[50,39,0],0)  # no invented symmetric spike

    def test_no_duplicate_neighbor_halos_or_square_edges(self):
        neb,stars,nd=input_pair()
        cv2.circle(stars,(61,50),2,(80,60,30),-1)
        scene=Scene(neb,stars,nd,out_w=200,out_h=120)
        np.testing.assert_allclose(scene.render(Pose()),stars,atol=1)
        for sprite in scene.catalog.sprites:
            # source black backgrounds remain transparent emitted light
            self.assertTrue(np.all(sprite[0]==0) and np.all(sprite[-1]==0))

    def test_intensity_does_not_change_catalog_geometry_or_size(self):
        neb,stars,nd=input_pair();scene=Scene(neb,stars,nd,out_w=200,out_h=120)
        before=scene.project_stars(Pose(x=.2))[0].copy();catalog=scene.catalog
        zero=scene.render(Pose(),star_intensity=0)
        half=scene.render(Pose(),star_intensity=.5)
        natural=scene.render(Pose(),star_intensity=1)
        strong=scene.render(Pose(),star_intensity=2)
        self.assertEqual(zero.max(),0)
        np.testing.assert_allclose(half.astype(float),natural*.5,atol=1)
        self.assertGreater(strong[70,145,2],natural[70,145,2])
        self.assertIs(scene.catalog,catalog);self.assertEqual(len(catalog),2)
        np.testing.assert_array_equal(before,scene.project_stars(Pose(x=.2))[0])

    def test_protection_extremes_and_soft_transitions(self):
        neb,stars,nd=input_pair();protection=np.zeros(nd.shape,np.float32)
        protection[:,:100]=1
        protection=cv2.GaussianBlur(protection,(0,0),4)
        scene=Scene(neb,stars,nd,out_w=200,out_h=120,protection=protection)
        scene.catalog.depth[:]=[1,0]
        pose=Pose(x=.12)
        locked=scene._project(pose,scene.surface_z)[0]
        full=scene.project_stars(pose,motion_over_nebula=1)[0]
        protect=scene.project_stars(pose,motion_over_nebula=0)[0]
        partial=scene.project_stars(pose,motion_over_nebula=.35)[0]
        np.testing.assert_allclose(protect[0],locked[0],atol=1e-5)
        np.testing.assert_allclose(protect[1],full[1],atol=1e-5)
        np.testing.assert_allclose(partial[0]-locked[0],.35*(full[0]-locked[0]),atol=1e-5)
        np.testing.assert_allclose(full,scene._project(pose,3.+(scene.catalog.depth-.5)*(-3.8)*.6)[0],atol=1e-5)

    def test_incoming_star_is_protected(self):
        neb,stars,nd=input_pair();protection=np.zeros_like(nd);protection[:,54:90]=1
        scene=Scene(neb,stars,nd,out_w=200,out_h=120,protection=protection)
        scene.catalog.depth[:]=[1,0]
        pose=Pose(x=-.12)
        normal=scene.project_stars(pose,motion_over_nebula=1)[0]
        locked=scene._project(pose,scene.surface_z)[0]
        reduced=scene.project_stars(pose,motion_over_nebula=0)[0]
        self.assertGreater(normal[0,0],60)
        self.assertLess(abs(reduced[0,0]-locked[0,0]),abs(normal[0,0]-locked[0,0]))

    def test_mask_feather_and_source_alignment(self):
        yy,xx=np.mgrid[:120,:200]
        neb=np.repeat((np.exp(-((xx-100)**2+(yy-60)**2)/500)*.6)[...,None],3,axis=2).astype(np.float32)
        protect=nebula_protection(neb)
        self.assertGreater(protect[60,100],.85);self.assertLess(protect[4,4],.05)
        self.assertLess(np.max(np.abs(np.diff(protect,axis=1))),.15)
        _,stars,nd=input_pair();cat=detect_stars(stars)
        a=Scene(neb,stars,nd,out_w=200,out_h=120,catalog=cat,protection=protect,fast_preview=True)
        b=Scene(neb,stars,nd,out_w=400,out_h=240,catalog=cat,protection=protect)
        p=Pose(x=.1,z=.3,yaw=2)
        np.testing.assert_allclose((a.project_stars(p)[0]+.5)/[200,120],(b.project_stars(p)[0]+.5)/[400,240],atol=1e-6)

    def test_templates_cache_and_depth_edit_reuses_detection(self):
        neb,stars,nd=input_pair();scene=Scene(neb,stars,nd,out_w=200,out_h=120)
        atlas=scene.prepare_sprites();scene.render(Pose(x=.1));scene.render(Pose(z=.2))
        self.assertIs(atlas,scene.prepare_sprites())
        changed=redistribute_depth(scene.catalog,dataclasses.replace(scene.catalog.settings,randomness=.9))
        self.assertIs(changed.sprites,scene.catalog.sprites)
        self.assertFalse(np.array_equal(changed.depth,scene.catalog.depth))

    def test_synthetic_is_separate_opt_in_and_deterministic(self):
        neb,stars,nd=input_pair();c=detect_stars(stars)
        default=Scene(neb,stars,nd,out_w=200,out_h=120,catalog=c)
        self.assertIs(default.catalog,c)
        a=with_synthetic_background(c,500);b=with_synthetic_background(c,500)
        self.assertEqual(a.original_count,len(c));self.assertGreater(len(a),len(c))
        np.testing.assert_array_equal(a.x,b.x);np.testing.assert_array_equal(a.depth,b.depth)
        np.testing.assert_array_equal(a.x[:len(c)],c.x)
        self.assertIs(a.sprites[0],c.sprites[0])

    def test_hotfix_dense_sampling_and_large_source(self):
        image=np.arange(40000,dtype=np.float32)[None,:]
        xs=np.linspace(0,39999,50001,dtype=np.float32)
        np.testing.assert_allclose(_sample_map_points(image,xs,np.zeros_like(xs)),xs,atol=.003)
        with self.assertRaises(ValueError):_sample_map_points(image,[1,2],[1])

    def test_compiled_and_python_compositor_agree(self):
        if not COMPILED:self.skipTest('Numba unavailable')
        neb,stars,nd=input_pair();scene=Scene(neb,stars,nd,out_w=200,out_h=120)
        a,m=scene.prepare_sprites();p,s,v,_=scene.project_stars(Pose(x=.08))
        np.testing.assert_allclose(draw_atlas(a,m,p,s,v,200,120,1.),draw_atlas.py_func(a,m,p,s,v,200,120,1.),atol=1e-6)

    def test_parallel_video_order_and_cpu_fallback(self):
        neb,stars,nd=input_pair();scene=Scene(neb,stars,nd,out_w=200,out_h=120)
        frames=default_keyframes('Fly-through',1)
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'serial.mp4';b=Path(tmp)/'parallel.mp4'
            render_video_scene(scene,frames,a,1,4,workers=1,encoder='cpu')
            info=render_video_scene(scene,frames,b,1,4,workers=2,encoder='cpu')
            self.assertEqual(info['encoder'],'libx264')
            r1=imageio.get_reader(a);r2=imageio.get_reader(b)
            for i in range(4):np.testing.assert_array_equal(r1.get_data(i),r2.get_data(i))
            r1.close();r2.close()
            with patch('motionstudio.video.working_hardware_encoders',return_value=()):
                self.assertEqual(video.select_encoder('nvenc'),'cpu')
            real_write=video._write;calls=[]
            def flaky(*args):
                calls.append(args[5])
                if args[5]=='nvenc':raise RuntimeError('simulated encoder failure')
                return real_write(*args)
            with patch('motionstudio.video.select_encoder',return_value='nvenc'),patch('motionstudio.video._write',side_effect=flaky):
                result=render_video_scene(scene,frames,Path(tmp)/'fallback.mp4',1,4,encoder='auto')
            self.assertEqual(calls,['nvenc','cpu']);self.assertEqual(result['encoder'],'libx264')
            fast=Scene(neb,stars,nd,out_w=200,out_h=120,fast_preview=True)
            with self.assertRaises(ValueError):render_video_scene(fast,frames,b,1,4)

if __name__=='__main__':unittest.main()
