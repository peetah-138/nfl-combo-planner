"""The engine tests' fake-network guard (GitHub #189). run_checks.sh puts this folder first on PYTHONPATH for every
engine test (t_*.py), so Python imports it at start-up, in the test and in any Python it starts.

A test must never depend on the real internet: ESPN's injury report, scores or odds change by the hour, so a test that
reads them passes or fails with the time of day (t_live_panel did, until it stubbed injury_note). This guard refuses
every connection to anything but this machine, at the socket level (requests, urllib and http.client all end up here),
and makes the test FAIL with the host it tried, instead of passing or failing on whatever the real service answered.

Allowed: localhost and 127.x / ::1 (the fakes' own servers, the test web apps), Unix sockets, and the reserved names
*.invalid / *.test / *.example (the harness points ntfy at ntfy.invalid on purpose; those are refused quietly, as
an offline machine would). Everything else is refused with an OSError (what an offline machine raises) and reported
once as a FAIL line, which run_checks.sh counts. Set NETGUARD_OFF=1 to switch it off while debugging."""
import importlib.machinery
import importlib.util
import ipaddress
import os
import socket
import sys

BLOCKED = []
QUIET = (".invalid", ".test", ".example", ".localhost")


def _local(host):
    h = (host or "").strip("[]").lower().rstrip(".")
    if h in ("", "localhost") or h.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(h.split("%")[0])
    except ValueError:
        return False
    return ip.is_loopback or ip.is_unspecified


def _caller():
    """Which of our own functions asked (the innermost frame outside the standard library and site-packages)."""
    f, out = sys._getframe(2), []
    while f and len(out) < 3:
        fn = f.f_code.co_filename
        if not (fn.startswith(sys.prefix) or fn.startswith(sys.base_prefix) or "site-packages" in fn or fn == __file__):
            out.append("%s:%s" % (os.path.basename(fn), f.f_code.co_name))
        f = f.f_back
    return " < ".join(out) or "?"


def _refuse(host, port):
    h = str(host or "").lower().rstrip(".")
    if not h.endswith(QUIET):
        what = "%s:%s" % (host, port)
        if what not in BLOCKED:
            BLOCKED.append(what)
            # a FAIL line at once (run_checks.sh counts it), so even a test that ends with os._exit is caught
            print("FAIL hermetic: the test tried to reach the real internet: %s from %s (stub it)" % (what, _caller()), flush=True)
    raise socket.gaierror(socket.EAI_NONAME, "netguard: no real network in tests (%s)" % h)


def install():
    real_gai, real_connect, real_connect_ex = socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex

    def getaddrinfo(host, port, *a, **k):
        if host is not None and not _local(host if isinstance(host, str) else host.decode("ascii", "replace")):
            _refuse(host, port)
        return real_gai(host, port, *a, **k)

    def _check(sock, addr):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and isinstance(addr, tuple) and not _local(str(addr[0])):
            _refuse(addr[0], addr[1] if len(addr) > 1 else "")

    def connect(self, addr):
        _check(self, addr)
        return real_connect(self, addr)

    def connect_ex(self, addr):
        _check(self, addr)
        return real_connect_ex(self, addr)

    socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex = getaddrinfo, connect, connect_ex


def _chain():
    """Run the sitecustomize this folder hides (a Python install may ship its own), so nothing else changes."""
    here = os.path.dirname(os.path.abspath(__file__))
    rest = [p for p in sys.path if p and os.path.abspath(p) != here]
    spec = importlib.machinery.PathFinder.find_spec("sitecustomize", rest)
    if spec and spec.loader and spec.origin and os.path.abspath(spec.origin) != os.path.abspath(__file__):
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)


if os.environ.get("NETGUARD_OFF") != "1":
    install()
try:
    _chain()
except Exception as e:  # another install's sitecustomize failing must not hide the guard
    sys.stderr.write("netguard: the next sitecustomize failed: %r\n" % (e,))
