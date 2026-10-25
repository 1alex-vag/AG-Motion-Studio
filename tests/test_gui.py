from gui_wait import wait_idle
"""Headless desktop integration, including real project and image roundtrips."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
import numpy as np
import cv2
import tifffile
from PyQt6.QtWidgets import QApplication,QFileDialog
from motionstudio.gui import Main
from motionstudio import engine as e
from motionstudio.stars import detect_stars,depth_map
from motionstudio.scene3d import Pose

APP=QApplication.instance() or QApplication([])

class GuiTests(unittest.TestCase):
    def test_tiff_preserves_faint_star(self):
        mask=np.zeros((70,100,3),np.uint16);cv2.circle(mask,(50,30),3,(70,60,40),-1)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'faint.tif';tifffile.imwrite(path,mask,photometric='rgb')
            data=e.load_image(path)
            self.assertEqual(data.dtype,np.float32)
            np.testing.assert_allclose(data[30,50],mask[30,50]/65535,rtol=1e-6)
            self.assertEqual(len(detect_stars(data)),1)

    def test_project_roundtrip_and_gui_preview(self):
        win=Main()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);neb=np.full((100,180,3),30,np.uint16)*200
            mask=np.zeros_like(neb);cv2.circle(mask,(50,40),3,(62000,40000,22000),-1)
            npth=root/'neb.tif';spth=root/'stars.tif'
            tifffile.imwrite(npth,neb,photometric='rgb');tifffile.imwrite(spth,mask,photometric='rgb')
            win.starless_path=str(npth);win.star_path=str(spth)
            win.starless=e.load_image(npth);win.stars=e.load_image(spth)
            win.make_depth();wait_idle(win);win.star_seed=87;win.rebuild_catalog();wait_idle(win)
            win.parallax.setValue(180);win.depth_spread.setValue(90)
            win.mode.blockSignals(True);win.mode.setCurrentText('Manual');win.mode.blockSignals(False)
            win.keyframes=[Pose(),Pose(time=8,x=.2,y=.03,z=.4,yaw=2)]
            win.boost.setValue(1.4);win.bloom.setChecked(False);win.motion_preview();wait_idle(win)
            expected=win._get_scene(180,100).render(Pose(x=.2),1.8,.9,True,1.4,False)
            before=win.catalog.depth.copy();proj=root/'project.json';win.write_project(proj)
            self.assertTrue(proj.with_suffix('.depth.npz').exists())
            fresh=Main()
            with patch.object(QFileDialog,'getOpenFileName',return_value=(str(proj),'JSON')),patch('motionstudio.gui.QMessageBox.critical') as errors:
                fresh.load_scene_project();wait_idle(fresh);errors.assert_not_called()
            np.testing.assert_array_equal(fresh.catalog.depth,before)
            np.testing.assert_array_equal(fresh.nd,win.nd)
            self.assertEqual(fresh.keyframes,win.keyframes)
            restored=fresh._get_scene(180,100).render(Pose(x=.2),fresh.parallax.value()/100,
                fresh.depth_spread.value()/100,fresh.star_movement.isChecked(),fresh.boost.value(),fresh.bloom.isChecked())
            np.testing.assert_array_equal(restored,expected)
            fresh.duration.setValue(4);self.assertEqual(fresh.keyframes[-1].time,4)
            fresh.debug_stars(True);wait_idle(fresh);fresh.close()
        win.close()

if __name__=='__main__':unittest.main()
