# Picks the Python the checks and dev.sh run on. Source it (`. tests/python_env.sh`) after setting R (the repo folder);
# it sets PY to an absolute interpreter path and prints which one and why. Needs Python >= 3.10.
#
# Why: Apple's Command Line Tools Python 3.9 links the system /usr/lib/libsqlite3.dylib, which segfaults on macOS 26.4
# ("Python quit unexpectedly", GitHub #68). A python.org / uv / Homebrew Python carries its own sqlite.
#
# Order: $CHECK_PYTHON -> ~/combowatch/.venv/bin/python (if >= 3.10 and it already has every module; nothing is ever
# installed into it) -> $R/.venv-tests (git-ignored; built on first use from python3.13/3.12/3.11/3.10 found on PATH,
# Homebrew, pyenv or uv, then `pip install` + `playwright install chromium`) -> python3 on PATH if it is already 3.10+
# with every module (that's CI) -> plain python3 with a loud warning.
# Set CHECK_VENV_NO_CREATE=1 to skip building the venv. PY_MODS (default below) is the module list that must import.
PY_MODS="${PY_MODS:-requests, pyflakes, playwright}"

_pe_ok() {   # $1 = interpreter: runs, is >= 3.10, imports every module in PY_MODS
  [ -x "$1" ] && "$1" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null \
    && "$1" -c "import $PY_MODS" 2>/dev/null
}

_pe_base() {   # finds a base Python >= 3.10 to build the venv from; prints its path
  local c v
  for v in 3.13 3.12 3.11 3.10; do
    for c in "$(command -v python$v 2>/dev/null)" "/opt/homebrew/bin/python$v" "/usr/local/bin/python$v" \
             "$HOME"/.pyenv/versions/$v*/bin/python3 "$HOME"/.local/share/uv/python/cpython-$v*/bin/python3 \
             "/Library/Frameworks/Python.framework/Versions/$v/bin/python3"; do
      [ -n "$c" ] && [ -x "$c" ] && "$c" -c "import sys, venv" 2>/dev/null && { echo "$c"; return 0; }
    done
  done
  return 1
}

_pe_describe() {   # prints the interpreter, its versions and whether its sqlite is Apple's system library
  "$PY" - <<'P'
import sys, sqlite3
print("checks run on: %s (Python %s)" % (sys.executable, sys.version.split()[0]))
print("sqlite3 module: SQLite library %s" % sqlite3.sqlite_version)
P
  local ext
  ext=$("$PY" -c "import _sqlite3; print(_sqlite3.__file__)" 2>/dev/null)
  [ -f "$ext" ] || ext=$("$PY" -c "import sys, os; print(os.path.realpath(sys.executable))")
  if command -v otool >/dev/null 2>&1; then
    if otool -L "$ext" 2>/dev/null | grep -q "/usr/lib/libsqlite3.dylib"; then
      echo "sqlite: links /usr/lib/libsqlite3.dylib (the system copy that crashes on macOS 26.4: set CHECK_PYTHON to a newer Python)"
    else
      echo "sqlite: its own copy, not /usr/lib/libsqlite3.dylib"
    fi
  fi
}

pick_python() {
  local base venv="${CHECK_VENV:-$R/.venv-tests}" why=""
  PY=""
  if [ -n "$CHECK_PYTHON" ]; then
    PY="$(command -v "$CHECK_PYTHON" 2>/dev/null)"; why="CHECK_PYTHON"        # a bare name like python3.12 works too
    if [ -z "$PY" ] || [ ! -x "$PY" ]; then echo "CHECK_PYTHON=$CHECK_PYTHON is not an executable; ignoring it" >&2; PY=""
    elif ! _pe_ok "$PY"; then echo "WARNING: CHECK_PYTHON=$PY is older than 3.10 or lacks $PY_MODS; the run may fail or crash (see tests/README.md)" >&2; fi
  fi
  if [ -z "$PY" ] && _pe_ok "$HOME/combowatch/.venv/bin/python"; then PY="$HOME/combowatch/.venv/bin/python"; why="the watcher's own venv (has every module)"; fi
  if [ -z "$PY" ] && _pe_ok "$venv/bin/python"; then
    PY="$venv/bin/python"; why="$venv"
    case "$PY_MODS" in *playwright*)    # a quick no-op when the browser is there; fixes it after a playwright upgrade
      "$PY" -m playwright install chromium >/dev/null 2>&1 || echo "WARNING: 'playwright install chromium' failed (offline?); the page tests need the browser" >&2;; esac
  fi
  # CI (and anyone whose python3 on PATH is already new enough with every module): use it, no venv needed
  if [ -z "$PY" ] && _pe_ok "$(command -v python3 2>/dev/null)"; then PY="$(command -v python3)"; why="python3 on PATH (3.10+, has every module)"; fi
  if [ -z "$PY" ] && [ -z "$CHECK_VENV_NO_CREATE" ] && base=$(_pe_base); then
    echo "Setting up the test Python once in $venv (from $base) ..." >&2
    if "$base" -m venv "$venv" >&2 && "$venv/bin/python" -m pip install -q --upgrade pip >&2 \
       && "$venv/bin/python" -m pip install -q --disable-pip-version-check requests cryptography pyflakes ruff playwright >&2 \
       && { case "$PY_MODS" in *playwright*) "$venv/bin/python" -m playwright install chromium >&2;; esac; } \
       && _pe_ok "$venv/bin/python"; then
      PY="$venv/bin/python"; why="$venv (just built)"
    else
      echo "Could not build $venv. See tests/README.md for the manual setup." >&2
    fi
  fi
  if [ -z "$PY" ]; then
    PY="$(command -v python3)"; why="fallback"
    echo "WARNING: no Python >= 3.10 with $PY_MODS found; using $PY. Apple's 3.9 can crash on macOS 26.4 (sqlite). See tests/README.md." >&2
  fi
  echo "python: $PY ($why)"
  _pe_describe
}
pick_python
