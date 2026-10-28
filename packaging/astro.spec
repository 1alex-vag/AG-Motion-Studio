# Build on the intended operating system. PyInstaller is not a cross-compiler.
from pathlib import Path
import os,sys
from PyInstaller.utils.hooks import collect_all,collect_submodules
ROOT=Path(SPECPATH).parent
name='AG_Astro_Motion_Studio_v1.9_Experimental' if sys.platform=='win32' else 'AG_Astro_Motion_Studio_v1.6'
datas=[];binaries=[];hidden=[]
for package in ('numba','llvmlite'):
    d,b,h=collect_all(package,filter_submodules=lambda module:'.tests' not in module and '.cuda' not in module)
    datas+=d;binaries+=b;hidden+=h
import imageio_ffmpeg
ffmpeg=Path(imageio_ffmpeg.get_ffmpeg_exe())
binaries.append((str(ffmpeg),'imageio_ffmpeg/binaries'))
hidden+=['imageio_ffmpeg','PIL.Image','astropy.io.fits','tifffile']
a=Analysis([str(ROOT/'packaging'/'launcher.py')],pathex=[str(ROOT)],binaries=binaries,datas=datas,
    hiddenimports=hidden,hookspath=[str(ROOT/'packaging'/'hooks')],runtime_hooks=[],
    excludes=['tkinter','matplotlib','pandas','IPython','pytest','PyQt5','PySide6'],
    module_collection_mode={'motionstudio':'pyz+py','numba':'pyz+py','llvmlite':'pyz+py'})
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name=name,debug=False,
    strip=False,upx=False,console=sys.platform not in ('win32','darwin'),
    codesign_identity=os.environ.get('MAC_CODESIGN_IDENTITY'),entitlements_file=None)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name=name)
if sys.platform=='darwin':
    app=BUNDLE(coll,name='AG Astro Motion Studio.app',bundle_identifier='com.agastrophotography.astromotionstudio',
        info_plist={'CFBundleShortVersionString':'1.6.0','CFBundleVersion':'1.6.0',
                    'NSHighResolutionCapable':True,'LSMinimumSystemVersion':'13.0'})
