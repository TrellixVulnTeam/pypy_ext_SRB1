import os
import shutil
import stat
import struct
import subprocess
import sys
from itertools import count
from time import sleep


def cmd_cd(path):
    return "cd /D {path}".format(**locals())


def cmd_set(name, value):
    return "set {name}={value}".format(**locals())


def cmd_append(name, value):
    op = "path " if name == "PATH" else "set {name}="
    return (op + "%{name}%;{value}").format(**locals())


def cmd_copy(src, tgt):
    return 'copy /Y /B "{src}" "{tgt}"'.format(**locals())


def cmd_xcopy(src, tgt):
    return 'xcopy /Y /E /I "{src}" "{tgt}"'.format(**locals())


def cmd_mkdir(path):
    return 'mkdir "{path}"'.format(**locals())


def cmd_rmdir(path):
    return 'rmdir /S /Q "{path}"'.format(**locals())


def cmd_nmake(makefile=None, target="", params=None):
    if params is None:
        params = ""
    elif isinstance(params, list) or isinstance(params, tuple):
        params = " ".join(params)
    else:
        params = str(params)

    return " ".join(
        [
            "{{nmake}}",
            "-nologo",
            '-f "{makefile}"' if makefile is not None else "",
            "{params}",
            '"{target}"',
        ]
    ).format(**locals())


def cmd_cmake(params=None, file="."):
    if params is None:
        params = ""
    elif isinstance(params, list) or isinstance(params, tuple):
        params = " ".join(params)
    else:
        params = str(params)
    return " ".join(
        [
            "{{cmake}}",
            "-DCMAKE_VERBOSE_MAKEFILE=ON",
            "-DCMAKE_RULE_MESSAGES:BOOL=OFF",
            "-DCMAKE_BUILD_TYPE=Release",
            "{params}",
            '-G "NMake Makefiles"',
            '"{file}"',
        ]
    ).format(**locals())


def cmd_msbuild(
    file, configuration="Release", target="Build", platform="{msbuild_arch}"
):
    return " ".join(
        [
            "{{msbuild}}",
            "{file}",
            '/t:"{target}"',
            '/p:Configuration="{configuration}"',
            "/p:Platform={platform}",
            "/m",
        ]
    ).format(**locals())


SF_MIRROR = "http://iweb.dl.sourceforge.net"

architectures = {
    "x86": {
        "cpython_arch": "win32",
        "boehm_arch": "NT",
        "boehm_target": r"Release\gc",
        "xz_arch": "i486",
        "tcl_arch": "IX86",
        "vcvars_arch": "x86",
        "msbuild_arch": "Win32",
    },
    "x64": {
        "cpython_arch": "amd64",
        "boehm_arch": "NT_X64",
        "boehm_target": r"gc64_dll",
        "xz_arch": "x86-64",
        "tcl_arch": "AMD64",
        "vcvars_arch": "x86_amd64",
        "msbuild_arch": "x64",
    },
}

header = [
    cmd_set("INCLUDE", "{inc_dir}"),
    cmd_set("INCLIB", "{lib_dir}"),
    cmd_set("LIB", "{lib_dir}"),
    cmd_append("PATH", "{bin_dir}"),
]

# dependencies, listed in order of compilation
deps = {
    "ntwin32.mak": {
        # ntwin32.mak is no longer distributed with Windows SDKs, needed for x64 Boehm GC
        "url": "https://gist.github.com/ynkdir/688e62f419e5374347bf/archive/d250598ddf5129addd212b8390279a01bca12706.zip",
        "filename": "688e62f419e5374347bf-d250598ddf5129addd212b8390279a01bca12706.zip",
        "dir": "688e62f419e5374347bf-d250598ddf5129addd212b8390279a01bca12706",
        "build": [
            cmd_copy("win32.mak", "ntwin32.mak"),
        ],
    },
    "boehm": {
        "url": "https://hboehm.info/gc/gc_source/gc-7.1.tar.gz",
        "filename": "gc-7.1.tar.gz",
        "dir": "gc-7.1",
        "patch": {
            r"misc.c": {
                "void GC_abort(const char *msg)\n"
                "{{\n"
                "#   if defined(MSWIN32)":
                    "void GC_abort(const char *msg)\n"
                    "{{\n"
                    "#   if 0",
            },
            r"include\private\gc_priv.h": {
                "# ifndef abs": "#if 0",
            },
            r"NT_X64_THREADS_MAKEFILE": {
                "cvarsmt": "cvarsdll",
            },
        },
        "build": [
            cmd_nmake("{boehm_arch}_THREADS_MAKEFILE", "CLEAN"),
            cmd_nmake("{boehm_arch}_THREADS_MAKEFILE", params="nodebug=1"),
        ],
        "headers": [r"include\gc.h"],
        "libs": [r"{boehm_target}.lib"],
        "bins": [r"{boehm_target}.dll"],
    },
    "zlib": {
        "url": "http://zlib.net/zlib1211.zip",
        "filename": "zlib1211.zip",
        "dir": "zlib-1.2.11",
        "build": [
            cmd_nmake(r"win32\Makefile.msc", "clean"),
            cmd_nmake(r"win32\Makefile.msc"),
        ],
        "headers": [r"z*.h"],
        "libs": [r"zlib.lib"],
        "bins": [r"zlib1.dll"],
    },
    "bz2": {
        "url": "https://github.com/python/cpython-source-deps/archive/bzip2-1.0.6.zip",
        "filename": "bzip2-1.0.6.zip",
        "dir": "cpython-source-deps-bzip2-1.0.6",
        "build": [
            cmd_nmake(r"makefile.msc", "clean"),
            cmd_nmake(r"makefile.msc"),
        ],
        "headers": [r"bzlib.h"],
        "libs": [r"libbz2.lib"],
    },
    "sqlite3": {
        # latest as of 2020-07-30 is 3.32.3.0
        "url": "https://github.com/python/cpython-source-deps/archive/sqlite-3.32.3.0.zip",
        "filename": "sqlite-3.32.3.0.zip",
        "dir": "cpython-source-deps-sqlite-3.32.3.0",
        "build": [
            cmd_copy(r"{winbuild_dir}\sqlite3.nmake", r"makefile.msc"),
            cmd_nmake(r"makefile.msc", "clean"),
            cmd_nmake(r"makefile.msc"),
        ],
        "headers": [r"sql*.h"],
        "libs": [r"*.lib"],
        "bins": [r"*.dll"],
    },
    "libexpat": {
        "url": "https://github.com/libexpat/libexpat/archive/R_2_2_4.zip",
        "filename": "R_2_2_4.zip",
        "dir": "libexpat-R_2_2_4",
        "patch": {
            r"expat\lib\xmltok.c": {
                "  const ptrdiff_t bytesStorable = toLim - *toP;\n":
                    "  const ptrdiff_t bytesStorable = toLim - *toP;\n"
                    "  const char * fromLimBefore;\n"
                    "  ptrdiff_t bytesToCopy;\n",
                "  const char * const fromLimBefore = fromLim;\n":
                    "  fromLimBefore = fromLim;\n",
                "  const ptrdiff_t bytesToCopy = fromLim - *fromP;\n":
                    "  bytesToCopy = fromLim - *fromP;\n",
            },
        },
        "build": [
            cmd_cd(r"expat\lib"),
            cmd_copy(r"{winbuild_dir}\libexpat.nmake", r"makefile.msc"),
            cmd_nmake(r"makefile.msc", "clean"),
            cmd_nmake(r"makefile.msc"),
        ],
        "headers": [r"expat.h", r"expat_external.h"],
        "libs": [r"libexpat.lib"],
        "bins": [r"libexpat.dll"],
    },
    "openssl-legacy": {
        # use pre-built OpenSSL from CPython
        "url": "https://github.com/python/cpython-bin-deps/archive/openssl-bin-1.0.2k.zip",
        "filename": "openssl-bin-1.0.2k.zip",
        "dir": "cpython-bin-deps-openssl-bin-1.0.2k",
        "build": [
            cmd_xcopy(r"{cpython_arch}\include", "{inc_dir}"),
        ],
        "libs": [r"{cpython_arch}\lib*.lib"],
        "bins": [r"{cpython_arch}\lib*.dll"],
    },
    "openssl": {
        # use pre-built OpenSSL from CPython
        "url": "https://github.com/python/cpython-bin-deps/archive/openssl-bin-1.1.1g.tar.gz",
        "filename": "openssl-bin-1.1.1g.tar.gz",
        "dir": "cpython-bin-deps-openssl-bin-1.1.1g",
        "build": [
            cmd_xcopy(r"{cpython_arch}\include", "{inc_dir}"),
        ],
        "libs": [r"{cpython_arch}\lib*.lib"],
        "bins": [r"{cpython_arch}\lib*.dll"],
    },
    "lzma": {
        "url": "http://tukaani.org/xz/xz-5.0.5-windows.zip",
        "filename": "xz-5.0.5-windows.zip",
        "dir": "xz-5.0.5-windows",
        "dir-create": True,
        "build": [
            cmd_copy(r"bin_{xz_arch}\liblzma.a", r"bin_{xz_arch}\lzma.lib"),
            cmd_xcopy(r"include", "{inc_dir}"),
        ],
        "libs": [r"bin_{xz_arch}\lzma.lib"],
        "bins": [r"bin_{xz_arch}\liblzma.dll"],
    },
    # Tcl/Tk are as close as I could get to CPython SVN without using SVN
    # These are the same version, unless CPython patched theirs
    "tcl": {
        "url": "https://master.dl.sourceforge.net/project/tcl/Tcl/8.5.2/tcl8.5.2-src.tar.gz",
        "filename": "tcl8.5.2-src.tar.gz",
        "dir": "tcl8.5.2",
        "patch": {
            r"generic\tclPosixStr.c": {
                # these were added as duplicates in modern MSVC, skip
                'case EPFNOSUPPORT: return "EPFNOSUPPORT";':
                    '/*case EPFNOSUPPORT: return "EPFNOSUPPORT";*/',
                'case ESOCKTNOSUPPORT: return "ESOCKTNOSUPPORT";':
                    '/*case ESOCKTNOSUPPORT: return "ESOCKTNOSUPPORT";*/',
                'case EPFNOSUPPORT: return "protocol family not supported";':
                    '/*case EPFNOSUPPORT: return "protocol family not supported";*/',
                'case ESOCKTNOSUPPORT: return "socket type not supported";':
                    '/*case ESOCKTNOSUPPORT: return "socket type not supported";*/',
            },
            r"generic\tcl.h": {
                # disable compatibility code for very old MSVC
                "#         if _MSC_VER < 1400 || !defined(_M_IX86)\n"
                "typedef struct _stati64	Tcl_StatBuf;":
                    "#         if _MSC_VER < 1400\n"
                    "typedef struct _stati64	Tcl_StatBuf;",
            },
            r"win\tclWinPort.h": {
                # modern MSVC no longer defines timezone alias, need to use _timezone
                "#    if defined(__MINGW32__) && !defined(__MSVCRT__)\n"
                "#	define timezone _timezone\n"
                "#    endif":
                    "#	define timezone _timezone",
            },
        },
        "build": [
            cmd_cd("win"),
            cmd_set("COMPILERFLAGS", "-DWINVER=0x0500"),
            cmd_set("DEBUG", "0"),
            cmd_set("INSTALLDIR", r"{tcltk_dir}"),
            cmd_set("MACHINE", "{tcl_arch}"),
            cmd_nmake("makefile.vc", "clean"),
            cmd_nmake("makefile.vc", "all"),
            cmd_nmake("makefile.vc", "install"),
            cmd_xcopy(r"{tcltk_dir}\lib\tcl8.5", r"{lib_dir}\tcl8.5")
        ],
        "headers": [r"{tcltk_dir}\include\tommath*.h", r"{tcltk_dir}\include\tcl*.h"],
        "libs": [r"{tcltk_dir}\lib\tcl*.lib"],
        "bins": [r"{tcltk_dir}\bin\tcl*.dll"],
    },
    "tk": {
        "url": "https://master.dl.sourceforge.net/project/tcl/Tcl/8.5.2/tk8.5.2-src.tar.gz",
        "filename": "tk8.5.2-src.tar.gz",
        "dir": "tk8.5.2",
        "patch": {
            r"win\tkWinPort.h": {
                # appears to be unused, conflicts with modern Win SDK
                "struct timezone {{\n"
                "    int tz_minuteswest;\n"
                "    int tz_dsttime;\n"
                "}};":
                    "/*\n"
                    " * struct timezone {{\n"
                    " *     int tz_minuteswest;\n"
                    " *     int tz_dsttime;\n"
                    " * }};\n"
                    " */",
            },
        },
        "build": [
            cmd_cd("win"),
            cmd_set("COMPILERFLAGS", "-DWINVER=0x0500"),
            cmd_set("OPTS", "noxp"),
            cmd_set("DEBUG", "1"),
            cmd_set("INSTALLDIR", r"{tcltk_dir}"),
            cmd_set("TCLDIR", r"{build_dir}\tcl8.5.2"),
            cmd_set("MACHINE", "{tcl_arch}"),
            cmd_nmake("makefile.vc", "clean"),
            cmd_nmake("makefile.vc", "all"),
            cmd_nmake("makefile.vc", "install"),
            cmd_xcopy(r"{tcltk_dir}\include\X11", r"{inc_dir}\X11"),
            cmd_xcopy(r"{tcltk_dir}\lib\tk8.5", r"{lib_dir}\tk8.5")
        ],
        "headers": [r"{tcltk_dir}\include\tk*.h"],
        "libs": [r"{tcltk_dir}\lib\tk*.lib"],
        "bins": [r"{tcltk_dir}\bin\tk*.dll"],
    },
}


# based on setuptools._distutils._msvccompiler version 50.0.0
def find_msvs2015():
    import winreg
    try:
        key = winreg.OpenKeyEx(
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\Microsoft\VisualStudio\SxS\VC7",
            access=winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
        )
    except OSError:
        print("Visual Studio not found in registry")
        return None

    with key:
        for i in count():
            try:
                v, vc_dir, vt = winreg.EnumValue(key, i)
            except OSError:
                print("Visual Studio 2015 not found")
                return None
            if v and vt == winreg.REG_SZ and os.path.isdir(vc_dir):
                try:
                    version = int(float(v))
                except (ValueError, TypeError):
                    continue
                if version == 14:
                    vspath = vc_dir
                    break

    vs = {
        "header": [],
        # nmake selected by vcvarsall
        "nmake": "nmake.exe",
        "vs_dir": vspath,
    }

    vcvarsall = os.path.join(vspath, "vcvarsall.bat")
    if not os.path.isfile(vcvarsall):
        print("Visual Studio vcvarsall not found")
        return None
    vs["header"].append('call "{}" {{vcvars_arch}} 8.1'.format(vcvarsall))

    try:
        key = winreg.OpenKeyEx(
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\Microsoft\MSBuild\ToolsVersions",
            access=winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
        )
    except OSError:
        print("MSBuild not found in registry")
        return None

    with key:
        for i in count():
            try:
                v = winreg.EnumKey(key, i)
            except OSError:
                print("MSBuild 14.0 not found")
                return None
            try:
                version = int(float(v))
            except (ValueError, TypeError):
                continue
            if version == 14:
                with winreg.OpenKeyEx(
                    key, v, access=winreg.KEY_READ | winreg.KEY_WOW64_32KEY
                ) as subkey:
                    msbuild_dir, vt = winreg.QueryValueEx(subkey, "MSBuildToolsPath")
                    msbuild = os.path.join(msbuild_dir, "MSBuild.exe")
                    if vt == winreg.REG_SZ and os.path.isfile(msbuild):
                        vs["msbuild"] = '"{}"'.format(msbuild)
                        break

    return vs


# based on distutils._msvccompiler from CPython 3.7.4
def find_msvs():
    root = os.environ.get("ProgramFiles(x86)") or os.environ.get("ProgramFiles")
    if not root:
        print("Program Files not found")
        return None

    try:
        vspath = (
            subprocess.check_output(
                [
                    os.path.join(
                        root, "Microsoft Visual Studio", "Installer", "vswhere.exe"
                    ),
                    "-latest",
                    "-prerelease",
                    "-requires",
                    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                    "-property",
                    "installationPath",
                    "-products",
                    "*",
                ]
            )
            .decode(encoding="mbcs")
            .strip()
        )
    except (subprocess.CalledProcessError, OSError, UnicodeDecodeError):
        print("vswhere not found")
        return None

    if not os.path.isdir(os.path.join(vspath, "VC", "Auxiliary", "Build")):
        print("Visual Studio seems to be missing C compiler")
        return None

    vs = {
        "header": [],
        # nmake selected by vcvarsall
        "nmake": "nmake.exe",
        "vs_dir": vspath,
    }

    # vs2017
    msbuild = os.path.join(vspath, "MSBuild", "15.0", "Bin", "MSBuild.exe")
    if os.path.isfile(msbuild):
        vs["msbuild"] = '"{}"'.format(msbuild)
    else:
        # vs2019
        msbuild = os.path.join(vspath, "MSBuild", "Current", "Bin", "MSBuild.exe")
        if os.path.isfile(msbuild):
            vs["msbuild"] = '"{}"'.format(msbuild)
        else:
            print("Visual Studio MSBuild not found")
            return None

    vcvarsall = os.path.join(vspath, "VC", "Auxiliary", "Build", "vcvarsall.bat")
    if not os.path.isfile(vcvarsall):
        print("Visual Studio vcvarsall not found")
        return None
    vs["header"].append('call "{}" {{vcvars_arch}}'.format(vcvarsall))

    return vs


def extract_dep(url, filename, dir=None):
    import urllib.request
    import tarfile
    import zipfile

    file = os.path.join(depends_dir, filename)
    if not os.path.exists(file):
        ex = None
        for i in range(3):
            try:
                print("Fetching %s (attempt %d)..." % (url, i + 1))
                content = urllib.request.urlopen(url).read()
                with open(file, "wb") as f:
                    f.write(content)
                break
            except urllib.error.URLError as e:
                ex = e
        else:
            raise RuntimeError(ex)

    print("Extracting " + filename)
    if dir:
        dir = os.path.join(build_dir, dir)
    else:
        dir = build_dir
    if filename.endswith(".zip"):
        with zipfile.ZipFile(file) as zf:
            zf.extractall(dir)
    elif filename.endswith(".tar.gz") or filename.endswith(".tgz"):
        with tarfile.open(file, "r:gz") as tgz:
            tgz.extractall(dir)
    else:
        raise RuntimeError("Unknown archive type: " + filename)


def write_script(name, lines):
    name = os.path.join(build_dir, name)
    lines = [line.format(**prefs) for line in lines]
    print("Writing " + name)
    with open(name, "w") as f:
        f.write("\n".join(lines))
    if verbose:
        for line in lines:
            print("    " + line)


def get_footer(dep):
    lines = []
    for out in dep.get("headers", []):
        lines.append(cmd_copy(out, "{inc_dir}"))
        lines.append("@if errorlevel 1 exit /B 1")
    for out in dep.get("libs", []):
        lines.append(cmd_copy(out, "{lib_dir}"))
        lines.append("@if errorlevel 1 exit /B 1")
    for out in dep.get("bins", []):
        lines.append(cmd_copy(out, "{bin_dir}"))
        lines.append("@if errorlevel 1 exit /B 1")
    return lines


def build_dep(name):
    dep = deps[name]
    dir = dep["dir"]
    file = "build_dep_{name}.cmd".format(**locals())

    extract_dep(dep["url"], dep["filename"], dep["dir"] if dep.get("dir-create", False) else None)

    for patch_file, patch_list in dep.get("patch", {}).items():
        if verbose:
            print("Patching " + patch_file)
        patch_file = os.path.join(build_dir, dir, patch_file.format(**prefs))
        with open(patch_file, "r") as f:
            text = f.read()
        for patch_from, patch_to in patch_list.items():
            text = text.replace(patch_from.format(**prefs), patch_to.format(**prefs))
        with open(patch_file, "w") as f:
            f.write(text)

    banner = "Building {name} ({dir})".format(**locals())
    lines = [
        "@echo " + ("=" * 70),
        "@echo ==== {:<60} ====".format(banner),
        "@echo " + ("=" * 70),
        "cd /D %s" % os.path.join(build_dir, dir),
        *prefs["header"],
        *dep.get("build", []),
        *get_footer(dep),
    ]

    write_script(file, lines)
    return file


def build_dep_all():
    lines = ["@echo on"]
    enabled = []
    for dep_name in deps:
        if dep_name in disabled:
            continue
        enabled.append(dep_name)
        lines.append(r'cmd.exe /c "{{build_dir}}\{}"'.format(build_dep(dep_name)))
        lines.append("@if errorlevel 1 @echo Build failed! && exit /B 1")
    lines.append("@echo All PyPy dependencies built successfully!")
    write_script("build_dep_all.cmd", lines)
    write_script(".gitignore", ["*"])
    print("Finished writing scripts for: " + ", ".join(enabled))


if __name__ == "__main__":
    if sys.version_info < (3, 6, 0):
        raise RuntimeError("This script requires Python 3.6+")

    # winbuild directory
    winbuild_dir = os.path.dirname(os.path.realpath(__file__))

    verbose = False
    disabled = ["openssl-legacy"]
    depends_dir = os.path.join(winbuild_dir, "cache")
    architecture = "x86"
    build_dir = os.path.join(winbuild_dir, "build")
    force_tk = False
    for arg in sys.argv[1:]:
        if arg == "-v":
            verbose = True
        elif arg.startswith("--depends="):
            depends_dir = arg[10:]
        elif arg.startswith("--architecture="):
            architecture = arg[15:]
        elif arg.startswith("--dir="):
            build_dir = arg[6:]
        elif arg.startswith("--openssl-legacy"):
            disabled.remove("openssl-legacy")
            disabled.append("openssl")
        elif arg.startswith("--with-tk"):
            force_tk = True
        else:
            raise ValueError("Unknown parameter: " + arg)

    # dependency cache directory
    os.makedirs(depends_dir, exist_ok=True)
    print("Caching dependencies in:", depends_dir)

    arch_prefs = architectures[architecture]
    print("Target Architecture:", architecture)

    msvs = find_msvs2015()
    if msvs is None:
        msvs = find_msvs()
        if not force_tk:
            # Tk 8.5.2 requires Win SDK <= 10.0.15063.0, which is not available by default
            disabled.extend(["tcl", "tk"])
    if msvs is None:
        raise RuntimeError(
            "Visual Studio not found. Please install Visual Studio 2015 or newer."
        )
    print("Found Visual Studio at:", msvs["vs_dir"])

    if "ntwin32.mak" not in disabled:
        header.append(cmd_append("INCLUDE", "{build_dir}\\" + deps["ntwin32.mak"]["dir"]))

    print("Using output directory:", build_dir)

    # build directory for *.h files
    inc_dir = os.path.join(build_dir, "include")
    # build directory for *.lib files
    lib_dir = os.path.join(build_dir, "lib")
    # build directory for *.bin files
    bin_dir = os.path.join(build_dir, "bin")

    tcltk_dir = os.path.join(build_dir, "tcltk")

    def rmtree_onerror(fn, path, excinfo):
        if excinfo[0] is PermissionError and excinfo[1].winerror == 5:
            os.chmod(path, stat.S_IWRITE)
            fn(path)
        elif excinfo[0] is FileNotFoundError:
            pass
        else:
            raise

    shutil.rmtree(build_dir, onerror=rmtree_onerror)
    for path in [build_dir, inc_dir, lib_dir, bin_dir, tcltk_dir]:
        os.makedirs(path)

    prefs = {
        # Target architecture
        "architecture": architecture,
        **arch_prefs,
        # Build paths
        "winbuild_dir": winbuild_dir,
        "build_dir": build_dir,
        "inc_dir": inc_dir,
        "lib_dir": lib_dir,
        "bin_dir": bin_dir,
        "tcltk_dir": tcltk_dir,
        # Compilers / Tools
        **msvs,
        "cmake": "cmake.exe",  # TODO find CMAKE automatically
        # TODO find NASM automatically
        # script header
        "header": sum([header, msvs["header"], ["@echo on"]], []),
    }

    print()

    build_dep_all()
