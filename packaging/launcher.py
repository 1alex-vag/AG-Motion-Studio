"""Frozen and source entry point; runtime setup happens before JIT imports."""
import sys
from motionstudio.runtime import configure_runtime
configure_runtime()

if __name__=='__main__':
    if '--self-test' in sys.argv:
        from motionstudio.selftest import main
        main()
    else:
        from motionstudio.gui import main
        main()
