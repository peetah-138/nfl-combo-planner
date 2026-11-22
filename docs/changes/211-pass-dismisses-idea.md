# Pass after Get price dismisses the idea (#211)

On a Live Buy idea card (and its detail page), **Pass** after Get price now closes the idea like the X does: `ideaPass`
(`watcher/spa/ideas.js`) drops the quote and its countdown (`S.ideaTid`), then goes through the same dismiss path
(`ideaX` / `ideaNotNowSheet`): the card slides out, the Mac remembers it in `combo_idea_dismiss.json`, Undo toast.
Pass is disabled while a buy is on its way (`S.ibuy[id]`, set around `buyIdea` / `buySingle`). Display only: no money
path changed. Test: `test_ideas2.py`.
