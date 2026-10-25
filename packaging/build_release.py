"""Build, smoke-test and archive a genuine native one-folder distribution."""
from pathlib import Path
import argparse,json,os,platform,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'packaging'))
from collect_notices import collect


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'release');parser.add_argument('--skip-tests',action='store_true')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen')
    if not args.skip_tests:subprocess.run([sys.executable,'-m','pytest','-q','tests'],cwd=ROOT,env=env,check=True)
    products=out/'build-products';dist=products/'dist';work=products/'work'
    subprocess.run([sys.executable,'-m','PyInstaller','--clean','--noconfirm','--distpath',str(dist),'--workpath',str(work),str(ROOT/'packaging'/'astro.spec')],cwd=ROOT,check=True)
    name='AG_Astro_Motion_Studio_v1.5'
    system={'win32':'Windows','darwin':'macOS'}.get(sys.platform,'Linux_validation')
    arch=platform.machine();suffix='' if sys.platform!='darwin' or arch=='arm64' else '_'+arch
    stage=out/(name+'_'+system+suffix);stage.mkdir(exist_ok=True)
    if sys.platform=='darwin':
        source=dist/'AG Astro Motion Studio.app';app=stage/source.name
        subprocess.run(['ditto',str(source),str(app)],check=True)
        executable=app/'Contents'/'MacOS'/name
        shutil.copy2(ROOT/'packaging'/'INSTALL_TO_APPLICATIONS.command',stage/'INSTALL_TO_APPLICATIONS.command')
    else:
        source=dist/name;app=stage/name
        shutil.copytree(source,app,dirs_exist_ok=True)
        executable=app/(name+('.exe' if sys.platform=='win32' else ''))
        if sys.platform=='win32':shutil.copy2(ROOT/'packaging'/'INSTALL_WINDOWS_STANDALONE.bat',stage/'INSTALL_WINDOWS.bat')
    smoke=stage/'PACKAGED_SELF_TEST.json'
    # Remove system Python and FFmpeg from PATH, exercising only the bundled runtime.
    smoke_env=dict(env);smoke_env.pop('PYTHONPATH',None);smoke_env.pop('PYTHONHOME',None);smoke_env.pop('IMAGEIO_FFMPEG_EXE',None)
    smoke_env['PATH']=str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32') if sys.platform=='win32' else '/usr/bin:/bin'
    subprocess.run([str(executable),'--self-test','--report',str(smoke)],cwd=stage,env=smoke_env,check=True,timeout=180)
    result=json.loads(smoke.read_text());assert result['ok'] and result['frozen']
    for filename in ['README.md','LICENSE','GITHUB_RELEASE_NOTES.md','DISTRIBUTION.md']:shutil.copy2(ROOT/filename,stage/filename)
    collect(stage/'THIRD_PARTY_LICENSES')
    (stage/'BUILD_INFO.json').write_text(json.dumps({'system':system,'architecture':arch,'python':platform.python_version(),'version':'1.5.0','self_test_passed':True},indent=2))
    archive=out/(name+'_'+system+suffix+'.zip')
    if sys.platform=='darwin':subprocess.run(['ditto','-c','-k','--sequesterRsrc',str(stage),str(archive)],check=True)
    else:shutil.make_archive(str(archive.with_suffix('')),'zip',stage)
    print(json.dumps({'archive':str(archive),'system':system,'architecture':arch,'self_test':str(smoke)}))

if __name__=='__main__':main()
