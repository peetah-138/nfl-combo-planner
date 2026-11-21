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


def go_and_hold(pg, view, secs=60):
    """Opens `view`, waits until the page's own load for it has finished (none still in flight), then stops the
    page refreshing itself, so data a test draws in next is never overwritten by a load that was still on its way
    (a fixed sleep before `window.load=async()=>{}` lost that race on a slow runner). Returns False on a timeout."""
    pg.wait_for_function("typeof window.load==='function'&&typeof S==='object'", timeout=secs * 1000)
    pg.evaluate("""(()=>{if(window.__ldw){window.load=window.__ldw;return;}const L=window.load;window.__loads=0;window.__done=0;
      window.load=window.__ldw=async(...a)=>{window.__loads++;try{return await L(...a)}finally{window.__loads--;window.__done++}};})()""")
    n0 = pg.evaluate("window.__done")
    pg.evaluate("v=>go(v)", view)
    t0, ok = time.time(), False
    while time.time() - t0 < secs:
        try:
            if pg.evaluate("n=>window.__done>n&&window.__loads===0&&S.view===%s" % repr(view), n0):
                ok = True
                break
        except Exception:
            pass
        time.sleep(.1)
    if not ok:
        print("PROBLEMS: the %s page never finished loading" % view, flush=True)
    pg.evaluate("window.load=async()=>{}")
    return ok
