# CHECK: group=engine
# The web app's one money format (polish foundation): fmtMoney / fmtSigned in common.js, between the FMT-BEGIN and
# FMT-END markers. Rule: under $100 always cents ($9.40, $12.00); $100 and over whole dollars with commas. Display only.
# Runs the real code in node (the slice is pure, no page needed) and checks exact strings.
import json, os, subprocess
ok = lambda n, c, *a: print(("PASS " if c else "FAIL ") + n, *(a if not c else ()))
SPA = os.path.join(os.path.abspath("wtest"), "spa", "common.js")
src = open(SPA, encoding="utf-8").read()
ok("the FMT markers exist once each", src.count("FMT-BEGIN") == 1 and src.count("FMT-END") == 1)
code = src.split("FMT-BEGIN", 1)[1].split("FMT-END", 1)[0]
code = code.split("\n", 1)[1] if "\n" in code else code   # drop the rest of the marker's own comment line
code = code[code.index("const fmtMoney"):code.rindex("/*")]
CASES = [("fmtMoney", 9.4, "$9.40"), ("fmtMoney", 9, "$9.00"), ("fmtMoney", 12, "$12.00"), ("fmtMoney", 54.3, "$54.30"),
         ("fmtMoney", 0, "$0.00"), ("fmtMoney", 0.5, "$0.50"), ("fmtMoney", 99.99, "$99.99"), ("fmtMoney", 99.996, "$100"),
         ("fmtMoney", 100, "$100"), ("fmtMoney", 154.4, "$154"), ("fmtMoney", 1250, "$1,250"), ("fmtMoney", 980, "$980"),
         ("fmtMoney", 1234567.5, "$1,234,568"), ("fmtMoney", -9.4, "−$9.40"), ("fmtMoney", -250, "−$250"),
         ("fmtMoney", -0.004, "$0.00"), ("fmtMoney", None, "—"), ("fmtMoney", "x", "—"), ("fmtMoney", "5", "$5.00"),
         ("fmtSigned", 9.4, "+$9.40"), ("fmtSigned", -9.4, "−$9.40"), ("fmtSigned", 0, "+$0.00"), ("fmtSigned", -0.004, "+$0.00"),
         ("fmtSigned", 12, "+$12.00"), ("fmtSigned", -130.2, "−$130"), ("fmtSigned", 1500, "+$1,500"), ("fmtSigned", None, "—")]
js = code + "\nconst C=%s;console.log(JSON.stringify(C.map(([f,v])=>({fmtMoney,fmtSigned}[f])(v))));" % json.dumps([[f, v] for f, v, _ in CASES])
r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
ok("the formatter runs in node", r.returncode == 0, r.stderr[:300])
got = json.loads(r.stdout) if r.returncode == 0 else []
for (f, v, want), g in zip(CASES, got):
    ok("%s(%r) = %s" % (f, v, want), g == want, "got", g)
ok("every case ran", len(got) == len(CASES))
