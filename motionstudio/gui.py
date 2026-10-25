"""Minimal PyQt6 desktop GUI for AG Astro Motion Studio V1."""
from __future__ import annotations
from pathlib import Path
import traceback
import json
import dataclasses
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QFileDialog, QMessageBox,
    QComboBox, QSlider, QSpinBox, QDoubleSpinBox, QProgressBar, QCheckBox, QGroupBox, QScrollArea, QFormLayout, QDialog, QDialogButtonBox, QListWidget, QSplitter, QLineEdit)
from . import engine as e
from . import scene3d as s3
from .cinematic import CinematicSettings, PRESETS
from .star_catalog import detect_stars, depth_map, DetectionSettings, normalized_rgb, redistribute_depth
from .protection import nebula_protection
from .sprites import COMPILED as SPRITE_COMPILED
from .jobs import Work
from .depth_edit import DepthVersions, checked_depth
from .depth_editor import DepthEditor
from .projects import portable_reference, resolve_reference
from .export_settings import RESOLUTIONS, validate_resolution
from . import __version__

STYLE = '''
QWidget { background:#141820; color:#eaf0f8; font-family:Segoe UI,Arial; font-size:13px; }
QGroupBox {border:1px solid #384453; border-radius:12px; margin-top:14px; padding:13px; font-weight:600;}
QGroupBox::title {subcontrol-origin:margin;left:13px;padding:0 6px;}
QPushButton {background:#273344;border:1px solid #4a5c70;border-radius:8px;padding:8px 13px;}
QPushButton:hover{background:#32465e;} QPushButton:disabled{color:#87919f;background:#20252c;}
QPushButton#primary {background:#236bd4; border:1px solid #4589e8; font-weight:600;}
QTabWidget::pane {border:1px solid #354252;border-radius:8px;}
QTabBar::tab {padding:8px 14px;background:#232c38;} QTabBar::tab:selected{background:#3167a8;}
QComboBox,QSpinBox {background:#202935;border:1px solid #506174;padding:7px;border-radius:6px;}
QProgressBar {border-radius:5px;background:#273443;text-align:center;}
QProgressBar::chunk{background:#3887f4;border-radius:5px;}
'''


class ImagePreview(QLabel):
    clicked = pyqtSignal(float,float)
    dragged = pyqtSignal(float,float)
    wheel_zoom = pyqtSignal(int)
    def __init__(self, text='No image loaded'):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(350, 310)
        self.setStyleSheet('background:#0c1016;border:1px solid #34404d;border-radius:9px;color:#8496ac')
        self.rgb = None
        self._drag_origin=None
        self._press_origin=None

    def mousePressEvent(self,ev):
        if ev.button()==Qt.MouseButton.LeftButton and self.rgb is not None:
            self._drag_origin=ev.position();self._press_origin=ev.position()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self,ev):
        if self._drag_origin is not None:
            p=ev.position()
            self.dragged.emit(float(p.x()-self._drag_origin.x()),float(p.y()-self._drag_origin.y()))
            self._drag_origin=p
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self,ev):
        if self._press_origin is not None and (ev.position()-self._press_origin).manhattanLength()<4 and self.rgb is not None:
            pixmap=self.pixmap()
            if pixmap is not None and not pixmap.isNull():
                x0=(self.width()-pixmap.width())/2;y0=(self.height()-pixmap.height())/2
                x=(ev.position().x()-x0)/max(1,pixmap.width()-1);y=(ev.position().y()-y0)/max(1,pixmap.height()-1)
                if 0<=x<=1 and 0<=y<=1:self.clicked.emit(x,y)
        self._press_origin=None
        self._drag_origin=None
        super().mouseReleaseEvent(ev)

    def wheelEvent(self,ev):
        if self.rgb is not None:
            self.wheel_zoom.emit(1 if ev.angleDelta().y()>0 else -1)
            ev.accept()
        else:super().wheelEvent(ev)

    def set_rgb(self, rgb):
        self.rgb = rgb
        self.refresh()

    def refresh(self):
        if self.rgb is None:
            return
        rgb=self.rgb
        import cv2
        scale=min(1.,max(1,self.width())/rgb.shape[1],max(1,self.height())/rgb.shape[0])
        if scale<1:rgb=cv2.resize(rgb,(max(1,round(rgb.shape[1]*scale)),max(1,round(rgb.shape[0]*scale))),interpolation=cv2.INTER_AREA)
        data = np.ascontiguousarray(np.uint8(normalized_rgb(rgb)*255+.5))
        h,w = data.shape[:2]
        q = QImage(data.data, w,h,data.strides[0], QImage.Format.Format_RGB888).copy()
        pix = QPixmap.fromImage(q)
        self.setPixmap(pix.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, evt):
        super().resizeEvent(evt)
        self.refresh()


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('AG Astro Motion Studio V1.5  •  ag_astrophotography')
        self.resize(1190, 790)
        self.setStyleSheet(STYLE)
        self.starless_path = self.star_path = None
        self.starless = self.stars = self.nd = self.sd = None
        self.depth_versions = None
        self.worker = None
        self.scene_cache = None
        self.catalog = None
        self.protection = None
        self.star_seed = 42
        self._last_duration = 8
        self.keyframes=s3.default_keyframes()
        self._job_kind=None
        self._pending_preview=None
        self._operation_text='Ready'
        self._operation_failed=False
        self._anchor_pick=False
        self.subject_anchor=(.5,.5)
        self.loop_frames=[]
        self._applying_cine_preset=False
        self.loop_index=0
        self.loop_timer=QTimer(self)
        self.loop_timer.timeout.connect(self._play_loop_frame)
        self.preview_debounce=QTimer(self)
        self.preview_debounce.setSingleShot(True)
        self.preview_debounce.timeout.connect(self.motion_preview)
        central = QWidget()
        self.setCentralWidget(central)
        whole = QVBoxLayout(central)
        whole.setContentsMargins(16,14,16,13)
        heading = QLabel('AG ASTRO MOTION STUDIO')
        heading.setStyleSheet('font-size:23px;font-weight:800;color:#f3f7ff;')
        title_row=QHBoxLayout();title_row.addWidget(heading);title_row.addStretch()
        about=QPushButton('About');about.clicked.connect(self.about_dialog);title_row.addWidget(about)
        whole.addLayout(title_row)
        sub = QLabel('Starless + star mask   →   Depth maps   →   Depth Refinement / Editing   →   Motion')
        sub.setStyleSheet('color:#93a6bd;margin-bottom:5px;')
        whole.addWidget(sub)

        body = QHBoxLayout()
        whole.addLayout(body,1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(370)
        scroll.setMaximumWidth(425)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        left = QWidget()
        left_col = QVBoxLayout(left)
        scroll.setWidget(left)
        body.addWidget(scroll)

        box1 = QGroupBox('1  IMPORT')
        l = QVBoxLayout(box1)
        self.btn_neb = QPushButton('Load Starless Image…')
        self.btn_star = QPushButton('Load Star Mask…')
        self.lbl_neb = QLabel('No starless image')
        self.lbl_star = QLabel('No star mask')
        for b, label in ((self.btn_neb,self.lbl_neb),(self.btn_star,self.lbl_star)):
            l.addWidget(b);l.addWidget(label)
            label.setWordWrap(True)
            label.setStyleSheet('color:#aebed0;font-size:11px;')
        self.btn_neb.clicked.connect(lambda:self.load_file(True))
        self.btn_star.clicked.connect(lambda:self.load_file(False))
        self.btn_reset=QPushButton('Reset Project')
        self.btn_reset.setToolTip('Clear the current scene. Source image files are kept.')
        self.btn_reset.clicked.connect(self.reset_project)
        self.btn_reset.setMaximumWidth(135)
        self.btn_reset.setStyleSheet('padding:5px 10px;')
        reset_row=QHBoxLayout();reset_row.addStretch();reset_row.addWidget(self.btn_reset)
        l.addLayout(reset_row)
        left_col.addWidget(box1)

        box2 = QGroupBox('2  DEPTH MAPS')
        l = QVBoxLayout(box2)
        self.btn_depth = QPushButton('Generate Depth Maps')
        self.btn_depth.setObjectName('primary')
        self.btn_depth.clicked.connect(self.make_depth)
        l.addWidget(self.btn_depth)
        self.btn_refine = QPushButton('Refine Nebula Depth')
        self.btn_refine.clicked.connect(self.refine);l.addWidget(self.btn_refine)
        l.addWidget(QLabel('Depth Refinement'))
        self.refinement_preset=QComboBox();self.refinement_preset.addItems(['Gentle','Balanced','Strong']);self.refinement_preset.setCurrentText('Balanced')
        l.addWidget(self.refinement_preset)
        note=QLabel('Improves the generated depth map using image structure, local contrast and edge-aware smoothing.')
        note.setWordWrap(True);note.setStyleSheet('color:#91a4bd;font-size:11px;');l.addWidget(note)
        self.btn_edit_depth=QPushButton('Edit Depth Map');self.btn_edit_depth.clicked.connect(self.edit_depth_map);l.addWidget(self.btn_edit_depth)
        self.btn_maps = QPushButton('Export Both Depth Maps (16-bit PNG)')
        self.btn_maps.clicked.connect(self.export_maps)
        l.addWidget(self.btn_maps)
        self.depth_extras=[l.itemAt(i).widget() for i in range(l.count()) if l.itemAt(i).widget() is not self.btn_depth]
        left_col.addWidget(box2)

        cinematic_box=QGroupBox('CINEMATIC')
        cf=QFormLayout(cinematic_box)
        self.cinematic_mode=QCheckBox('Cinematic Mode')
        cf.addRow(self.cinematic_mode)
        self.cine_main=QWidget();cm=QFormLayout(self.cine_main)
        self.cine_preset=QComboBox();self.cine_preset.addItems(['Custom',*PRESETS])
        cm.addRow('Preset',self.cine_preset)
        self.cine_sliders={}
        for key,title,maximum,default in [('strength','3D Strength',200,100),('camera_motion','Camera Motion',200,100),
                ('star_motion','Star Motion',200,100),('atmosphere','Atmosphere',100,25)]:
            widget=self._percent_control(key,title,maximum,default,cm)
        self.loop_mode=QComboBox();self.loop_mode.addItems(['Off','Ping-Pong','Seamless Orbit','Seamless Drift'])
        cm.addRow('Loop Mode',self.loop_mode)
        self.loop_duration=QComboBox();self.loop_duration.setEditable(True)
        self.loop_duration.addItems(['5','8','10','15','20']);self.loop_duration.setCurrentText('8')
        cm.addRow('Loop Duration (s)',self.loop_duration)
        self.loop_duration.lineEdit().editingFinished.connect(self._loop_duration_changed)
        self.loop_duration.activated.connect(lambda _:self._loop_duration_changed())
        self.btn_loop=QPushButton('Preview Loop');self.btn_loop.clicked.connect(self.preview_loop)
        cm.addRow(self.btn_loop)
        self.advanced_settings=QPushButton('Advanced Settings ▸');self.advanced_settings.setCheckable(True)
        cm.addRow(self.advanced_settings)
        cf.addRow(self.cine_main)
        self.cine_advanced=QWidget();ca=QFormLayout(self.cine_advanced)
        self.camera_path=QComboBox();self.camera_path.addItems(['Linear','Smooth','Cinematic']);self.camera_path.setCurrentText('Cinematic')
        self.keep_centered=QCheckBox('Keep Subject Centered');self.keep_centered.setChecked(True)
        self.auto_drift=QCheckBox('Automatic Cinematic Drift');self.auto_drift.setChecked(True)
        self.layer_split=QCheckBox('Nebula Layer Split');self.layer_split.setChecked(True)
        self.volumetric=QCheckBox('Volumetric Look');self.volumetric.setChecked(False)
        self.volumetric.toggled.connect(self._cinematic_changed)
        ca.addRow(self.volumetric)
        self.anchor_button=QPushButton('Pick Subject Anchor');self.anchor_button.setCheckable(True)
        self.anchor_button.toggled.connect(self.pick_anchor)
        reset_anchor=QPushButton('Use Image Center');reset_anchor.clicked.connect(self.reset_anchor)
        ca.addRow(self.anchor_button,reset_anchor)
        ca.addRow('Camera Path',self.camera_path)
        ca.addRow(self.keep_centered);ca.addRow(self.auto_drift);ca.addRow(self.layer_split)
        for key,title,maximum,default in [('contrast','Depth Contrast',200,100),('smoothing','Depth Smoothing',100,40),
                ('foreground_limit','Foreground Star Limit',100,50),('motion_blur','Star Motion Blur',100,15),('depth_haze','Depth Haze',100,100),('volumetric_strength','Volumetric Strength',100,25)]:
            self._percent_control(key,title,maximum,default,ca)
        info=QLabel('Artistic 2.5D depth. Centering aims at the image center or selected anchor and controls yaw/pitch. Volumetric Look is an artistic 2.5D enhancement. Closed loops use the camera path extent; Off and Ping-Pong follow its keyframes.')
        info.setWordWrap(True);ca.addRow(info)
        cf.addRow(self.cine_advanced)
        left_col.addWidget(cinematic_box)
        self.cine_preset.currentTextChanged.connect(self.apply_cinematic_preset)
        self.cinematic_mode.toggled.connect(self._cinematic_changed)
        self.advanced_settings.toggled.connect(self._advanced_visibility)
        self.loop_mode.currentTextChanged.connect(self._cinematic_changed)
        self.camera_path.currentTextChanged.connect(self._cinematic_changed)
        for check in (self.keep_centered,self.auto_drift,self.layer_split):check.toggled.connect(self._cinematic_changed)

        # 3D scene and manual camera share the exact video renderer.
        scene_box=QGroupBox('3  3D SCENE')
        sl=QGridLayout(scene_box)
        self.parallax=QSlider(Qt.Orientation.Horizontal)
        self.parallax.setRange(0,300);self.parallax.setValue(100)
        self.parallax_label=QLabel('100%')
        self.parallax.valueChanged.connect(lambda v:(self.parallax_label.setText(f'{v}%'),self.motion_preview()))
        self.depth_spread=QSlider(Qt.Orientation.Horizontal)
        self.depth_spread.setRange(0,100);self.depth_spread.setValue(60)
        self.depth_spread_label=QLabel('60%')
        self.depth_spread.valueChanged.connect(lambda v:(self.depth_spread_label.setText(f'{v}%'),self.motion_preview()))
        sl.addWidget(QLabel('Star Parallax'),0,0);sl.addWidget(self.parallax,0,1);sl.addWidget(self.parallax_label,0,2)
        sl.addWidget(QLabel('Star Depth Spread'),1,0);sl.addWidget(self.depth_spread,1,1);sl.addWidget(self.depth_spread_label,1,2)
        sl.addWidget(QLabel('Stars are individually projected in 3D. Nebula uses a depth surface.'),2,0,1,3)
        self.star_movement=QCheckBox('Enable star movement');self.star_movement.setChecked(True)
        self.star_movement.toggled.connect(lambda _:self.motion_preview())
        sl.addWidget(self.star_movement,3,0,1,3)
        self.star_preset=QComboBox();self.star_preset.addItems(['Custom','Natural','3D','Fly-through'])
        self.star_preset.currentTextChanged.connect(self.apply_star_preset)
        sl.addWidget(QLabel('Star preset'),4,0);sl.addWidget(self.star_preset,4,1,1,2)
        self.detection=QComboBox();self.detection.addItems(['Sensitive','Normal','Strict']);self.detection.setCurrentText('Normal')
        self.detection.currentTextChanged.connect(self.detection_changed)
        sl.addWidget(QLabel('Star Detection'),5,0);sl.addWidget(self.detection,5,1,1,2)
        self.star_count=QLabel('Stars: not detected');sl.addWidget(self.star_count,6,0,1,3)
        advanced_toggle=QPushButton('Advanced star settings ▾');advanced=QWidget();af=QFormLayout(advanced)
        self.detection_sigma=QDoubleSpinBox();self.detection_sigma.setRange(1,15);self.detection_sigma.setValue(3.5)
        self.minimum_area=QSpinBox();self.minimum_area.setRange(1,100);self.minimum_area.setValue(2)
        self.randomness=QDoubleSpinBox();self.randomness.setRange(0,1);self.randomness.setSingleStep(.05);self.randomness.setValue(.55)
        self.foreground=QDoubleSpinBox();self.foreground.setRange(-.5,.5);self.foreground.setSingleStep(.05)
        self.boost=QDoubleSpinBox();self.boost.setRange(.1,5);self.boost.setSingleStep(.1);self.boost.setValue(1)
        self.bloom=QCheckBox('Subtle bloom');self.bloom.setChecked(False)
        for title,widget in [('Detection sigma',self.detection_sigma),('Minimum area (source px)',self.minimum_area),
                             ('Depth randomness',self.randomness),('Foreground bias',self.foreground),('Brightness boost',self.boost),('Bloom',self.bloom)]:
            af.addRow(title,widget)
        for widget in (self.detection_sigma,self.minimum_area,self.randomness,self.foreground):
            widget.valueChanged.connect(self.rebuild_catalog)
        self.boost.valueChanged.connect(lambda _:self.motion_preview());self.bloom.toggled.connect(lambda _:self.motion_preview())
        advanced.hide();advanced_toggle.clicked.connect(lambda:advanced.setVisible(not advanced.isVisible()))
        sl.addWidget(advanced_toggle,7,0,1,3);sl.addWidget(advanced,8,0,1,3)
        detection_view=QPushButton('Detection view');detection_view.clicked.connect(lambda:self.debug_stars(False))
        depth_view=QPushButton('Depth view');depth_view.clicked.connect(lambda:self.debug_stars(True))
        sl.addWidget(detection_view,9,0,1,2);sl.addWidget(depth_view,9,2)
        self.original_only=QCheckBox('Use original stars only');self.original_only.setChecked(True)
        self.synthetic=QCheckBox('Add synthetic background stars');self.synthetic.setChecked(False)
        self.original_only.toggled.connect(lambda checked:self.set_synthetic(not checked))
        self.synthetic.toggled.connect(self.set_synthetic)
        self.nebula_motion=QSlider(Qt.Orientation.Horizontal);self.nebula_motion.setRange(0,100);self.nebula_motion.setValue(35)
        self.nebula_motion_label=QLabel('35%')
        self.nebula_motion.valueChanged.connect(lambda v:(self.nebula_motion_label.setText(f'{v}%'),self.motion_preview()))
        self.star_intensity=QSlider(Qt.Orientation.Horizontal);self.star_intensity.setRange(0,200);self.star_intensity.setValue(100)
        self.star_intensity_label=QLabel('100%')
        self.star_intensity.valueChanged.connect(lambda v:(self.star_intensity_label.setText(f'{v}%'),self.motion_preview()))
        # Move the existing advanced/debug rows down to keep the new main sliders visible.
        for row in (9,8,7,6,5,4,3,2):
            items=[]
            for index in range(sl.count()):
                item=sl.itemAt(index);r,c,rs,cs=sl.getItemPosition(index)
                if r==row:items.append((item.widget(),r,c,rs,cs))
            for widget,r,c,rs,cs in items:
                if widget:sl.removeWidget(widget);sl.addWidget(widget,r+4,c,rs,cs)
        sl.addWidget(QLabel('Star Motion over Nebula'),2,0);sl.addWidget(self.nebula_motion,2,1);sl.addWidget(self.nebula_motion_label,2,2)
        sl.addWidget(QLabel('Star Intensity'),3,0);sl.addWidget(self.star_intensity,3,1);sl.addWidget(self.star_intensity_label,3,2)
        sl.addWidget(self.original_only,4,0,1,3);sl.addWidget(self.synthetic,5,0,1,3)
        self.synthetic_density=QSpinBox();self.synthetic_density.setRange(0,5000);self.synthetic_density.setValue(300)
        self.synthetic_density.setSuffix(' / MP');self.synthetic_density.setEnabled(False)
        self.synthetic_density.valueChanged.connect(lambda _:self.motion_preview())
        af.addRow('Synthetic density',self.synthetic_density)
        protect_view=QPushButton('Nebula protection view');protect_view.clicked.connect(self.protection_preview)
        sl.addWidget(protect_view,14,0,1,3)
        left_col.addWidget(scene_box)

        camera_box=QGroupBox('4  CAMERA / KEYFRAMES')
        cg=QGridLayout(camera_box)
        self.cam={}
        values={'x':(-3,3,0),'y':(-3,3,0),'z':(-1.5,2.,0),
                'yaw':(-45,45,0),'pitch':(-45,45,0),'roll':(-45,45,0),'fov':(15,120,55)}
        for idx,(name,(lo,hi,default)) in enumerate(values.items()):
            inp=QDoubleSpinBox();inp.setRange(lo,hi);inp.setDecimals(2)
            inp.setSingleStep(.05 if name in ('x','y','z') else 1)
            inp.setValue(default);self.cam[name]=inp
            inp.valueChanged.connect(self._camera_changed)
            cg.addWidget(QLabel(name.upper()),idx//2,2*(idx%2))
            cg.addWidget(inp,idx//2,2*(idx%2)+1)
        self.kf_list=QListWidget();self.kf_list.setMaximumHeight(94)
        self.kf_list.currentRowChanged.connect(self.select_keyframe)
        cg.addWidget(self.kf_list,4,0,1,4)
        addbtn=QPushButton('Add / Replace at time')
        delbtn=QPushButton('Delete keyframe')
        addbtn.clicked.connect(self.add_keyframe)
        delbtn.clicked.connect(self.delete_keyframe)
        cg.addWidget(addbtn,5,0,1,2);cg.addWidget(delbtn,5,2,1,2)
        self.btn_top=QPushButton('Top View')
        self.btn_top.clicked.connect(self.top_preview)
        cg.addWidget(self.btn_top,6,0,1,4)
        self.camera_hint=QLabel('Drag preview = yaw/pitch · Mouse wheel = Z · Add keyframe to keep changes.')
        cg.addWidget(self.camera_hint,7,0,1,4)
        left_col.addWidget(camera_box)

        box3 = QGroupBox('5  VIDEO EXPORT')
        g = QGridLayout(box3)
        self.mode = QComboBox();self.mode.addItems(['Parallax','Push In','Pull Out','Side Drift','Fly-through','Orbit','Manual'])
        self.mode.currentTextChanged.connect(self._mode_changed)
        self.duration = QSpinBox();self.duration.setRange(1,600);self.duration.setValue(8);self.duration.setSuffix(' sec')
        self.fps = QComboBox();self.fps.addItems(['24','30','60']);self.fps.setCurrentIndex(1)
        self.orientation=QComboBox();self.orientation.addItems(['Landscape','Portrait'])
        self.preset=QComboBox();self.preset.addItems([f'{w}×{h}' for w,h in RESOLUTIONS['Landscape']]+['Custom'])
        self.custom_width=QSpinBox();self.custom_width.setRange(2,8192);self.custom_width.setSingleStep(2);self.custom_width.setValue(1280)
        self.custom_height=QSpinBox();self.custom_height.setRange(2,8192);self.custom_height.setSingleStep(2);self.custom_height.setValue(720)
        self.intensity = QSlider(Qt.Orientation.Horizontal);self.intensity.setRange(0,100);self.intensity.setValue(50)
        for row,(lab,widget) in enumerate([('Mode',self.mode),('Duration',self.duration),('FPS',self.fps),('Format',self.preset),('Motion strength',self.intensity)]):
            g.addWidget(QLabel(lab),row,0);g.addWidget(widget,row,1)
        self.btn_preview = QPushButton('Preview Current Frame')
        self.btn_preview.clicked.connect(self.motion_preview)
        self.btn_render = QPushButton('Render MP4…')
        self.btn_render.setObjectName('primary')
        self.btn_render.clicked.connect(self.export_video)
        self.preview_quality=QComboBox();self.preview_quality.addItems(['Fast Preview','High Quality Preview'])
        self.preview_quality.currentTextChanged.connect(lambda _:self.motion_preview())
        self.encoder=QComboBox();self.encoder.addItems(['Auto (GPU if available)','CPU – H.264','NVIDIA NVENC','Intel Quick Sync','AMD AMF'])
        self.frame_workers=QSpinBox();self.frame_workers.setRange(0,8);self.frame_workers.setValue(0)
        self.frame_workers.setSpecialValueText('Auto');self.frame_workers.setToolTip('Parallel frames. Auto is bounded by CPU and frame memory.')
        g.addWidget(QLabel('Orientation'),5,0);g.addWidget(self.orientation,5,1)
        g.addWidget(QLabel('Preview quality'),6,0);g.addWidget(self.preview_quality,6,1)
        self.export_advanced_toggle=QPushButton('Advanced Export Settings ▸');self.export_advanced_toggle.setCheckable(True)
        self.export_advanced=QWidget();ex=QFormLayout(self.export_advanced)
        self.video_quality=QSpinBox();self.video_quality.setRange(0,35);self.video_quality.setValue(18)
        self.video_quality.setToolTip('CRF/CQ quality: lower is higher quality and a larger file. Default 18.')
        self.output_path=QLineEdit();self.output_path.setPlaceholderText('Choose a file when rendering')
        for label,widget in [('Custom width',self.custom_width),('Custom height',self.custom_height),('Encoder',self.encoder),
                             ('Frame workers',self.frame_workers),('Quality (CRF/CQ)',self.video_quality),('Output path',self.output_path)]:ex.addRow(label,widget)
        self.export_advanced.hide()
        self.export_advanced_toggle.toggled.connect(self.toggle_export_advanced)
        self.orientation.currentTextChanged.connect(self.orientation_changed)
        self.custom_width.valueChanged.connect(self.motion_preview);self.custom_height.valueChanged.connect(self.motion_preview)
        g.addWidget(self.export_advanced_toggle,7,0,1,2);g.addWidget(self.export_advanced,8,0,1,2)
        g.addWidget(self.btn_preview,9,0,1,2);g.addWidget(self.btn_render,10,0,1,2)
        left_col.addWidget(box3)
        projects=QGroupBox('6  PROJECT');pl=QHBoxLayout(projects)
        save=QPushButton('Save project…');load=QPushButton('Open project…')
        save.clicked.connect(self.save_scene_project);load.clicked.connect(self.load_scene_project)
        pl.addWidget(save);pl.addWidget(load);left_col.addWidget(projects)
        self.edit_groups=(box2,cinematic_box,scene_box,camera_box,box3)
        self.project_buttons=(save,load)
        self.advanced_boxes=(scene_box,camera_box,self.cine_advanced)
        self._advanced_visibility()
        for label in left.findChildren(QLabel):label.setWordWrap(True)
        left_col.addStretch(1)

        right = QVBoxLayout()
        body.addLayout(right,1)
        self.tabs = QTabWidget()
        self.views = {}
        for name in ['Starless','Star mask','Nebula depth','Star depth','Star Detection','Nebula protection','3D Preview']:
            view = ImagePreview('Load images to begin' if name in ('Starless','Star mask') else 'Generate depth maps to begin')
            self.views[name]=view
            self.tabs.addTab(view,name)
        self.views['Starless'].clicked.connect(self.anchor_selected)
        self.views['3D Preview'].dragged.connect(self.drag_camera)
        self.views['3D Preview'].wheel_zoom.connect(self.zoom_camera)
        right.addWidget(self.tabs,1)
        frame_control = QHBoxLayout()
        frame_control.addWidget(QLabel('Preview position'))
        self.timeline = QSlider(Qt.Orientation.Horizontal);self.timeline.setRange(0,100);self.timeline.setValue(40)
        self.timeline.valueChanged.connect(self.motion_preview)
        frame_control.addWidget(self.timeline)
        right.addLayout(frame_control)
        self.status = QLabel('Ready. Import a starless image and matching star mask.')
        self._updating_cam=False
        self._refresh_keyframes()
        self.status.setWordWrap(True)
        self.progress = QProgressBar();self.progress.setValue(0)
        whole.addWidget(self.status);whole.addWidget(self.progress)
        self.duration.valueChanged.connect(self.duration_changed)
        self.preset.currentTextChanged.connect(self.motion_preview)
        self.intensity.valueChanged.connect(self.motion_preview)
        self._update_buttons()

    def _update_buttons(self):
        ready = (self.starless is not None and self.stars is not None
                 and self.starless.shape == self.stars.shape)
        maps = ready and self.nd is not None and self.sd is not None
        busy = self.worker is not None
        for group in self.edit_groups:group.setEnabled(not busy)
        self.timeline.setEnabled(not busy)
        self.btn_depth.setEnabled(ready and not busy)
        self.btn_refine.setEnabled(maps and not busy)
        self.btn_edit_depth.setEnabled(maps and not busy)
        self.btn_maps.setEnabled(maps and not busy)
        self.btn_preview.setEnabled(maps and not busy)
        self.btn_render.setEnabled(maps and not busy)
        self.btn_top.setEnabled(maps and not busy)
        self.btn_neb.setEnabled(not busy)
        self.btn_star.setEnabled(not busy)
        self.btn_reset.setEnabled(not busy)
        self.btn_loop.setEnabled(maps and not busy and self.loop_mode.currentText()!='Off')
        for b in self.project_buttons:b.setEnabled(not busy)

    def _percent_control(self,key,title,maximum,default,form):
        row=QWidget();layout=QHBoxLayout(row);layout.setContentsMargins(0,0,0,0)
        slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(0,maximum);slider.setValue(default)
        label=QLabel(f'{default}%');label.setMinimumWidth(40)
        layout.addWidget(slider);layout.addWidget(label)
        slider.valueChanged.connect(lambda v:(label.setText(f'{v}%'),self._cinematic_changed(slider_changed=True)))
        self.cine_sliders[key]=slider
        form.addRow(title,row)
        return slider

    def cinematic_settings(self):
        return CinematicSettings(enabled=self.cinematic_mode.isChecked(),
            **{k:v.value()/100 for k,v in self.cine_sliders.items()},
            loop=self.loop_mode.currentText(),path=self.camera_path.currentText(),
            centered=self.keep_centered.isChecked(),drift=self.auto_drift.isChecked(),layer_split=self.layer_split.isChecked(),
            volumetric=self.volumetric.isChecked(),anchor_x=self.subject_anchor[0],anchor_y=self.subject_anchor[1])

    def _advanced_visibility(self,*_):
        if not hasattr(self,'advanced_boxes'):return
        enabled=self.cinematic_mode.isChecked()
        advanced=enabled and self.advanced_settings.isChecked()
        self.cine_main.setVisible(enabled)
        for box in self.advanced_boxes[:2]:box.setVisible(not enabled or advanced)
        self.cine_advanced.setVisible(advanced)
        for widget in self.depth_extras:
            if widget is not None:widget.setVisible(not enabled or advanced)
        self.advanced_settings.setText('Advanced Settings ▾' if advanced else 'Advanced Settings ▸')
        centered=enabled and self.keep_centered.isChecked()
        for key in ('yaw','pitch'):self.cam[key].setEnabled(not centered)
        self.camera_hint.setText(('Drag preview = X/Y with center locked' if centered else 'Drag preview = yaw/pitch')+
                                 ' · Mouse wheel = Z · Add keyframe to keep changes.')

    def _cinematic_changed(self,*_,slider_changed=False):
        self.stop_loop()
        if slider_changed and not self._applying_cine_preset and hasattr(self,'cine_preset'):
            self.cine_preset.blockSignals(True);self.cine_preset.setCurrentText('Custom');self.cine_preset.blockSignals(False)
        self.scene_cache=None
        self._advanced_visibility()
        if hasattr(self,'btn_render'):
            self._update_buttons()
            self.preview_debounce.start(120)

    def apply_cinematic_preset(self,name):
        if name not in PRESETS:return
        self._applying_cine_preset=True
        try:
            for key,value in zip(('strength','camera_motion','star_motion','atmosphere','volumetric_strength'),PRESETS[name]):
                self.cine_sliders[key].setValue(round(100*value))
            self._cinematic_changed()
        finally:self._applying_cine_preset=False

    def _loop_duration_changed(self):
        try:
            value=int(self.loop_duration.currentText())
            if not 1<=value<=600:raise ValueError()
            self.duration.setValue(value)
        except ValueError:
            self.loop_duration.setCurrentText(str(self.duration.value()))
            self.status.setText('Loop duration: enter a whole number from 1 to 600 seconds.')

    def stop_loop(self):
        self.loop_timer.stop()
        self.loop_frames=[]
        if hasattr(self,'btn_loop'):self.btn_loop.setText('Preview Loop')

    def _play_loop_frame(self):
        if not self.loop_frames:return
        self.views['3D Preview'].set_rgb(self.loop_frames[self.loop_index])
        self.loop_index=(self.loop_index+1)%len(self.loop_frames)

    def preview_loop(self):
        if self.loop_timer.isActive():self.stop_loop();return
        if self.nd is None or self.worker is not None:return
        config=self.cinematic_settings()
        if not config.enabled or config.loop=='Off':return
        self.stop_loop();self.preview_debounce.stop()
        try:settings=self._settings()
        except ValueError as exc:self.status.setText(str(exc));return
        scale=min(1.,480/max(settings.width,settings.height))
        w=max(2,int(settings.width*scale)//2*2);h=max(2,int(settings.height*scale)//2*2)
        key,args=self._scene_snapshot(w,h,True);cached=self.scene_cache;frames=self.render_keyframes()
        duration=settings.duration;count=min(240,max(24,round(duration*12)))
        kwargs=self._render_arguments()
        def task(status,progress):
            status('Building loop preview scene…');progress(-1)
            scene=cached[1] if cached is not None and cached[0]==key else s3.Scene(**args)
            status('Rendering low-resolution loop preview…')
            result=[]
            for i in range(count):
                t=duration*i/count
                result.append(scene.render(scene.pose_at(frames,t,duration),
                    previous_pose=scene.pose_at(frames,t-.5/30,duration),**kwargs))
                progress(round(100*(i+1)/count))
            return result
        def done(result):
            self.loop_frames=result;self.loop_index=0
            self.loop_timer.start(max(1,round(1000*duration/count)))
            self.btn_loop.setText('Stop Loop Preview')
            self.tabs.setCurrentWidget(self.views['3D Preview'])
            self.status.setText('Loop preview playing. Check the wrap from the end to the beginning.')
        self._start_work(task,done,'loop','Building loop preview…')

    def _render_arguments(self):
        return dict(star_parallax=self.parallax.value()/100,depth_spread=self.depth_spread.value()/100,
            movement=self.star_movement.isChecked(),brightness_boost=self.boost.value(),bloom=self.bloom.isChecked(),
            motion_over_nebula=self.nebula_motion.value()/100,star_intensity=self.star_intensity.value()/100)

    def _clear_generated(self):
        self.stop_loop();self.preview_debounce.stop()
        self.nd=self.sd=self.catalog=self.protection=self.scene_cache=self.depth_versions=None
        self._pending_preview=None
        self._anchor_pick=False;self.anchor_button.setChecked(False)
        self.star_count.setText('Stars: not detected')
        self.progress.setValue(0)
        for name in ('Nebula depth','Star depth','Star Detection','Nebula protection','3D Preview'):
            self.views[name].rgb=None;self.views[name].clear();self.views[name].setText('Generate depth maps to begin')

    def reset_project(self):
        if self.worker is not None:return
        self._clear_generated()
        self.starless=self.stars=self.starless_path=self.star_path=None
        self.lbl_neb.setText('No starless image');self.lbl_star.setText('No star mask')
        for name in ('Starless','Star mask'):
            self.views[name].rgb=None;self.views[name].clear();self.views[name].setText('No project loaded')
        self.mode.blockSignals(True);self.mode.setCurrentText('Parallax');self.mode.blockSignals(False)
        self.intensity.blockSignals(True);self.intensity.setValue(50);self.intensity.blockSignals(False)
        self.keyframes=s3.default_keyframes(duration=self.duration.value())
        self.timeline.blockSignals(True);self.timeline.setValue(0);self.timeline.blockSignals(False)
        self.subject_anchor=(.5,.5)
        self._set_camera(s3.Pose());self._refresh_keyframes()
        self.tabs.setCurrentWidget(self.views['Starless'])
        self.status.setText('No project loaded')
        self._update_buttons()

    def load_file(self, neb):
        if self.worker is not None:return
        path,_=QFileDialog.getOpenFileName(self,'Choose '+('starless image' if neb else 'star mask'),'',
                                              'Astrophotography (*.fits *.fit *.fts *.tif *.tiff *.png *.jpg *.jpeg)')
        if not path:return
        try:
            img=e.load_image(path)
            if img.ndim!=3 or img.shape[-1]!=3 or min(img.shape[:2])<1 or not np.isfinite(img).all():
                raise ValueError('Please choose a valid RGB image.')
            other=self.stars if neb else self.starless
            incompatible=other is not None and other.shape!=img.shape
            self._clear_generated()
            if neb:
                self.starless=img;self.starless_path=path
                self.lbl_neb.setText(f'{Path(path).name}  •  {img.shape[1]}×{img.shape[0]}')
                self.views['Starless'].set_rgb(img)
                if incompatible:
                    self.stars=self.star_path=None;self.lbl_star.setText('No star mask')
            else:
                self.stars=img;self.star_path=path
                self.lbl_star.setText(f'{Path(path).name}  •  {img.shape[1]}×{img.shape[0]}')
                self.views['Star mask'].set_rgb(img)
                if incompatible:
                    self.starless=self.starless_path=None;self.lbl_neb.setText('No starless image')
            if incompatible:
                old='Star mask' if neb else 'Starless'
                self.views[old].rgb=None;self.views[old].clear();self.views[old].setText('Load matching image')
                self.status.setText(f'The previously loaded {old} image has a different resolution and was cleared. Please load the matching image.')
            elif self.starless is not None and self.stars is not None:
                e.validate_pair(self.starless,self.stars)
                self.status.setText('Both images loaded and dimensions match. Generate Depth Maps.')
            else:self.status.setText('Loaded. Import the matching second image.')
            self.tabs.setCurrentWidget(self.views['Starless' if neb else 'Star mask'])
            self._update_buttons()
        except Exception as exc:
            self.status.setText(str(exc));QMessageBox.warning(self,'Import issue',str(exc))
            self._update_buttons()

    @staticmethod
    def _depth_display(depth):
        import cv2
        h,w=depth.shape;scale=min(1.,1200/max(h,w))
        image=cv2.resize(depth,(max(1,round(w*scale)),max(1,round(h*scale))),interpolation=cv2.INTER_AREA) if scale<1 else depth
        return e.preview_depth(image)

    def make_depth(self):
        if self.worker is not None:return
        if self.starless is None or self.stars is None:return
        n,st=self.starless,self.stars;detection=self.detection_settings()
        try:settings=self._settings()
        except ValueError:settings=e.MotionSettings()  # depth generation is independent of export dimensions
        config=self.cinematic_settings()
        density=self.synthetic_density.value() if self.synthetic.isChecked() else 0
        scale=min(1.,640/max(settings.width,settings.height));w=max(2,int(settings.width*scale)//2*2);h=max(2,int(settings.height*scale)//2*2)
        def task(status,progress):
            status('Preparing images…');progress(-1);e.validate_pair(n,st);progress(10)
            status('Generating nebula depth…');progress(-1);nd=e.nebula_depth(n);progress(35)
            status('Detecting stars…');progress(-1);catalog=detect_stars(st,detection);progress(65)
            status('Generating star depth…');progress(-1);sd=depth_map(catalog);progress(75)
            status('Generating nebula protection…');progress(-1);protection=nebula_protection(n);progress(85)
            status('Building scene…');progress(-1)
            versions=DepthVersions(nd)
            scene=s3.Scene(n,st,versions.current,sd,w,h,catalog=catalog,protection=protection,fast_preview=True,cinematic=config,synthetic_density=density)
            progress(95)
            displays=[self._depth_display(value) for value in (nd,sd,protection)]
            return versions,catalog,sd,protection,displays,scene
        def done(result):
            versions,self.catalog,self.sd,self.protection,displays,scene=result
            self.depth_versions=versions;self.nd=versions.current
            key,_=self._scene_snapshot(w,h,True);self.scene_cache=(key,scene)
            self.star_count.setText(f'Stars: {len(self.catalog):,}')
            for name,image in zip(('Nebula depth','Star depth','Nebula protection'),displays):self.views[name].set_rgb(image)
            self.tabs.setCurrentWidget(self.views['Nebula depth'])
            self.status.setText('Ready — 100%. Depth maps generated. Refine, edit or preview the scene.')
        self._start_work(task,done,'depth','Generating depth maps…')

    def _operation_status(self,message):
        self._operation_text=message;self.status.setText(message)

    def _operation_progress(self,value):
        if value<0:self.progress.setRange(0,0)
        else:
            self.progress.setRange(0,100);self.progress.setValue(max(0,min(100,value)))

    def _start_work(self,task,after,kind='processing',label='Processing…'):
        if self.worker is not None:return False
        self.stop_loop();self.preview_debounce.stop()
        self._job_kind=kind;self._operation_failed=False
        self._operation_status(label);self._operation_progress(-1)
        worker=Work(task,self);self.worker=worker
        worker.status.connect(self._operation_status);worker.progress.connect(self._operation_progress)
        def commit(result):
            try:after(result)
            except Exception as exc:self._on_failure(str(exc))
        worker.done.connect(commit);worker.failed.connect(self._on_failure)
        worker.finished.connect(self._on_finished)
        worker.start();self._update_buttons()
        return True

    def _on_failure(self,msg):
        self._operation_failed=True;self._pending_preview=None
        self.progress.setRange(0,100);self.progress.setValue(0)
        self.status.setText('Operation failed: '+msg)
        QMessageBox.critical(self,'Operation failed',msg)

    def _on_finished(self):
        worker=self.worker;self.worker=None;self._job_kind=None
        if not self._operation_failed:self.progress.setRange(0,100);self.progress.setValue(100)
        self._update_buttons()
        if worker is not None:worker.deleteLater()
        pending=self._pending_preview;self._pending_preview=None
        if pending is not None and not self._operation_failed:QTimer.singleShot(0,lambda:self.motion_preview(manual=pending))

    def refine(self):
        if self.worker is not None or self.nd is None:return
        versions=self.depth_versions or DepthVersions(self.nd)
        strength=[.3,.6,.85][self.refinement_preset.currentIndex()];image=self.starless
        def task(status,progress):
            value=e.refine_nebula_depth(image,versions.generated,strength,status,progress)
            updated=versions.refined_copy(value);return updated,self._depth_display(updated.current)
        def done(result):
            self.depth_versions,display=result;self.nd=self.depth_versions.current;self.scene_cache=None
            self.views['Nebula depth'].set_rgb(display);self.tabs.setCurrentWidget(self.views['Nebula depth'])
            self.status.setText('Depth Refinement completed — 100%. Generated Depth remains available.')
        self._start_work(task,done,'refinement','Refining nebula depth…')

    def edit_depth_map(self):
        if self.worker is not None or self.nd is None:return
        self.stop_loop();self.preview_debounce.stop()
        versions=self.depth_versions or DepthVersions(self.nd)
        editor=DepthEditor(versions,self)
        if editor.exec()!=QDialog.DialogCode.Accepted:return
        painted=editor.model.depth
        def task(status,progress):
            status('Applying manual depth…');progress(-1)
            updated=DepthVersions(versions.generated,versions.refined,painted)
            return updated,self._depth_display(updated.current)
        def done(result):
            self.depth_versions,display=result;self.nd=self.depth_versions.current;self.scene_cache=None
            self.views['Nebula depth'].set_rgb(display);self.tabs.setCurrentWidget(self.views['Nebula depth'])
            self.status.setText('Manual Depth applied — 100%. Source image and Generated Depth are unchanged.')
        self._start_work(task,done,'depth-edit','Applying manual depth…')

    def _settings(self):
        if self.preset.currentText()=='Custom':w,h=validate_resolution(self.custom_width.value(),self.custom_height.value())
        else:
            import re
            w,h=map(int,re.findall(r'\d+',self.preset.currentText()))
        return e.MotionSettings(mode=self.mode.currentText(),duration=self.duration.value(),
            fps=int(self.fps.currentText()),intensity=self.intensity.value()/100,width=w,height=h)

    def orientation_changed(self,orientation):
        index=max(0,min(3,self.preset.currentIndex()))
        self.preset.blockSignals(True);self.preset.clear()
        self.preset.addItems([f'{w}×{h}' for w,h in RESOLUTIONS[orientation]]+['Custom'])
        self.preset.setCurrentIndex(index);self.preset.blockSignals(False)
        if orientation=='Portrait':self.custom_width.setValue(720);self.custom_height.setValue(1280)
        else:self.custom_width.setValue(1280);self.custom_height.setValue(720)
        self.motion_preview()

    def toggle_export_advanced(self,checked):
        self.export_advanced.setVisible(checked)
        self.export_advanced_toggle.setText('Advanced Export Settings ▾' if checked else 'Advanced Export Settings ▸')

    def pick_anchor(self,checked):
        self._anchor_pick=checked
        if checked:
            self.stop_loop();self.tabs.setCurrentWidget(self.views['Starless'])
            self.status.setText('Click the subject in the Starless preview to set its anchor.')

    def anchor_selected(self,x,y):
        if not self._anchor_pick or self.worker is not None:return
        self.subject_anchor=(x,y);self.anchor_button.setChecked(False)
        self._cinematic_changed();self.status.setText('Subject Anchor selected. Center locking uses this point.')

    def reset_anchor(self):
        self.subject_anchor=(.5,.5);self.anchor_button.setChecked(False);self._cinematic_changed()

    def about_dialog(self):
        QMessageBox.about(self,'About AG Astro Motion Studio',
            f'AG Astro Motion Studio V1.5 ({__version__})\nDeveloped by ag_astrophotography\n\n'
            'Artistic 2.5D animation from original starless and star-mask images.\nDepth Refinement runs locally and works offline.')

    def _mode_changed(self, mode):
        if mode == 'Manual': return
        if hasattr(self,'kf_list') and self.keyframes:
            if QMessageBox.question(self,'Replace camera path?',
                  'Replace existing camera keyframes with the '+mode+' preset?',
                  QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                  QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                self.mode.blockSignals(True);self.mode.setCurrentText('Manual');self.mode.blockSignals(False)
                return
        self.keyframes=s3.default_keyframes(mode,self.duration.value())
        self._refresh_keyframes()
        self.motion_preview()

    def drag_camera(self,dx,dy):
        if self.worker is not None:return
        self._updating_cam=True
        if self.cinematic_mode.isChecked() and self.keep_centered.isChecked():
            self.cam['x'].setValue(self.cam['x'].value()+dx*.003)
            self.cam['y'].setValue(self.cam['y'].value()+dy*.003)
        else:
            self.cam['yaw'].setValue(self.cam['yaw'].value()+dx*.12)
            self.cam['pitch'].setValue(self.cam['pitch'].value()+dy*.12)
        self._updating_cam=False
        self.motion_preview(manual=True)

    def zoom_camera(self,step):
        if self.worker is not None:return
        self.cam['z'].setValue(self.cam['z'].value()+step*.08)

    def _current_pose(self):
        return s3.Pose(time=self.duration.value()*self.timeline.value()/100,
                       **{k:v.value() for k,v in self.cam.items()})

    def _camera_changed(self, *_):
        if getattr(self,'_updating_cam',True):return
        self.motion_preview(manual=True)

    def _set_camera(self, pose):
        self._updating_cam=True
        for name,box in self.cam.items():box.setValue(getattr(pose,name))
        self._updating_cam=False

    def _refresh_keyframes(self):
        self.kf_list.blockSignals(True)
        self.kf_list.clear()
        for f in sorted(self.keyframes,key=lambda p:p.time):
            self.kf_list.addItem(f'◆  {f.time:.2f}s     X {f.x:.2f}  Y {f.y:.2f}  Z {f.z:.2f}')
        self.kf_list.blockSignals(False)

    def select_keyframe(self,idx):
        if idx < 0 or idx>=len(self.keyframes):return
        p=sorted(self.keyframes,key=lambda f:f.time)[idx]
        self.timeline.blockSignals(True)
        self.timeline.setValue(int(round(100*p.time/self.duration.value())))
        self.timeline.blockSignals(False)
        self._set_camera(p)
        self.motion_preview(manual=True)

    def add_keyframe(self):
        self.stop_loop()
        self.mode.blockSignals(True);self.mode.setCurrentText('Manual');self.mode.blockSignals(False)
        current=self._current_pose()
        self.keyframes=[k for k in self.keyframes if abs(k.time-current.time)>.05]+[current]
        self.keyframes.sort(key=lambda k:k.time)
        self._refresh_keyframes()
        self.status.setText('Camera keyframe saved at %.2fs.'%current.time)

    def delete_keyframe(self):
        idx=self.kf_list.currentRow()
        if idx>=0 and len(self.keyframes)>1:
            self.keyframes.pop(idx)
            self._refresh_keyframes()
            self.motion_preview()

    def _get_scene(self,w,h,fast_preview=False):
        if self.protection is None:self.protection=nebula_protection(self.starless)
        density=self.synthetic_density.value() if self.synthetic.isChecked() else 0
        key=(w,h,fast_preview,density,id(self.nd),id(self.sd),id(self.starless),id(self.stars),id(self.catalog),id(self.protection),self.cinematic_settings())
        if self.scene_cache is None or self.scene_cache[0]!=key:
            self.scene_cache=(key,s3.Scene(self.starless,self.stars,self.nd,self.sd,w,h,catalog=self.catalog,
                    protection=self.protection,fast_preview=fast_preview,synthetic_density=density,cinematic=self.cinematic_settings()))
        return self.scene_cache[1]

    def set_synthetic(self, enabled):
        for widget in (self.original_only,self.synthetic):widget.blockSignals(True)
        self.synthetic.setChecked(enabled);self.original_only.setChecked(not enabled)
        for widget in (self.original_only,self.synthetic):widget.blockSignals(False)
        self.synthetic_density.setEnabled(enabled)
        self.scene_cache=None;self.motion_preview()

    def protection_preview(self):
        if self.protection is None or self.worker is not None:return
        protection=self.protection
        self._start_work(lambda status,progress:self._depth_display(protection),
            lambda image:self._display_view('Nebula protection',image,'Nebula protection ready — 100%.'),'preview','Preparing protection preview…')

    def _display_view(self,name,image,message):
        self.views[name].set_rgb(image);self.tabs.setCurrentWidget(self.views[name]);self.status.setText(message)

    def top_preview(self):
        if self.nd is None or self.worker is not None:return
        key,args=self._scene_snapshot(900,520,False);pose=self._current_pose();spread=self.depth_spread.value()/100
        def task(status,progress):
            status('Building top view…');progress(-1)
            return s3.Scene(**args).top_view(pose,depth_spread=spread)
        self._start_work(task,lambda image:self._display_view('3D Preview',image,'Top view ready — 100%.'),'preview','Preparing top view…')

    def _scene_snapshot(self,w,h,fast):
        config=self.cinematic_settings();density=self.synthetic_density.value() if self.synthetic.isChecked() else 0
        key=(w,h,fast,density,id(self.nd),id(self.sd),id(self.starless),id(self.stars),id(self.catalog),id(self.protection),config)
        args=dict(starless=self.starless,stars=self.stars,nebdepth=self.nd,stardepth=self.sd,out_w=w,out_h=h,
                  catalog=self.catalog,protection=self.protection,fast_preview=fast,synthetic_density=density,cinematic=config)
        return key,args

    def motion_preview(self,value=None,manual=False):
        if not hasattr(self,'nd') or self.nd is None:return
        if self.worker is not None:
            self._pending_preview=manual;return
        try:settings=self._settings()
        except ValueError as exc:self.status.setText(str(exc));return
        fast=self.preview_quality.currentIndex()==0;limit=640 if fast else 900
        scale=min(1.,limit/max(settings.width,settings.height))
        w=max(2,int(settings.width*scale)//2*2);h=max(2,int(settings.height*scale)//2*2)
        key,args=self._scene_snapshot(w,h,fast);cached=self.scene_cache
        frames=self.render_keyframes();t=settings.duration*self.timeline.value()/100;pose=self._current_pose() if manual else None
        render_args=self._render_arguments();duration=settings.duration
        def task(status,progress):
            status('Preparing preview scene…');progress(-1)
            scene=cached[1] if cached is not None and cached[0]==key else s3.Scene(**args)
            current=scene.center_pose(pose) if manual else scene.pose_at(frames,t,duration)
            status('Rendering preview…');progress(-1)
            previous=None if manual else scene.pose_at(frames,t-.5/30 if scene.cinematic.loop!='Off' else max(0,t-.5/30),duration)
            image=scene.render(current,previous_pose=previous,**render_args)
            return scene,current,image
        def done(result):
            scene,current,image=result;self.scene_cache=(key,scene);self._set_camera(current)
            self.views['3D Preview'].set_rgb(image);self.tabs.setCurrentWidget(self.views['3D Preview'])
            self.status.setText('Preview ready — 100%.'+(' Subject anchor was limited to the output crop.' if scene.anchor_clamped else ''))
        self._start_work(task,done,'preview','Rendering preview…')

    def duration_changed(self, value):
        self.stop_loop()
        self.loop_duration.setCurrentText(str(value))
        factor=value/max(1,self._last_duration)
        self.keyframes=[dataclasses.replace(k,time=k.time*factor) for k in self.keyframes]
        self._last_duration=value
        self._refresh_keyframes();self.motion_preview()

    def detection_settings(self):
        return DetectionSettings(sigma=self.detection_sigma.value(),min_area=self.minimum_area.value(),
             randomness=self.randomness.value(),foreground_bias=self.foreground.value(),seed=self.star_seed)

    def detection_changed(self, name):
        self.detection_sigma.setValue({'Sensitive':2.5,'Normal':3.5,'Strict':5.}[name])

    def rebuild_catalog(self,*_):
        if self.stars is None or self.nd is None or self.worker is not None:return
        settings=self.detection_settings();catalog=self.catalog;stars=self.stars
        def task(status,progress):
            status('Detecting stars…');progress(-1)
            previous=catalog.settings if catalog is not None else None
            if previous and (previous.sigma,previous.min_area)==(settings.sigma,settings.min_area):updated=redistribute_depth(catalog,settings)
            else:updated=detect_stars(stars,settings)
            progress(75);status('Generating star depth…');depth=depth_map(updated)
            return updated,depth,self._depth_display(depth)
        def done(result):
            self.catalog,self.sd,display=result;self.scene_cache=None
            self.star_count.setText(f'Stars: {len(self.catalog):,}');self.views['Star depth'].set_rgb(display)
            self.status.setText('Star Detection completed — 100%.')
            self._pending_preview=False
        self._start_work(task,done,'detection','Detecting stars…')

    def apply_star_preset(self, name):
        if name not in ('Natural','3D','Fly-through'):return
        par,spread={'Natural':(80,45),'3D':(120,70),'Fly-through':(180,90)}[name]
        self.parallax.setValue(par);self.depth_spread.setValue(spread)

    def debug_stars(self,depth=False):
        if self.catalog is None or self.worker is not None:return
        try:settings=self._settings()
        except ValueError as exc:self.status.setText(str(exc));return
        scale=min(1.,900/max(settings.width,settings.height))
        key,args=self._scene_snapshot(max(2,int(settings.width*scale)//2*2),max(2,int(settings.height*scale)//2*2),False)
        spread=self.depth_spread.value()/100
        self._start_work(lambda status,progress:s3.Scene(**args).debug_view(depth,spread),
            lambda image:self._display_view('Star Detection',image,'Star detection view ready — 100%.'),'preview','Preparing star detection view…')

    def render_keyframes(self):
        frames=[dataclasses.replace(k) for k in self.keyframes]
        strength=self.intensity.value()/50
        # Motion strength applies to the path, not manually entered keyframes.
        if self.mode.currentText()!='Manual' and frames:
            origin=frames[0]
            for frame in frames[1:]:
                for k in ('x','y','z','yaw','pitch','roll'):
                    setattr(frame,k,getattr(origin,k)+(getattr(frame,k)-getattr(origin,k))*strength)
        return frames

    def project_document(self):
        return {'schema':6,'application':'AG Astro Motion Studio V1.5',
          'depth_refinement_preset':self.refinement_preset.currentText(),
          'export':{'orientation':self.orientation.currentText(),'quality':self.video_quality.value()},
          'cinematic':dataclasses.asdict(self.cinematic_settings()),'cinematic_preset':self.cine_preset.currentText(),
          'starless':self.starless_path,'star_mask':self.star_path,
          'animation':dataclasses.asdict(self._settings()),
          'star_parallax':self.parallax.value()/100,'star_depth_spread':self.depth_spread.value()/100,
          'star_movement':self.star_movement.isChecked(),'brightness_boost':self.boost.value(),
          'star_motion_over_nebula':self.nebula_motion.value()/100,'star_intensity':self.star_intensity.value()/100,
          'original_stars_only':self.original_only.isChecked(),'synthetic_background':self.synthetic.isChecked(),
          'synthetic_density':self.synthetic_density.value(),'preview_quality':self.preview_quality.currentIndex(),
          'video_encoder':self.encoder.currentIndex(),'frame_workers':self.frame_workers.value(),
          'bloom':self.bloom.isChecked(),'detection':dataclasses.asdict(self.detection_settings()),
          'keyframes':[dataclasses.asdict(k) for k in self.keyframes],
          'note':'Artistic relative depths; isolated observed star sprites, synthetic background opt-in only.'}

    @staticmethod
    def _write_document(path,doc,versions,protection):
        path=Path(path);doc=dict(doc)
        for key in ('starless','star_mask'):doc[key]=portable_reference(doc.get(key),path.parent)
        if versions is not None:
            depth_path=path.with_suffix('.depth.npz')
            np.savez_compressed(depth_path,nebula=versions.current,protection=protection,**versions.arrays())
            doc['nebula_depth_file']=depth_path.name
        path.write_text(json.dumps(doc,indent=2),encoding='utf-8')

    def write_project(self,path):
        versions=self.depth_versions or (DepthVersions(self.nd) if self.nd is not None else None)
        self._write_document(path,self.project_document(),versions,self.protection)

    def save_scene_project(self):
        if self.nd is None:return
        path,_=QFileDialog.getSaveFileName(self,'Save project','motion_project.json','JSON (*.json)')
        if not path:return
        try:self.write_project(path);self.status.setText('Project saved with camera, stars and nebula depth.')
        except Exception as ex:QMessageBox.critical(self,'Save failed',str(ex))

    def load_scene_project(self):
        if self.worker is not None:return
        path,_=QFileDialog.getOpenFileName(self,'Open project','','JSON (*.json)')
        if not path:return
        try:
            doc=json.loads(Path(path).read_text(encoding='utf-8'));base=Path(path).parent
            nebpath=resolve_reference(doc['starless'],base);starpath=resolve_reference(doc['star_mask'],base)
            for title,value,key in [('Starless Image',nebpath,'starless'),('Star Mask',starpath,'star_mask')]:
                if not value.exists():
                    replacement,_=QFileDialog.getOpenFileName(self,'Locate '+title,'','Images (*.fits *.fit *.fts *.tif *.tiff *.png *.jpg *.jpeg)')
                    if not replacement:return
                    if key=='starless':nebpath=Path(replacement)
                    else:starpath=Path(replacement)
            cine=CinematicSettings(**doc.get('cinematic',{}))
            detection=DetectionSettings(**doc.get('detection',{}))
            frames=[s3.Pose(**k) for k in doc.get('keyframes',[])] or s3.default_keyframes()
        except Exception as exc:QMessageBox.critical(self,'Open failed',str(exc));return
        def task(status,progress):
            status('Loading project images…');progress(-1)
            neb=e.load_image(nebpath);stars=e.load_image(starpath);e.validate_pair(neb,stars);progress(20)
            status('Restoring project depth…');progress(-1)
            protection=None
            if doc.get('nebula_depth_file'):
                with np.load(resolve_reference(doc['nebula_depth_file'],base),allow_pickle=False) as saved:
                    generated=checked_depth(saved['generated'] if 'generated' in saved else saved['nebula'],neb.shape[:2])
                    versions=DepthVersions(generated,saved['refined'] if 'refined' in saved else None,saved['manual'] if 'manual' in saved else None)
                    if 'protection' in saved:protection=checked_depth(saved['protection'],neb.shape[:2])
            else:versions=DepthVersions(e.nebula_depth(neb))
            progress(50);status('Detecting project stars…');progress(-1)
            catalog=detect_stars(stars,detection);sd=depth_map(catalog);progress(80)
            if protection is None:
                status('Generating nebula protection…');progress(-1);protection=nebula_protection(neb)
            displays=[self._depth_display(v) for v in (versions.current,sd,protection)]
            return neb,stars,versions,catalog,sd,protection,displays
        def done(result):
            neb,stars,versions,catalog,sd,protection,displays=result
            self.depth_versions=versions;nd=versions.current
            self.starless_path=str(nebpath);self.star_path=str(starpath)
            self.starless=neb;self.stars=stars;self.nd=nd;self.catalog=catalog;self.sd=sd
            self.protection=protection;self.scene_cache=None
            anim=doc.get('animation',{})
            controls=[self.mode,self.duration,self.fps,self.preset,self.intensity,self.parallax,self.depth_spread,
                      self.star_movement,self.boost,self.bloom,self.detection_sigma,self.minimum_area,self.randomness,self.foreground,
                      self.nebula_motion,self.star_intensity,self.original_only,self.synthetic,self.synthetic_density,
                      self.preview_quality,self.encoder,self.frame_workers]
            for widget in controls:widget.blockSignals(True)
            try:
                self.mode.setCurrentText(anim.get('mode','Manual'));self.duration.setValue(anim.get('duration',8))
                self.fps.setCurrentText(str(anim.get('fps',30)))
                self._restore_resolution(anim.get('width',1280),anim.get('height',720))
                self.video_quality.setValue(doc.get('export',{}).get('quality',18))
                self.intensity.setValue(round(anim.get('intensity',.5)*100))
                self.parallax.setValue(round(doc.get('star_parallax',1)*100));self.depth_spread.setValue(round(doc.get('star_depth_spread',.6)*100))
                self.star_movement.setChecked(doc.get('star_movement',True));self.boost.setValue(doc.get('brightness_boost',1))
                self.bloom.setChecked(doc.get('bloom',False));self.detection_sigma.setValue(detection.sigma)
                self.minimum_area.setValue(detection.min_area);self.randomness.setValue(detection.randomness)
                self.foreground.setValue(detection.foreground_bias)
                self.nebula_motion.setValue(round(doc.get('star_motion_over_nebula',.35)*100))
                self.star_intensity.setValue(round(doc.get('star_intensity',1)*100))
                synthetic=bool(doc.get('synthetic_background',False))
                self.synthetic.setChecked(synthetic);self.original_only.setChecked(not synthetic)
                self.synthetic_density.setValue(doc.get('synthetic_density',300));self.synthetic_density.setEnabled(synthetic)
                self.preview_quality.setCurrentIndex(doc.get('preview_quality',0));self.encoder.setCurrentIndex(doc.get('video_encoder',0))
                self.frame_workers.setValue(doc.get('frame_workers',0))
            finally:
                for widget in controls:widget.blockSignals(False)
            self._restore_cinematic(cine,doc.get('cinematic_preset','Custom'))
            self.refinement_preset.setCurrentText(doc.get('depth_refinement_preset','Balanced'))
            self.loop_duration.setCurrentText(str(self.duration.value()))
            self.star_seed=detection.seed
            self._last_duration=self.duration.value()
            self.keyframes=frames;self._refresh_keyframes()
            self.parallax_label.setText(f'{self.parallax.value()}%');self.depth_spread_label.setText(f'{self.depth_spread.value()}%')
            self.nebula_motion_label.setText(f'{self.nebula_motion.value()}%');self.star_intensity_label.setText(f'{self.star_intensity.value()}%')
            self.views['Nebula protection'].set_rgb(displays[2])
            self.lbl_neb.setText(nebpath.name);self.lbl_star.setText(starpath.name)
            self.star_count.setText(f'Stars: {len(catalog):,}')
            for name,image in [('Starless',neb),('Star mask',stars),('Nebula depth',displays[0]),('Star depth',displays[1])]:
                self.views[name].set_rgb(image)
            self._pending_preview=False;self.status.setText('Project restored — 100%.')
        self._start_work(task,done,'project','Opening project…')


    def _restore_resolution(self,w,h):
        orientation='Portrait' if h>w else 'Landscape'
        controls=(self.orientation,self.preset,self.custom_width,self.custom_height)
        blocked=[widget.blockSignals(True) for widget in controls]
        try:
            self.orientation.setCurrentText(orientation);self.preset.clear()
            sizes=[f'{x}×{y}' for x,y in RESOLUTIONS[orientation]]
            self.preset.addItems(sizes+['Custom']);text=f'{w}×{h}'
            self.preset.setCurrentText(text if text in sizes else 'Custom')
            self.custom_width.setValue(w);self.custom_height.setValue(h)
        finally:
            for widget,previous in zip(controls,blocked):widget.blockSignals(previous)

    def _restore_cinematic(self,config,preset='Custom'):
        controls=[self.cinematic_mode,self.cine_preset,self.loop_mode,self.camera_path,self.keep_centered,
                  self.auto_drift,self.layer_split,self.volumetric,*self.cine_sliders.values(),self.advanced_settings]
        for widget in controls:widget.blockSignals(True)
        try:
            self.cinematic_mode.setChecked(config.enabled)
            self.cine_preset.setCurrentText(preset)
            for key,slider in self.cine_sliders.items():slider.setValue(round(100*getattr(config,key)))
            self.loop_mode.setCurrentText(config.loop);self.camera_path.setCurrentText(config.path)
            self.keep_centered.setChecked(config.centered);self.auto_drift.setChecked(config.drift)
            self.layer_split.setChecked(config.layer_split);self.advanced_settings.setChecked(False)
            self.volumetric.setChecked(config.volumetric);self.subject_anchor=(config.anchor_x,config.anchor_y)
        finally:
            for widget in controls:widget.blockSignals(False)
        # Refresh percentage labels without triggering preview work.
        for slider in self.cine_sliders.values():
            label=slider.parentWidget().findChild(QLabel)
            label.setText(f'{slider.value()}%')
        self._advanced_visibility()

    def closeEvent(self,event):
        if self.worker is not None:
            self.status.setText('Please wait for the current operation before closing.')
            event.ignore();return
        self.stop_loop();self.preview_debounce.stop()
        super().closeEvent(event)

    def export_maps(self):
        target=QFileDialog.getExistingDirectory(self,'Export depth maps')
        if not target:return
        try:
            e.save_depth(self.nd,Path(target)/'nebula_depth_16bit.png')
            e.save_depth(self.sd,Path(target)/'stars_depth_16bit.png')
            e.save_depth(self.protection,Path(target)/'nebula_protection_16bit.png')
            self.write_project(Path(target)/'motion_project.json')
            self.status.setText('Saved nebula depth, star depth, nebula protection and project.')
        except Exception as exc:QMessageBox.critical(self,'Export error',str(exc))

    def export_video(self):
        if not SPRITE_COMPILED:
            QMessageBox.warning(self, 'Slow renderer active',
                'Numba acceleration is not active. Final rendering will be extremely slow and limited to one frame worker.\n\n'
                'Run INSTALL_WINDOWS.bat again, or install with:\npython -m pip install numba\n\nThen restart AG Astro Motion Studio.')
        path,_=QFileDialog.getSaveFileName(self,'Export animation',self.output_path.text().strip() or 'AG_Astro_Motion.mp4','MP4 Video (*.mp4)')
        if not path:return
        try:settings=self._settings()
        except ValueError as exc:QMessageBox.warning(self,'Export settings',str(exc));return
        self.output_path.setText(path)
        # Inputs are read-only during export; imports/depth processing/project loading are disabled.
        # Keep references rather than duplicating multi-GB source arrays.
        n,st,nd,sd=self.starless,self.stars,self.nd,self.sd
        frames=self.render_keyframes()
        catalog=self.catalog
        protection=self.protection
        density=self.synthetic_density.value() if self.synthetic.isChecked() else 0
        over_nebula=self.nebula_motion.value()/100;star_intensity=self.star_intensity.value()/100
        workers=self.frame_workers.value();encoder=['auto','cpu','nvenc','qsv','amf'][self.encoder.currentIndex()]
        movement=self.star_movement.isChecked();boost=self.boost.value();bloom=self.bloom.isChecked()
        doc=self.project_document()
        cine=self.cinematic_settings()
        quality=self.video_quality.value();versions=self.depth_versions or DepthVersions(nd)
        par=self.parallax.value()/100
        spread=self.depth_spread.value()/100
        duration=settings.duration;fps=settings.fps
        def task(status,progress):
            status('Building final 3D scene…');progress(-1)
            scene=s3.Scene(n,st,nd,sd,settings.width,settings.height,catalog=catalog,protection=protection,synthetic_density=density,cinematic=cine)
            encoding=s3.render_video_scene(scene,frames,path,duration,fps,par,spread,
                 progress=lambda done,total:progress(int(100*done/total)),
                 movement=movement,brightness_boost=boost,bloom=bloom,motion_over_nebula=over_nebula,
                 star_intensity=star_intensity,workers=workers,encoder=encoder,status=status,quality=quality)
            project_path=Path(path).with_suffix('.json')
            doc['render_result']=encoding
            self._write_document(project_path,doc,versions,protection)
            return path
        def done(out):
            self.status.setText('Video rendered: '+str(out))
            self.progress.setValue(100)
            QMessageBox.information(self,'Render complete','Saved:\n'+str(out))
        self._start_work(task,done,'video','Preparing video render…')


def main():
    import sys
    app=QApplication(sys.argv)
    gui=Main()
    gui.show()
    sys.exit(app.exec())

if __name__=='__main__':main()
