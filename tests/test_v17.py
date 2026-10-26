import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from motionstudio.gui import Main
from motionstudio.depth_edit import DepthPaint,DepthVersions
from motionstudio.depth_editor import DepthEditor
from motionstudio.enhanced_depth import combine
from motionstudio.numeric import IntControl,FloatControl
from motionstudio.scene3d import Scene
from gui_wait import wait_idle
APP=QApplication.instance() or QApplication([])
def test_multiscale_dust_controls_and_flat_input():
    y,x=np.mgrid[:80,:120];image=np.full((80,120,3),.4,np.float32);image[:,52:61]*=.15
    depth=(.5+.1*np.sin(x/30)).astype(np.float32)
    original=image.copy();a,base,fine=combine(image,depth)
    emphasized=combine(image,depth,dust=1.8)[0]
    assert np.max(np.abs(a-emphasized))>.01
    b,_,_=combine(image,depth,fine=1.8,dust=1.8,bias=.9)
    assert abs(a-b).max()>.03 and np.isfinite(b).all() and b.min()>=0 and b.max()<=1
    np.testing.assert_array_equal(image,original)
    flat=combine(np.ones_like(image)*.2,np.full(depth.shape,.5,np.float32))[0]
    np.testing.assert_allclose(flat,.5,atol=1e-6)
def test_selection_operations_are_non_destructive_and_undoable():
    generated=np.full((40,60),.5,np.float32);model=DepthPaint(DepthVersions(generated));mask=np.zeros_like(generated);mask[:,20:40]=1
    for operation in ('Back','Forward','Smooth','Flatten','Restore'):
        before=model.depth.copy();history=len(model.undo_stack);model.selected(mask,operation)
        np.testing.assert_array_equal(model.depth[:,:20],before[:,:20])
        if len(model.undo_stack)>history:
            after=model.depth.copy();model.undo();np.testing.assert_array_equal(model.depth,before);model.redo();np.testing.assert_array_equal(model.depth,after)
    np.testing.assert_array_equal(generated,.5)
def test_editor_selection_only_changes_depth_on_apply():
    editor=DepthEditor(DepthVersions(np.tile(np.linspace(0,1,60,dtype=np.float32),(40,1))))
    before=editor.model.depth.copy();editor.select_background();assert editor.canvas.selection.any()
    np.testing.assert_array_equal(before,editor.model.depth)
    editor.apply_selection('Back');assert np.any(editor.model.depth<before)
    editor.undo();np.testing.assert_array_equal(before,editor.model.depth)
    editor.clear_selection();assert not editor.canvas.selection.any();editor.close()
def test_explicit_numeric_buttons_and_typed_value():
    for cls in (IntControl,FloatControl):
        box=cls();box.setRange(1,300);box.setValue(15);box.plus.click();assert box.value()==16
        box.minus.click();assert box.value()==15
        box.lineEdit().setText('23');box.interpretText();assert box.value()==23
        box.setValue(300);assert not box.plus.isEnabled();box.setValue(1);assert not box.minus.isEnabled()
def test_build_preview_playback_never_renders_again():
    win=Main();win.starless=np.zeros((48,80,3),np.float32);win.stars=np.zeros((48,80,3),np.uint8);win.stars[20:23,30:33]=200
    win.duration.setValue(1);win.make_depth();wait_idle(win);win.build_preview();wait_idle(win)
    assert win.built_preview is not None and win.built_preview.count==16 and win._preview_seconds==0
    with patch.object(Scene,'render',side_effect=AssertionError('render during built playback')):
        win.toggle_playback();APP.processEvents();win.pause_playback();wait_idle(win)
    win.reset_project();assert win.built_preview is None;win.close()
