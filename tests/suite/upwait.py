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


# Counts the page's requests in flight from before its own script runs (so the boot load counts too). Install it
# with pg.add_init_script(upwait.COUNT_FETCHES) before pg.goto; go_and_hold() then waits for them as well.
COUNT_FETCHES = """(()=>{const F=window.fetch;window.__fx=0;
  window.fetch=function(...a){window.__fx++;let p;try{p=F.apply(this,a)}catch(e){window.__fx--;throw e}
    return p.then(r=>{const j=r.json.bind(r),t=r.text.bind(r),end=x=>{window.__fx--;return x};let done=false;
      const once=f=>(...b)=>f(...b).then(x=>{if(!done){done=true;end()}return x},e=>{if(!done){done=true;end()}throw e});
      r.json=once(j);r.text=once(t);setTimeout(()=>{if(!done){done=true;end()}},15000);return r},
     e=>{window.__fx--;throw e});};})()"""


def quiet(pg, js="true", secs=60, still=0.5):
    """Waits until `js` holds, no counted request is in flight and no counted load() is running, steadily for
    `still` seconds (a request's body is read in a later step, so one instant of quiet isn't enough)."""
    cond = "(%s)&&!(window.__fx>0)&&!(window.__loads>0)" % js
    t0, since = time.time(), None
    while time.time() - t0 < secs:
        try:
            okay = pg.evaluate(cond)
        except Exception:
            okay = False
        if okay:
            since = since or time.time()
            if time.time() - since >= still:
                return True
        else:
            since = None
        time.sleep(.05)
    return False


def go_and_hold(pg, view, secs=60):
    """Opens `view`, waits until the page's own loads have finished (the boot load included, when COUNT_FETCHES is
    installed), then stops the page refreshing itself, so data a test draws in next is never overwritten by a load
    still on its way (a fixed sleep before `window.load=async()=>{}` lost that race on a slow runner)."""
    pg.wait_for_function("typeof window.load==='function'&&typeof S==='object'", timeout=secs * 1000)
    pg.evaluate("""(()=>{if(window.__ldw){window.load=window.__ldw;return;}const L=window.load;window.__loads=0;window.__done=0;
      window.load=window.__ldw=async(...a)=>{window.__loads++;try{return await L(...a)}finally{window.__loads--;window.__done++}};})()""")
    n0 = pg.evaluate("window.__done")
    pg.evaluate("v=>go(v)", view)
    ok = quiet(pg, "window.__done>%d&&S.view===%s" % (n0, repr(view)), secs)
    if not ok:
        print("PROBLEMS: the %s page never finished loading" % view, flush=True)
    pg.evaluate("window.load=async()=>{}")
    return ok
