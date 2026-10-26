"""Temporary lossless disk sequence. Independent of the bounded interactive RAM LRU."""
import tempfile
from pathlib import Path
import cv2
class PreviewSequence:
    def __init__(self,state,duration,count):
        self.folder=tempfile.TemporaryDirectory(prefix='astro-preview-');self.path=Path(self.folder.name)
        self.state=state;self.duration=duration;self.count=count;self.bytes=0
    def put(self,index,image):
        path=self.path/f'{index:06d}.png'
        if not cv2.imwrite(str(path),cv2.cvtColor(image,cv2.COLOR_RGB2BGR)):raise OSError('Cannot store temporary preview')
        self.bytes+=path.stat().st_size
        if self.bytes>2*1024**3:raise ValueError('Preview exceeds the 2 GB disk budget. Use a shorter preview duration.')
    def get(self,seconds):
        index=min(self.count-1,max(0,round(seconds/self.duration*(self.count-1))))
        image=cv2.imread(str(self.path/f'{index:06d}.png'))
        if image is None:raise OSError('Temporary preview frame is unavailable')
        return cv2.cvtColor(image,cv2.COLOR_BGR2RGB)
    def close(self):self.folder.cleanup()
