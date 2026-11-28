# CHECK: group=engine
# Release 148 delight nits (GitHub #664), display only: the games card names its teams for a screen reader, a finished
# game's empty line takes no room, the settings css uses the app's own --mute colour, and the Back to start sheet shows the
# frozen sentence only when the tap can really go ahead, in the app's own --no red. Reads the web app's files as text.
import os
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))
SPA = os.path.join("wtest", "spa")
rd = lambda f: open(os.path.join(SPA, f), encoding="utf-8").read()
games, gcss, scss, fa = rd("games.js"), rd("games.css"), rd("settings.css"), rd("fullauto.js")
ok("games card: aria-label is 'team vs opponent, open game' on the role=button card",
   """role="button" tabindex="0" aria-label="${esc((g.kind==='total'&&g.matchup?g.matchup:g.name)+(oppNm?' vs '+oppNm:''))}, open game" onclick=""" in games)
ok("finished game card: an empty .gl.none takes no room (display:none), live ones keep visibility:hidden",
   ".gc.done .gl.none{display:none}" in gcss and ".gc .gl.none{visibility:hidden}" in gcss)
ok("settings.css .fadw uses --mute, never the undefined --muted", ".fadw{color:var(--mute,inherit)}" in scss and ".fadw{color:var(--muted" not in scss)
ok("reset sheet: the frozen sentence needs one.frozen && one.reset_ok", "${one.frozen&&one.reset_ok?' It is frozen" in fa)
ok("reset sheet: the refusal text uses the app's --no red (--red is undefined)", "color:var(--no,inherit)" in fa and "--red" not in fa)
