"""Portable references: forward-slash relative paths and legacy path recovery."""
from pathlib import Path,PureWindowsPath
import os


def portable_reference(value,base):
    if value is None:return None
    try:return Path(os.path.relpath(Path(value).resolve(),Path(base).resolve())).as_posix()
    except ValueError:return Path(value).as_posix()  # different Windows drives


def resolve_reference(value,base):
    if not isinstance(value,str) or not value:raise ValueError('Missing project input reference')
    normalized=value.replace('\\','/');p=Path(normalized)
    if p.is_absolute() and p.exists():return p
    if not PureWindowsPath(value).is_absolute() and not p.is_absolute():
        relative=Path(base)/p
        if relative.exists():return relative
    # A moved legacy project may still include the images next to its JSON.
    beside=Path(base)/p.name
    return beside if beside.exists() else p if p.is_absolute() else Path(base)/p
