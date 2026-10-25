from gui_wait import wait_idle
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import cv2
from PIL import Image
from PyQt6.QtWidgets import QApplication,QFileDialog
from motionstudio.gui import Main
from motionstudio.scene3d import Pose
from motionstudio import engine

APP=QApplication.instance() or QApplication([])

class V13GuiTests(unittest.TestCase):
    def test_new_defaults_and_optional_mode(self):
        win=Main()
        self.assertTrue(win.original_only.isChecked());self.assertFalse(win.synthetic.isChecked())
        self.assertFalse(win.synthetic_density.isEnabled())
        self.assertEqual(win.nebula_motion.value(),35);self.assertEqual(win.star_intensity.value(),100)
        self.assertEqual(win.preview_quality.currentIndex(),0)
        win.synthetic.setChecked(True)
        self.assertFalse(win.original_only.isChecked());self.assertTrue(win.synthetic_density.isEnabled())
        win.original_only.setChecked(True)
        self.assertFalse(win.synthetic.isChecked());win.close()

    def test_new_settings_and_protection_project_roundtrip(self):
        win=Main()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);neb=np.zeros((120,200,3),np.uint8);neb[30:90,40:160]=[55,20,65]
            stars=np.zeros_like(neb);cv2.circle(stars,(55,55),3,(220,140,80),-1)
            n=root/'neb.png';s=root/'stars.png';Image.fromarray(neb).save(n);Image.fromarray(stars).save(s)
            win.starless_path=str(n);win.star_path=str(s);win.starless=engine.load_image(n);win.stars=engine.load_image(s)
            win.make_depth();wait_idle(win);win.star_seed=87;win.rebuild_catalog();wait_idle(win)
            win.nebula_motion.setValue(15);win.star_intensity.setValue(65);win.synthetic.setChecked(True)
            win.synthetic_density.setValue(500);win.preview_quality.setCurrentIndex(1)
            win.encoder.setCurrentIndex(2);win.frame_workers.setValue(3)
            before=win._get_scene(200,120).render(Pose(x=.12),motion_over_nebula=.15,star_intensity=.65)
            path=root/'project.json';win.write_project(path)
            fresh=Main()
            with patch.object(QFileDialog,'getOpenFileName',return_value=(str(path),'JSON')),patch('motionstudio.gui.QMessageBox.critical') as errors:
                fresh.load_scene_project();wait_idle(fresh);errors.assert_not_called()
            self.assertEqual(fresh.nebula_motion.value(),15);self.assertEqual(fresh.star_intensity.value(),65)
            self.assertTrue(fresh.synthetic.isChecked());self.assertFalse(fresh.original_only.isChecked())
            self.assertEqual(fresh.synthetic_density.value(),500);self.assertEqual(fresh.frame_workers.value(),3)
            self.assertEqual(fresh.encoder.currentIndex(),2);self.assertEqual(fresh.preview_quality.currentIndex(),1)
            self.assertEqual(fresh.star_seed,87)
            np.testing.assert_array_equal(fresh.protection,win.protection)
            np.testing.assert_array_equal(fresh.catalog.depth,win.catalog.depth)
            after=fresh._get_scene(200,120).render(Pose(x=.12),motion_over_nebula=.15,star_intensity=.65)
            np.testing.assert_array_equal(before,after);fresh.close()
        win.close()

if __name__=='__main__':unittest.main()
