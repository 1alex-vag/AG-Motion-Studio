import unittest, tempfile
from pathlib import Path
import numpy as np
import cv2
import imageio.v2 as imageio
from motionstudio import scene3d as sc
from motionstudio.stars import detect_stars,DetectionSettings

def images():
    neb=np.zeros((100,180,3),dtype=np.uint8);neb[:]=(35,9,25)
    stars=np.zeros_like(neb)
    cv2.circle(stars,(48,46),2,(240,170,90),-1)
    cv2.circle(stars,(132,59),3,(100,170,240),-1)
    return neb,stars,np.full((100,180),.5,np.float32),None

class SceneTests(unittest.TestCase):
    def scene(self):return sc.Scene(*images(),180,100)
    def test_neutral_alignment_all_controls(self):
        scene=self.scene()
        for par in (0,1,3):
            for spread in (0,.6,1):
                pos,scale,valid,z=scene.project_stars(sc.Pose(),par,spread)
                np.testing.assert_allclose(pos,np.c_[scene.x,scene.y],atol=1e-5)
                np.testing.assert_allclose(scale,1,atol=1e-6)
                self.assertTrue(valid.all())
        np.testing.assert_allclose(scene.render_nebula(sc.Pose()),scene.neb,atol=1/255)
    def test_near_stars_move_more_and_spread(self):
        scene=self.scene();scene.catalog.depth[:]=[1,0];pose=sc.Pose(x=.2)
        pos,_,_,depth=scene.project_stars(pose,1,1)
        movement=np.abs(pos[:,0]-scene.x)
        self.assertLess(depth[0],depth[1]);self.assertGreater(movement[0],movement[1]*3)
        flat=scene.project_stars(pose,1,0)[0][:,0]-scene.x
        np.testing.assert_allclose(flat[0],flat[1],atol=1e-5)
    def test_zero_tracks_nebula_and_relative_multiplier(self):
        scene=self.scene();p=sc.Pose(x=.2,y=.1,z=.2,yaw=3,pitch=2,roll=4,fov=61)
        locked=scene.project_stars(p,0,1)[0]
        np.testing.assert_allclose(locked,scene._project(p,scene.surface_z)[0])
        self.assertGreater(np.max(np.abs(locked-np.c_[scene.x,scene.y])),1)
        normal=scene.project_stars(p,1,1)[0];double=scene.project_stars(p,2,1)[0]
        np.testing.assert_allclose(double-locked,2*(normal-locked),atol=1e-5)
        np.testing.assert_allclose(scene.project_stars(p,3,1,False)[0],locked)
    def test_preview_export_catalog_consistency(self):
        neb,stars,nd,sd=images();cat=detect_stars(stars)
        a=sc.Scene(neb,stars,nd,sd,180,100,catalog=cat);b=sc.Scene(neb,stars,nd,sd,360,200,catalog=cat)
        pa=a.project_stars(sc.Pose(x=.2),1,.8)[0];pb=b.project_stars(sc.Pose(x=.2),1,.8)[0]
        np.testing.assert_allclose((pa+.5)/[180,100],(pb+.5)/[360,200],atol=1e-6)
        self.assertIs(a.catalog,b.catalog)
    def test_round_gaussian_and_color_no_patch(self):
        scene=self.scene();img=scene.render(sc.Pose(),bloom=False)
        np.testing.assert_allclose(img[46,50],img[48,48],atol=1)
        self.assertGreater(int(img[46,48,0]),int(img[46,48,2]))
        self.assertGreater(int(img[59,132,2]),int(img[59,132,0]))
        self.assertFalse(hasattr(scene,'billboards'))
    def test_clip_empty_and_flythrough(self):
        scene=self.scene();scene.catalog.depth[:]=[1,0]
        _,_,valid,_=scene.project_stars(sc.Pose(z=1.5),1,1)
        self.assertFalse(valid[0]);self.assertTrue(valid[1]);scene.render(sc.Pose(z=2.5,yaw=40))
        neb,stars,nd,sd=images();stars[:]=0
        blank=sc.Scene(neb,stars,nd,sd,180,100)
        self.assertEqual(len(blank.catalog),0);self.assertEqual(blank.render(sc.Pose()).shape,(100,180,3))
    def test_detection_precision_noise_determinism_grayscale(self):
        data=np.zeros((60,80),np.uint16);cv2.circle(data,(25,30),2,70,-1);data[4,4]=5000
        c=detect_stars(data);self.assertEqual(len(c),1);self.assertAlmostEqual(c.x[0],25)
        np.testing.assert_array_equal(c.color,[[1,1,1]]);np.testing.assert_array_equal(c.depth,detect_stars(data).depth)
        rng=np.random.default_rng(1);noisy=rng.normal(.1,.003,(100,180)).astype(np.float32)
        cv2.circle(noisy,(60,40),3,.4,-1)
        self.assertEqual(len(detect_stars(noisy,DetectionSettings(sigma=5))),1)
    def test_keyframe_and_video_decode(self):
        frames=sc.default_keyframes('Fly-through',1);self.assertAlmostEqual(sc.camera_at(frames,.5).z,.375)
        scene=self.scene()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'real.mp4';progress=[]
            sc.render_video_scene(scene,frames,path,1,4,progress=lambda a,b:progress.append((a,b)))
            reader=imageio.get_reader(path);first=reader.get_data(0);last=reader.get_data(3);reader.close()
            self.assertEqual(first.shape,(100,180,3));self.assertGreater(np.abs(first.astype(float)-last).mean(),.1)
            self.assertLess(np.abs(first.astype(float)-scene.render(sc.Pose())).mean(),6)
            self.assertEqual(progress[-1],(4,4))

if __name__=='__main__':unittest.main()
