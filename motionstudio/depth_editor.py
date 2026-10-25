"""Dedicated visual depth editor. The caller is changed only after Apply."""
import math
import numpy as np
import cv2
from PyQt6.QtCore import Qt,QRectF,QPointF,pyqtSignal
from PyQt6.QtGui import QPainter,QImage,QColor,QPen,QKeySequence,QShortcut
from PyQt6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QComboBox,QSpinBox,QSlider,QPushButton,QCheckBox,QProgressBar,QDialogButtonBox)
from .depth_edit import DepthPaint
from .jobs import Work


class DepthCanvas(QWidget):
    edited=pyqtSignal()
    painting=pyqtSignal(bool)

    def __init__(self,model,parent=None):
        super().__init__(parent);self.model=model
        self.tool='Raise';self.brush_size=100;self.strength=.3;self.softness=.7
        self.before=False;self.pointer=None;self.down=False
        self.setMinimumSize(500,330);self.setMouseTracking(True)
        self.setStyleSheet('background:#0c1016')
        self.refresh()

    def image_rect(self):
        h,w=self.model.depth.shape;scale=min(self.width()/w,self.height()/h)
        return QRectF((self.width()-w*scale)/2,(self.height()-h*scale)/2,w*scale,h*scale)

    def image_point(self,position):
        rect=self.image_rect()
        if not rect.contains(position):return None
        h,w=self.model.depth.shape
        return ((position.x()-rect.x())*w/rect.width()-.5,(position.y()-rect.y())*h/rect.height()-.5)

    def refresh(self):
        depth=self.model.generated if self.before else self.model.depth
        h,w=depth.shape;scale=min(1.,1200/max(h,w))
        display=cv2.resize(depth,(max(1,round(w*scale)),max(1,round(h*scale))),interpolation=cv2.INTER_AREA)
        rgb=cv2.applyColorMap(np.uint8(np.clip(display,0,1)*255),cv2.COLORMAP_TURBO)[...,::-1].copy()
        self.image=QImage(rgb.data,rgb.shape[1],rgb.shape[0],rgb.strides[0],QImage.Format.Format_RGB888).copy()
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#0c1016'))
        painter.drawImage(self.image_rect(),self.image)
        if self.pointer is not None and self.image_point(self.pointer) is not None:
            radius=self.brush_size/2*self.image_rect().width()/self.model.depth.shape[1]
            painter.setPen(QPen(QColor('#ffffff'),1.3));painter.drawEllipse(self.pointer,radius,radius)
            painter.setPen(QPen(QColor('#60baff'),1));painter.drawEllipse(self.pointer,radius*(1-self.softness),radius*(1-self.softness))

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or self.before:return
        point=self.image_point(event.position())
        if point is None:return
        self.down=True;self.model.begin();self.painting.emit(True);self._paint(point)

    def _paint(self,point):
        self.model.stroke(*point,self.tool,self.brush_size,self.strength,self.softness)
        self.refresh()

    def mouseMoveEvent(self,event):
        self.pointer=event.position();point=self.image_point(self.pointer)
        if self.down and point is not None:self._paint(point)
        self.update()

    def mouseReleaseEvent(self,event):
        if not self.down:return
        self.down=False;self.model.end();self.painting.emit(False);self.edited.emit()

    def leaveEvent(self,event):
        self.pointer=None;self.update()
        # Release can occur outside the widget; never leave an unfinished stroke.
        if self.down:self.down=False;self.model.end();self.painting.emit(False);self.edited.emit()


class DepthEditor(QDialog):
    def __init__(self,versions,parent=None):
        super().__init__(parent);self.setWindowTitle('AG Astro Motion Studio V1.5 — Depth Editor')
        self.resize(1000,750);self.model=DepthPaint(versions);self.worker=None
        layout=QVBoxLayout(self);toolbar=QHBoxLayout();layout.addLayout(toolbar)
        self.tool=QComboBox();self.tool.addItems(['Raise','Lower','Smooth','Restore','Flatten'])
        self.size=QSpinBox();self.size.setRange(10,1000);self.size.setValue(100);self.size.setSuffix(' px')
        self.strength=QSpinBox();self.strength.setRange(1,100);self.strength.setValue(30);self.strength.setSuffix('%')
        self.softness=QSpinBox();self.softness.setRange(0,100);self.softness.setValue(70);self.softness.setSuffix('%')
        for label,control in [('Tool',self.tool),('Brush Size',self.size),('Strength',self.strength),('Softness',self.softness)]:toolbar.addWidget(QLabel(label));toolbar.addWidget(control)
        self.canvas=DepthCanvas(self.model);layout.addWidget(self.canvas,1)
        self.tool.currentTextChanged.connect(lambda v:setattr(self.canvas,'tool',v))
        self.size.valueChanged.connect(lambda v:setattr(self.canvas,'brush_size',v))
        self.strength.valueChanged.connect(lambda v:setattr(self.canvas,'strength',v/100))
        self.softness.valueChanged.connect(lambda v:setattr(self.canvas,'softness',v/100))
        self.canvas.edited.connect(self.refresh);self.canvas.painting.connect(self.painting)
        actions=QHBoxLayout();layout.addLayout(actions)
        self.undo_button=QPushButton('Undo');self.redo_button=QPushButton('Redo')
        self.reset_button=QPushButton('Reset Depth Map');self.compare=QCheckBox('Before / After — show Generated Depth')
        for button in (self.undo_button,self.redo_button,self.reset_button,self.compare):actions.addWidget(button)
        self.undo_button.clicked.connect(self.undo);self.redo_button.clicked.connect(self.redo)
        self.reset_button.clicked.connect(self.reset_depth);self.compare.toggled.connect(self.compare_changed)
        for key,slot in [(QKeySequence.StandardKey.Undo,self.undo),(QKeySequence.StandardKey.Redo,self.redo)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(slot)
        note=QLabel('Warm colors = closer. Restore and Reset return to Generated Depth. Apply keeps a separate Manual Depth; Cancel leaves the project untouched.')
        note.setWordWrap(True);layout.addWidget(note)
        self.status=QLabel('Depth editor ready');self.progress=QProgressBar();self.progress.setValue(100)
        layout.addWidget(self.status);layout.addWidget(self.progress)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.refresh()

    def painting(self,active):
        self.progress.setRange(0,0 if active else 100)
        if not active:self.progress.setValue(100)
        self.status.setText('Painting depth…' if active else 'Depth stroke completed — 100%')
        for widget in (self.undo_button,self.redo_button,self.reset_button,self.compare):widget.setEnabled(not active)
        if not active:self.refresh()

    def refresh(self):
        self.canvas.refresh();busy=self.worker is not None
        self.undo_button.setEnabled(bool(self.model.undo_stack) and not busy)
        self.redo_button.setEnabled(bool(self.model.redo_stack) and not busy)

    def compare_changed(self,value):self.canvas.before=value;self.canvas.refresh()

    def undo(self):
        if self.worker is not None or self.canvas.down:return
        self.model.undo();self.refresh();self.status.setText('Undo completed — 100%')

    def redo(self):
        if self.worker is not None or self.canvas.down:return
        self.model.redo();self.refresh();self.status.setText('Redo completed — 100%')

    def reset_depth(self):
        if self.worker is not None:return
        self.canvas.setEnabled(False);self.buttons.setEnabled(False);self.reset_button.setEnabled(False)
        self.progress.setRange(0,0);self.status.setText('Restoring Generated Depth…')
        self.worker=Work(lambda status,progress:self.model.reset(),self)
        self.worker.done.connect(lambda _:self.status.setText('Generated Depth restored — 100%'))
        self.worker.failed.connect(lambda error:self.status.setText('Depth reset failed: '+error))
        self.worker.finished.connect(self._finished);self.worker.start();self.refresh()

    def _finished(self):
        self.worker=None;self.canvas.setEnabled(True);self.buttons.setEnabled(True);self.reset_button.setEnabled(True)
        self.progress.setRange(0,100);self.progress.setValue(100);self.refresh()

    def done(self,result):
        if self.worker is not None:return
        super().done(result)

    def closeEvent(self,event):
        if self.worker is not None:event.ignore()
        else:super().closeEvent(event)
