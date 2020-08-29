This repository contains scripts which can be used to build PyPy dependencies on Windows.

To run these scripts you must use Python 3.6+ and have Visual Studio 2017+ installed.

These scripts were tested on x64 with VS 2017 Community (version 15.9.20).

Tcl/Tk fails to build, all other dependencies build successfully (some are downloaded pre-built).

See `build_prepare.py` for details, based on https://foss.heptapod.net/pypy/externals/-/tree/branch/win32_160 readme.

See branch `win64_150` for built binaries.

===========

To run a PyPy translation and some tests like rpython/jit/backend, you need:

1. DO NOT use the same directory as your win32 checkout of pypy, if you already
installed the same dependencies for win32 in the parent directory of the
checkout, because there is confusion over which one it tries to pick.  Instead, I made
another clone (or 'hg share') inside this directory here.

2. the PYTHONPATH should point to a directory where you manually copy a few
pure-python packages, or maybe even to the same site-packages directory of
another python installation.  I needed 'attr', 'enum', 'hypothesis' and
'pycparser'.  (I copied them manually because I failed to run 'pip' with the
modified cpython6464.)

3. prepare and run a .bat file of this kind:

```
set PATH=d:\pypy\pypy\cpython6464\pcbuild\amd64;d:\pypy\pypy\pypy_ext\build\bin;%PATH%
set INCLUDE=d:\pypy\pypy\pypy_ext\build\include;%INCLUDE%
set LIB=d:\pypy\pypy\pypy_ext\build\lib;%LIB%
set PYTHONPATH=d:\pypy\pypy\pypy_ext\site-packages;%PYTHONPATH%

"C:\Program Files (x86)\Microsoft Visual Studio\2017\Community\VC\Auxiliary\Build\vcvars64.bat"
# commands put here won't be run, put them before
```
