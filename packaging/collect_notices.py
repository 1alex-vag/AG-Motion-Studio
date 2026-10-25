"""Copy installed dependency license files into the native distribution."""
from pathlib import Path
import importlib.metadata as metadata
import subprocess,json


def collect(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    packages=['numpy','Pillow','opencv-python-headless','PyQt6','PyQt6-Qt6','PyQt6-sip','imageio','imageio-ffmpeg',
              'astropy','astropy-iers-data','pyerfa','tifffile','numba','llvmlite','packaging','PyYAML','PyInstaller']
    manifest={}
    for name in packages:
        dist=metadata.distribution(name);manifest[name]={'version':dist.version,'license':str(dist.metadata.get('License-Expression') or dist.metadata.get('License') or '')}
        for path in dist.files or []:
            lowered=str(path).lower()
            if any(token in lowered for token in ('license','copying','copyright','notice')) and '.dist-info/' in lowered:
                source=Path(dist.locate_file(path))
                if source.is_file():
                    relative=Path(str(path).split('.dist-info/',1)[1]);target=destination/name/relative
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
    import imageio_ffmpeg
    output=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-L'],capture_output=True,text=True,check=True)
    (destination/'FFmpeg-LICENSE.txt').write_text(output.stdout+output.stderr,encoding='utf-8')
    (destination/'DEPENDENCIES.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
