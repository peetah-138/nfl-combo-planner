# Settings scrolls on an iPhone again (issue #281)

**Section:** Look and feel (the makeover), "Press feedback + haptic on every control" (the #151 exception)

Pete (iOS 27.2.1, Home Screen app): swiping up or down on Settings was really bad. Cause: the Settings folds (#212,
shipped in 2026.11.21.131) made every section header a full-width 56pt button (`.sfold`, about 360x56 at 390 wide),
and the Mac line (`.smac`, 362x44) is one too. Real buttons count as compact in `hswBig` unless taller than 64px, so
each got a see-through iOS switch (method N). With most sections folded (only Money and The Mac start open) those
headers stack up: measured at 390x844 in WebKit and Chromium, 55-65% of a screen of Settings was see-through switch
(Live and Build: at most ~24%, Results ~15%), and a switch under the finger can stop iOS scrolling (#151). Ruled out
by measurement: no re-render while scrolling (Settings isn't in the refresh loop; 2 DOM mutations over a full scroll),
no long tasks (p95 frame ~18 ms in both engines), the tab swipe and pull-to-refresh skip inputs and only act on a
mostly sideways / at-the-top drag, native switches (`.tg`) and sliders cover 1-6% of a screen, no `touch-action`,
`will-change` or blur layer specific to Settings.

Fix: `.sfold` and `.smac` carry `data-hsw="0"` (already in `HSWNO`), so they get no switch: scrolling first, as in
#151. They keep press feedback and their tap (fold/unfold, jump to The Mac); they no longer tick on iOS 27. Every small
Settings control (chips, choice and stepper buttons, the Mac's buttons) keeps its switch. Settings at 390x844 is now at
most ~11% switch (the league chips). UI only: no setting, save, money, buy/sell, Pause or cap code touched.

Tests: `test_settings_scroll.py` (new; fails on the old code): folded and unfolded, a drag from every kind of Settings
line (section header, Mac line, switch row, slider row, Let it ride, choice row, moved-to-Build row, combo-mix row, the
Mac's facts and buttons) starts on the line itself, never on a switch or slider (WebKit and Chromium), and in Chromium
(real touch events through CDP) scrolls ~the dragged 216px and changes no setting or fold; no screen of Settings is
over 25% switch; header and Mac line still work on a tap; small controls keep their switches. `test_motion.py`'s
iPhone audit counts `[data-hsw="0"]` controls as exempt scroll surfaces.

ROADMAP: none
