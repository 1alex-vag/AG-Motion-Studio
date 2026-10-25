"""Session-only byte-bounded LRU. Owned exclusively by the GUI thread."""
from collections import OrderedDict

class PreviewCache:
    def __init__(self, maximum_mb=512):
        self.maximum_bytes=int(maximum_mb*1024**2)
        self.frames=OrderedDict();self.bytes=0;self.hits=0;self.misses=0
    def clear(self):
        self.frames.clear();self.bytes=0
    def get(self,key):
        value=self.frames.pop(key,None)
        if value is None:self.misses+=1;return None
        self.frames[key]=value;self.hits+=1;return value
    def put(self,key,value):
        old=self.frames.pop(key,None)
        if old is not None:self.bytes-=old[1].nbytes
        size=value[1].nbytes
        if size>self.maximum_bytes:return
        while self.frames and self.bytes+size>self.maximum_bytes:
            _,entry=self.frames.popitem(last=False);self.bytes-=entry[1].nbytes
        value[1].setflags(write=False)
        self.frames[key]=value;self.bytes+=size
    def resize(self,maximum_mb):
        self.maximum_bytes=int(maximum_mb*1024**2)
        while self.frames and self.bytes>self.maximum_bytes:
            _,entry=self.frames.popitem(last=False);self.bytes-=entry[1].nbytes
