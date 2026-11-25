# A newer version reaches an open page (issue #150)

**Section:** Live page

- **A newer version reaches an open page (GitHub #150, display only).** The web app fills the running version into the page
  (`PAGE_VER`, `__CWVER__` in `SPA`, from `A.VERSION`; the page is `no-store`). Every live/games/game answer carries it
  (`fresh.ver`), and any view also asks the small read-only `GET /app/api/ver` (same sign-in, no app lock, no money) on the Mac's
  tick, every 12 s and when the app comes back (`verPoll`), so a phone parked on Build/Results/Settings notices too.
  `watcher/spa/update.js` (`verSeen`) compares it with `PAGE_VER`. Different + idle = reload by itself with a quiet fade, then an
  "Updated to <version>" toast; busy = a "New version ready: tap to refresh" pill (44 px, labelled, hidden = not focusable;
  `verTap` fires the light haptic inside the real tap, then reloads). **Busy (`verBusy`)** = a finger down, a scrub, a sheet or
  pushed page (game/combo/idea) open, `S.buying`/`S.pSend`/a pot move sending, **any POST still in flight** (`api()` counts them in
  `S.inflight`), a 15 s hold after a buy/go/hedge/single buy/pot move/panel approve/add/cancel/restart result (`S.verHold`, so its
  message can be read), `S.busy`, quote/buy entries (`S.qpend`/`S.bpend`) younger than 60 s, a flip, a combo quote or custom offer
  under 25 s old, a Live Buy-idea quote (`S.ideaq`) under 25 s old, a visible bad or "check" toast, a field being typed in, an armed
  Approve/Add. Idle also needs 1.5 s since the last touch, scroll or key. The "already reloaded for this version" note (5 min) is kept
  in sessionStorage and localStorage; if neither can be written, or it is there, only the pill shows (no loop). An unreadable
  version does nothing. The service worker has no fetch handler (caches nothing) and carries `WATCHER_VERSION`, so every release
  changes it. Settings > The Mac shows "Up to date" with the app version, or "A newer version is ready" with a Reload button.
  Tests: `t_newversion`, `test_newversion`. Follow-ups: #213, #214.
