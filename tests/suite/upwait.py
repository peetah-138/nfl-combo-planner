# Page tests start the web app in a thread and then open it. They used to wait a fixed 3 s, but the web app loads
# the whole engine before it listens, and on a busy runner that can take longer: the first page.goto then hit a
# closed port ("connection refused", a traceback, a failed test). wait_up() waits for the port itself (up to `secs`),
# and never less than the old 3 s, so nothing that relied on those 3 s changes.
import os, socket, time


def wait_up(secs=90, at_least=3.0, port=None):
    port = int(port or os.environ.get("CW_WEBAPP_PORT", "8766"))
    t0 = time.time()
    while time.time() - t0 < secs:
        s = socket.socket()
        s.settimeout(1)
        try:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        finally:
            s.close()
        time.sleep(.1)
    else:
        print("PROBLEMS: the web app never started listening on port %d within %ds" % (port, secs), flush=True)
    time.sleep(max(0.0, at_least - (time.time() - t0)))
