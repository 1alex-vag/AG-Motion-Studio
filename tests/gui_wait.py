"""Wait for asynchronous GUI operations while Qt continues dispatching events."""
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

def wait_idle(window,timeout=20):
    deadline=time.monotonic()+timeout;stable=0
    while time.monotonic()<deadline:
        QApplication.processEvents();QTest.qWait(1)
        idle=window.worker is None and not window.preview_debounce.isActive() and window._pending_preview is None
        stable=stable+1 if idle else 0
        if stable>=3:return
    raise AssertionError('GUI job did not finish before timeout: '+window.status.text())
