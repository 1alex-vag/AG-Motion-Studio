"""Editable Qt spin boxes with explicit, auto-repeating minus/plus buttons."""
from PyQt6.QtWidgets import QSpinBox,QDoubleSpinBox,QAbstractSpinBox,QPushButton
class Buttons:
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setMinimumWidth(100)
        self.setStyleSheet('QAbstractSpinBox {padding-left:29px;padding-right:29px;}')
        self.minus=QPushButton('−',self);self.plus=QPushButton('+',self)
        for button,slot in ((self.minus,self.stepDown),(self.plus,self.stepUp)):
            button.setAutoRepeat(True);button.setStyleSheet('padding:0px;border-radius:4px;');button.clicked.connect(slot)
        self.valueChanged.connect(self._limits);self._limits()
    def _limits(self,*_):
        self.minus.setEnabled(self.value()>self.minimum());self.plus.setEnabled(self.value()<self.maximum())
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.minus.setGeometry(1,1,25,self.height()-2);self.plus.setGeometry(self.width()-26,1,25,self.height()-2)
class IntControl(Buttons,QSpinBox):pass
class FloatControl(Buttons,QDoubleSpinBox):pass
