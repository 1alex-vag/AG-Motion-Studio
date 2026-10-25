"""One-operation worker; GUI commits results only on the main Qt thread."""
from PyQt6.QtCore import QThread,pyqtSignal

class Work(QThread):
    _active=set()
    done=pyqtSignal(object)
    failed=pyqtSignal(str)
    status=pyqtSignal(str)
    progress=pyqtSignal(int)

    def __init__(self,func,parent=None):
        super().__init__(parent);self.func=func
        self.finished.connect(self._release)

    def start(self,*args):
        self._active.add(self)
        super().start(*args)

    def _release(self):
        self._active.discard(self)

    def run(self):
        try:self.done.emit(self.func(self.status.emit,self.progress.emit))
        except Exception as exc:self.failed.emit(str(exc))
