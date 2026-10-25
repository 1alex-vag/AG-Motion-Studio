"""Keep Astropy runtime/FITS support without collecting its optional test/UI packages."""
from PyInstaller.utils.hooks import collect_data_files,collect_submodules,copy_metadata

def runtime_module(name):
    if name in ('astropy.tests','astropy.tests.runner'):return True
    return not any(part in name.split('.') for part in ('tests','visualization'))

datas=collect_data_files('astropy',excludes=['**/tests/**'])
datas+=copy_metadata('astropy')+copy_metadata('numpy')
# Unit parser tables are loaded by filename rather than ordinary imports.
datas += [(path,target) for path,target in collect_data_files('astropy',include_py_files=True)
          if path.endswith(('_parsetab.py','_lextab.py'))]
hiddenimports=collect_submodules('astropy',filter=runtime_module)+['numpy.lib.recfunctions']
excludedimports=['astropy.visualization']
