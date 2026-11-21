"""The watcher's text as the source-reading tests expect it: combo_watcher.py followed by the web app's files
(the spa folder next to it, in MANIFEST.json order). Before GitHub #124 the web app was written inside the
watcher file, so tests that look for a piece of the page's code in "the watcher's source" read both."""
import json, os


def watcher_text(path="wtest/combo_watcher.py"):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    spa = os.path.join(os.path.dirname(os.path.abspath(path)), "spa")
    with open(os.path.join(spa, "MANIFEST.json"), encoding="utf-8") as f:
        m = json.load(f)
    for name in [m["shell"], *m["css"], *m["js"], m["login"]]:
        with open(os.path.join(spa, name), encoding="utf-8") as f:
            src += "\n" + f.read()
    return src
