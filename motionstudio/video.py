"""Bounded parallel frame pipeline and verified hardware encoder selection."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import os
import subprocess
import tempfile

ENCODERS={
    'cpu':('libx264',['-preset','fast','-crf','18']),
    'nvenc':('h264_nvenc',['-preset','p4','-cq','20','-b:v','0']),
    'qsv':('h264_qsv',['-global_quality','20']),
    'amf':('h264_amf',['-quality','balanced','-qp_i','20','-qp_p','20']),
}

@lru_cache(maxsize=1)
def working_hardware_encoders():
    """A compiled encoder name alone does not prove there is a working GPU."""
    import imageio_ffmpeg
    exe=imageio_ffmpeg.get_ffmpeg_exe()
    listing=subprocess.run([exe,'-hide_banner','-encoders'],capture_output=True,text=True,timeout=10).stdout
    good=[]
    with tempfile.TemporaryDirectory() as tmp:
        for name in ('nvenc','qsv','amf'):
            codec,options=ENCODERS[name]
            if codec not in listing:continue
            command=[exe,'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=black:s=64x64:r=1',
                    '-frames:v','1','-an','-c:v',codec,*options,'-pix_fmt','yuv420p',str(Path(tmp)/f'{name}.mp4')]
            try:
                probe=subprocess.run(command,capture_output=True,timeout=8)
                if probe.returncode==0:good.append(name)
            except (OSError,subprocess.TimeoutExpired):pass
    return tuple(good)


def select_encoder(requested='auto'):
    if requested not in (*ENCODERS,'auto'):raise ValueError('Unknown video encoder')
    if requested=='cpu':return 'cpu'
    available=working_hardware_encoders()
    if requested=='auto':return available[0] if available else 'cpu'
    return requested if requested in available else 'cpu'


def worker_count(width,height,requested=0):
    from .sprites import COMPILED
    if not COMPILED:return 1  # pure-Python pixel loops cannot benefit from threads
    cores=max(1,os.cpu_count() or 1)
    target=min(4,max(1,cores//2)) if requested==0 else max(1,min(8,int(requested),cores))
    # Conservative cap for concurrent RGB, mapping arrays and ordered queue.
    available=1024*1024**2
    try:
        if os.name=='nt':
            import ctypes
            class Memory(ctypes.Structure):
                _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','extended')]
            memory=Memory();memory.length=ctypes.sizeof(memory)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):available=memory.avail_phys
        elif hasattr(os,'sysconf'):available=os.sysconf('SC_AVPHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')
    except (OSError,ValueError,AttributeError):pass
    budget=min(1024*1024**2,max(128*1024**2,available*.25))
    memory_cap=max(1,int(budget/max(1,width*height*120)))
    return min(target,memory_cap)


def _write(scene,keyframes,path,duration,fps,selected,workers,render_kwargs,progress,quality=18):
    import imageio_ffmpeg
    count=max(1,round(float(duration)*int(fps)))
    def frame(i):
        looping=scene.cinematic.enabled and scene.cinematic.loop!='Off'
        t=float(duration)*i/(count if looping else max(1,count-1))
        previous=t-.5/int(fps)
        if not looping:previous=max(0.,previous)
        return scene.render(scene.pose_at(keyframes,t,duration),
                            previous_pose=scene.pose_at(keyframes,previous,duration),**render_kwargs)
    # Warm the compiled kernel and templates on one thread. Scene stays read-only
    # during parallel rendering, and frame order is fixed by its numeric index.
    first=frame(0)
    codec,base_options=ENCODERS[selected]
    options=list(base_options)
    quality_flag={'cpu':'-crf','nvenc':'-cq','qsv':'-global_quality','amf':'-qp_i'}[selected]
    options[options.index(quality_flag)+1]=str(quality)
    if selected=='amf':options[options.index('-qp_p')+1]=str(quality)
    command=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-y',
        '-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s',f'{scene.w}x{scene.h}',
        '-r',str(fps),'-i','pipe:0','-an','-c:v',codec,*options,
        '-pix_fmt','yuv420p','-movflags','+faststart']
    if selected=='cpu':command+=['-threads',str(min(4,os.cpu_count() or 1))]
    command+=[str(path)]
    # Error output goes to a bounded file rather than an unread pipe that can deadlock.
    with tempfile.TemporaryFile() as errors:
        proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors)
        try:
            proc.stdin.write(first.tobytes())
            if progress:progress(1,count)
            if workers==1:
                for i in range(1,count):
                    proc.stdin.write(frame(i).tobytes())
                    if progress:progress(i+1,count)
            else:
                with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='astro-frame') as pool:
                    pending={};submit=1
                    for i in range(1,count):
                        while submit<count and len(pending)<workers:
                            pending[submit]=pool.submit(frame,submit);submit+=1
                        result=pending.pop(i).result()
                        proc.stdin.write(result.tobytes())
                        if progress:progress(i+1,count)
            proc.stdin.close()
            code=proc.wait(timeout=120)
            if code:
                errors.seek(0);raise RuntimeError(errors.read(8192).decode('utf-8','replace'))
        except BaseException as ex:
            try:proc.stdin.close()
            except (OSError,ValueError):pass
            if proc.poll() is None:proc.kill()
            proc.wait()
            errors.seek(0);detail=errors.read(8192).decode('utf-8','replace')
            raise RuntimeError(f'Video encoding failed: {detail or str(ex)}') from ex


def render_video(scene,keyframes,path,duration,fps,star_parallax=1.,depth_spread=.6,progress=None,
                 movement=True,brightness_boost=1.,bloom=False,motion_over_nebula=.35,
                 star_intensity=1.,workers=0,encoder='auto',status=None,quality=18):
    quality=int(quality)
    if not 0<=quality<=35:raise ValueError('Video quality must be between 0 and 35')
    if float(duration)<=0 or int(fps)<=0:raise ValueError('Duration and FPS must be positive')
    if scene.w%2 or scene.h%2:raise ValueError('H.264 export requires even image dimensions')
    if scene.fast_preview:raise ValueError('Final export requires a final-quality scene')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if status:status('Preparing video encoder…')
    selected=select_encoder(encoder);threads=worker_count(scene.w,scene.h,workers)
    scene.prepare_sprites(bloom)
    kwargs=dict(star_parallax=star_parallax,depth_spread=depth_spread,movement=movement,
        brightness_boost=brightness_boost,bloom=bloom,motion_over_nebula=motion_over_nebula,star_intensity=star_intensity)
    if status:
        reason=' (requested GPU unavailable; using CPU)' if encoder not in ('auto','cpu',selected) else ''
        status(f'Rendering with {threads} frame worker(s), {ENCODERS[selected][0]}{reason}…')
    original_progress=progress
    def progress(done,total):
        if status:status(f'Encoder: {ENCODERS[selected][0]} · Rendering frame {done} / {total}')
        if original_progress:original_progress(done,total)
    fd,temporary=tempfile.mkstemp(suffix='.mp4',prefix='.astro-render-',dir=path.parent);os.close(fd)
    temporary=Path(temporary)
    try:
        try:_write(scene,keyframes,temporary,duration,fps,selected,threads,kwargs,progress,quality)
        except RuntimeError:
            if selected=='cpu':raise
            selected='cpu'
            if status:status('Hardware encoding failed; restarting safely with CPU encoding…')
            _write(scene,keyframes,temporary,duration,fps,selected,threads,kwargs,progress,quality)
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)
    return {'quality':quality,'encoder':ENCODERS[selected][0],'workers':threads,'frames':max(1,round(float(duration)*int(fps)))}
