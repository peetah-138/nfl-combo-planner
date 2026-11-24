// ---------------- bet wording, shared by Live, Games, the game page and the combo page
/* The Mac gives every single bet and every combo leg four plain fields (display only, nothing here prices or sells):
   plain   what the bet is: "Over 144.5 total points", "Duke -6.5 (wins by 7+)", "Duke to win"
   matchup both teams: "Duke vs UNC"
   league  "CBB", "NFL", ...
   found   false when the teams could not be named (the matchup is then the ticker's own letters)
   These helpers read them and fall back to the older name/label/opp fields when a field is missing. */
function betPlain(x){return String((x&&(x.plain||x.label||x.name))||'');}
function betMatch(x){return String((x&&x.matchup)||'');}
/* "CBB · Duke vs UNC", plus a quiet "game not found" when the teams are only the ticker's letters (HTML, escaped) */
function betWhere(x){const m=betMatch(x);if(!m)return '';
 return `<span class="bwh">${x.league?esc(x.league)+' · ':''}${esc(m)}${x.found===false?' <i class="nf">game not found</i>':''}</span>`;}
/* the short form for a chip: spread/win keep the team and line, a total keeps over/under and its matchup */
function betChip(l){const p=betPlain(l);if(!l||!l.plain)return short(p);
 const base=p.replace(/\s*\(.*\)$/,'');
 return /total points$/.test(base)&&l.matchup?base.replace(/ total points$/,'')+' · '+l.matchup:base;}
