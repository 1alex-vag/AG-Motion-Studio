"""Writable application data and bundled FFmpeg selection, before Numba imports."""
from pathlib import Path
import os
import sys


def app_data_dir():
    if sys.platform=='win32':
        base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local'))
    elif sys.platform=='darwin':
        base=Path.home()/'Library'/'Application Support'
    else:
        base=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local'/'share'))
    return base/'AG Astro Motion Studio'


def configure_runtime():
    root=app_data_dir();(root/'cache'/'numba').mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('NUMBA_CACHE_DIR',str(root/'cache'/'numba'))
    if getattr(sys,'frozen',False) and not os.environ.get('IMAGEIO_FFMPEG_EXE'):
        binaries=Path(sys._MEIPASS)/'imageio_ffmpeg'/'binaries'
        candidates=sorted(p for p in binaries.glob('ffmpeg*') if p.is_file() and p.suffix in ('','.exe'))
        if candidates:os.environ['IMAGEIO_FFMPEG_EXE']=str(candidates[0])
    return root
