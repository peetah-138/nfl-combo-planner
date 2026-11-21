# Offline guard for the engine tests (GitHub #189). run_checks.sh puts this folder on PYTHONPATH for them, so Python
# loads it at start-up. Any HTTP request through `requests` to a host other than this machine is refused here, before
# anything is sent, with the same ConnectionError a dead network gives (what the engine already handles).
# Why: several tests reached ESPN's real injury report (news_gap -> injury_note). When a team in a test had fresh
# injury news, a check failed in CI only, at some hours of the day (t_live_panel "fresh score and a good price: bought").
# Local runs behind a proxy never saw it. With this guard CI and every machine see the same thing: no outside data.
import os
import sys

_LOCAL = {"127.0.0.1", "localhost", "::1", ""}


def _install():
    try:
        import requests.adapters as _ra
        from requests.exceptions import ConnectionError as _CE
        from urllib.parse import urlsplit
    except Exception:            # no requests here: nothing to guard
        return
    _send = _ra.HTTPAdapter.send

    def send(self, request, *a, **k):
        host = (urlsplit(request.url).hostname or "").lower()
        if host not in _LOCAL:
            log = os.environ.get("CHECK_NETLOG")
            if log:
                try:
                    with open(log, "a") as f:
                        f.write(f"{os.path.basename(sys.argv[0] if sys.argv else '?')} {host}\n")
                except OSError:
                    pass
            raise _CE(f"offline in tests: {host} is not reachable (tests/suite/netguard)", request=request)
        return _send(self, request, *a, **k)

    _ra.HTTPAdapter.send = send


_install()
