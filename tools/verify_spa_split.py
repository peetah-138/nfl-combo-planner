"""Proof that splitting the web app into watcher/spa/ changed nothing (GitHub #124).

Takes the SPA and LOGIN_HTML strings exactly as they were written inside watcher/combo_watcher.py at the last
commit before the split, assembles today's watcher/spa/ files with the watcher's own spa_assemble, and checks the
two are byte-for-byte identical (sha256 printed for both). Run from anywhere:

    python3 tools/verify_spa_split.py            # against the commit before the split
    python3 tools/verify_spa_split.py <commit>   # against another commit that still had the strings inline

It only proves the split itself: once someone edits a spa file the output differs on purpose, and that's fine
(the day-to-day test is tests/suite/t_spa_files.py, which checks the files, the manifest and the assembly).
"""
import ast, hashlib, importlib.util, os, subprocess, sys, tempfile

PRE_SPLIT = "1a7ea9b"            # origin/develop just before the split landed (after the #161 scroll hotfix)
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def old_strings(rev):
    src = subprocess.run(["git", "-C", R, "show", f"{rev}:watcher/combo_watcher.py"], capture_output=True,
                         text=True, check=True).stdout
    out = {}
    for n in ast.parse(src).body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and getattr(n.targets[0], "id", "") in ("SPA", "LOGIN_HTML") \
                and isinstance(n.value, ast.Constant):
            out[n.targets[0].id] = n.value.value
    if set(out) != {"SPA", "LOGIN_HTML"}:
        sys.exit(f"{rev} doesn't have SPA and LOGIN_HTML written inline")
    return out


def new_strings():
    os.environ["COMBOWATCH_HOME"] = tempfile.mkdtemp(prefix="spaverify")   # never the real ~/combowatch
    spec = importlib.util.spec_from_file_location("W", os.path.join(R, "watcher", "combo_watcher.py"))
    W = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(W)
    spa, login = W.spa_assemble()
    if W.SPA != spa or W.LOGIN_HTML != login:
        sys.exit("the module's SPA/LOGIN_HTML aren't what spa_assemble builds")
    return {"SPA": spa, "LOGIN_HTML": login}


def main():
    rev = sys.argv[1] if len(sys.argv) > 1 else PRE_SPLIT
    old, new = old_strings(rev), new_strings()
    bad = 0
    for k in ("SPA", "LOGIN_HTML"):
        a, b = old[k].encode("utf-8"), new[k].encode("utf-8")
        same = a == b
        bad += not same
        print(f"{k}: before {hashlib.sha256(a).hexdigest()} ({len(a)} bytes)")
        print(f"{' ' * len(k)}  after  {hashlib.sha256(b).hexdigest()} ({len(b)} bytes)  {'IDENTICAL' if same else 'DIFFERENT'}")
    print("BYTE-IDENTICAL" if not bad else "NOT IDENTICAL")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
