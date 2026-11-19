import os
AUTOCAPITALIZE_NONE = 0
class View:
    def __init__(self, **kw):
        self.subviews = []; self.value = 0; self.text = ""; self.selected_index = 0
        self.frame = (0, 0, 375, 667); self.bounds = (0, 0, 375, 667)
        for k, v in kw.items(): setattr(self, k, v)
    def add_subview(self, v): self.subviews.append(v)
    def layout(self): pass
    hidden = False
    def close(self): pass
    def wait_modal(self): pass
    def present(self, style, **kw):
        if not isinstance(self, ScrollView):
            WebView.LOG.append("present"); self.on_screen = True; return
        WebView.LOG.append('settings-panel')
        for v in self.subviews:
            if isinstance(v, TextField) and getattr(v, "placeholder", "") == "Key ID": v.text = " fake-key-id "
            if isinstance(v, TextView): v.text = os.environ.get("PEM", "")
        segs = [v for v in self.subviews if isinstance(v, SegmentedControl)]
        segs[1].selected_index = 0
        title = os.environ.get("PANEL_BTN", "Build combos")
        b = [v for v in self.subviews if isinstance(v, Button) and v.title.startswith(title)][0]
        b.action(b)
class ScrollView(View): pass
class ButtonItem:
    def __init__(self, **kw):
        for k, v in kw.items(): setattr(self, k, v)
class Label(View): pass
class Slider(View): pass
class Switch(View): pass
class Button(View): pass
class TextField(View): pass
class TextView(View): pass
class SegmentedControl(View): pass
class _NoSubclass(type):
    def __new__(mcs, name, bases, ns):
        if any(getattr(b, "_final", False) for b in bases):
            raise TypeError("type '_ui.WebView' is not an acceptable base type")
        return super().__new__(mcs, name, bases, ns)


class WebView(View, metaclass=_NoSubclass):
    _final = True
    LOG = []
    def __init__(self, **kw):
        super().__init__(**kw); self.on_screen = False
    def present(self, style, **kw):
        self.on_screen = True; WebView.LOG.append("present")
    def close(self):
        self.on_screen = False; WebView.LOG.append("close")
    def evaluate_javascript(self, js):
        if js.startswith('go("') and self.delegate is not None:
            import threading as _t
            ch = js[4:-2]
            _t.Thread(target=self.delegate.webview_should_start_load, args=(self, "combo://settings/" + ch + "/", 0), daemon=True).start()
            WebView.LOG.append("go:" + ch); return
        if js == "typeof window.__load":
            return "function" if "window.__load" in getattr(self, "h", "") else "undefined"
        if js.startswith("window.__load("):
            import json as _j
            WebView.LOG.append("inplace"); self.load_html(_j.loads(js[len("window.__load("):-1])); return
        if js.startswith("window.__swap("):
            import json as _j
            body = _j.loads(js[len("window.__swap("):-1])
            head = getattr(self, "h", "<html><body>").split("<body>")[0]
            self.h = head + "<body>" + body + "</body></html>"
            WebView.LOG.append("swap")
            return
        if "setMsg(" in js:
            WebView.LOG.append("msg:" + js.split('setMsg(')[1].rstrip(')').strip('"'))
        else:
            WebView.LOG.append("js:" + js)
    def load_html(self, h):
        self.h = h
        # NAVCHECK: every real page (not the loading spinner) must have nav top + bottom
        if 'setMsg' not in h or '<section' in h:
            WebView.LOG.append('NAVOK' if "class='tabbar'" in h else 'NONAV:' + h[h.find('<h1>'):h.find('<h1>')+40])
        if "id='budgetline'" in h:
            WebView.LOG.append("settings-page")
            open("run/settings_view.html","w",encoding="utf-8").write(h)
            import json, urllib.parse
            btn = os.environ.get("PANEL_BTN", "Build combos")
            if btn == "Hold":
                return
            choice = ("update" if btn == "Update" else "mine" if btn.startswith("Show my") else "check" if btn.startswith(("Check", "Save key"))
                      else "show" if btn.startswith("Show last") else "build")
            vals = {"kalshi_key_id": "fake-key-id", "pem": os.environ.get("PEM", "")}
            if os.environ.get("LOCKBUF"):
                vals["picks"] = {}
            url = "combo://settings/" + choice + "/" + urllib.parse.quote(json.dumps(vals))
            self.delegate.webview_should_start_load(self, url, 0)
            return
        WebView.LASTANY = self
        if 'var BUILD="' in h: WebView.LAST = self
        if "setMsg" in h and "var BUILD" not in h and "<section" not in h:
            WebView.LOG.append("loading-page"); return
        WebView.LOG.append("page:" + ("results" if 'var BUILD="' in h else "other"))
        if 'var BUILD="' not in h:
            open("run/combos_view.html","w",encoding="utf-8").write(h); return
        open("run/viewed.html","w",encoding="utf-8").write(h)
        bid = h.split('var BUILD="')[1].split('"')[0]
        for u in os.environ.get("CLICKS","").split():
            self.delegate.webview_should_start_load(self, u.replace("BID", bid), 0)
