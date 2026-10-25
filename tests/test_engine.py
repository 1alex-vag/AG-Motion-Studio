"""Run from project root: python -m unittest discover -s tests -v"""
from pathlib import Path
import tempfile
import unittest
import sys
import numpy as np
import cv2
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motionstudio import engine as e


def synthetic():
    h,w=180,320
    yy,xx=np.mgrid[:h,:w]
    gradient=np.exp(-((xx-130)**2/(2*74**2) + (yy-90)**2/(2*40**2)))
    neb=np.stack([np.clip(gradient*185+7,0,255),np.clip(gradient*55+3,0,255),np.clip(gradient*115+4,0,255)],-1).astype('uint8')
    stars=np.zeros_like(neb)
    cv2.circle(stars,(80,44),3,(255,220,180),-1)
    cv2.circle(stars,(240,120),2,(130,200,255),-1)
    cv2.circle(stars,(220,50),1,(210,210,230),-1)
    return neb,stars

class EngineTests(unittest.TestCase):
    def setUp(self):self.neb,self.stars=synthetic()
    def test_depth_generation_and_separation(self):
        nd=e.nebula_depth(self.neb)
        sd=e.star_depth(self.stars)
        self.assertEqual(nd.shape,(180,320))
        self.assertEqual(sd.shape,(180,320))
        self.assertTrue(np.all(np.isfinite(nd)))
        self.assertTrue(np.all((nd>=0)&(nd<=1)))
        self.assertTrue(np.all((sd>=0)&(sd<=1)))
        self.assertGreater(float(nd.max()-nd.min()), .1)
        self.assertEqual(float(sd[160,300]), 0.)
        self.assertGreater(float(sd[44,80]),0.)
        np.testing.assert_array_equal(sd,e.star_depth(self.stars))
    def test_input_size_validation(self):
        with self.assertRaisesRegex(ValueError,'do not match'):
            e.validate_pair(self.neb,self.stars[:160])
    def test_two_motion_modes_and_depth_map_export(self):
        nd=e.nebula_depth(self.neb);sd=e.star_depth(self.stars)
        for mode in ('Parallax','Fly-through'):
            settings=e.MotionSettings(mode=mode,width=320,height=180)
            frame=e.render_frame(self.neb,self.stars,nd,sd,.5,settings)
            self.assertEqual(frame.shape,(180,320,3))
            self.assertEqual(frame.dtype,np.uint8)
            self.assertGreater(int(frame.max()),120)
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'nebula_depth_16bit.png'
            e.save_depth(nd,target)
            with Image.open(target) as im:
                self.assertEqual(im.mode,'I;16')
                self.assertEqual(im.size,(320,180))
    def test_png_read_and_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            Image.fromarray(self.neb).save(p/'neb.png')
            got=e.load_image(p/'neb.png')
            np.testing.assert_array_equal(got,self.neb)
            nd=e.nebula_depth(got);sd=e.star_depth(self.stars)
            target=p/'demo.mp4'
            progress=[]
            e.render_video(got,self.stars,nd,sd,target,e.MotionSettings(width=320,height=180,duration=2,fps=4),
                           progress=lambda i,n:progress.append((i,n)))
            self.assertTrue(target.exists())
            self.assertGreater(target.stat().st_size,1000)
            self.assertEqual(progress[-1],(8,8))

if __name__=='__main__': unittest.main()
