#!/usr/bin/env python3
"""Static checks on the shipped browser assets — stdlib only, no Node.

Run:  python3 site/tests/test_assets.py

There is no Node on this machine, so nothing ever parsed the JavaScript this
site serves. A single mismatched quote in `ops.js` — a string opened with `"`
and closed with `'` — took the **entire** ops console down: not one panel, the
whole file, so the login form silently stopped responding with no error on
screen. It was found by loading the page in a browser, which is not a thing that
happens on every edit.

This is the cheap guard. It is not a JavaScript parser and does not pretend to
be one; it tokenises far enough to know what is a string, a comment and a regex
literal, and then asserts the two things that hand-editing actually breaks:

  * no string is left unterminated at the end of a line, and
  * brackets balance across the file.

The checker's own acceptance test is that it reports **nothing** on the four
files as they stand — a checker that cries wolf on working code gets ignored,
which is worse than no checker.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # site/
JS_DIR = os.path.join(ROOT, "public", "assets", "js")
CSS_DIR = os.path.join(ROOT, "public", "assets", "css")

_fails = []


def check(cond, msg):
    if cond:
        print("  ok  " + msg)
    else:
        print("FAIL  " + msg)
        _fails.append(msg)


# `/` is a regex literal when the previous significant character cannot end an
# expression. Anything else and it is division. This is the one ambiguity that
# makes a naive quote-counter useless on real code (`.replace(/"/g, '""')`).
_PRE_REGEX = set("(,=:[!&|?{};+-*%~^<>") | {"\n"}


def scan(src):
    """Yield (line, kind, detail) for anything that looks broken."""
    problems = []
    depth = {"(": 0, "[": 0, "{": 0}
    closers = {")": "(", "]": "[", "}": "{"}
    i, n, line = 0, len(src), 1
    prev_sig = "\n"
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            prev_sig = "\n"
            continue
        if c in " \t\r":
            i += 1
            continue
        # comments
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                problems.append((line, "comment", "unterminated /* block comment"))
                break
            line += src.count("\n", i, j)
            i = j + 2
            continue
        # strings — a newline inside one (other than a template) is the bug
        if c in "\"'`":
            quote, j, start_line = c, i + 1, line
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "\n":
                    line += 1
                    if quote != "`":
                        problems.append((start_line, "string",
                                         "unterminated %s string" % quote))
                        break
                if src[j] == quote:
                    j += 1
                    break
                j += 1
            else:
                problems.append((start_line, "string", "unterminated %s string at EOF" % quote))
            i = j
            prev_sig = quote
            continue
        # regex literal vs division
        if c == "/" and prev_sig in _PRE_REGEX:
            j, cls = i + 1, False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    cls = True
                elif src[j] == "]":
                    cls = False
                elif src[j] == "/" and not cls:
                    j += 1
                    break
                j += 1
            i = j
            prev_sig = "/"
            continue
        if c in depth:
            depth[c] += 1
        elif c in closers:
            depth[closers[c]] -= 1
            if depth[closers[c]] < 0:
                problems.append((line, "bracket", "closing '%s' with nothing open" % c))
                depth[closers[c]] = 0
        prev_sig = c
        i += 1
    for br, d in depth.items():
        if d:
            problems.append((0, "bracket", "%d unclosed '%s'" % (d, br)))
    return problems


def test_js_parses():
    print("\n[js] every shipped script tokenises cleanly")
    files = sorted(f for f in os.listdir(JS_DIR) if f.endswith(".js"))
    check(len(files) >= 4, "found %d scripts to check: %s" % (len(files), ", ".join(files)))
    for f in files:
        src = open(os.path.join(JS_DIR, f), encoding="utf-8").read()
        probs = scan(src)
        check(not probs, "%s is clean%s" % (
            f, "" if not probs else " — " + "; ".join(
                "line %d: %s" % (l, d) for l, _k, d in probs[:4])))


def test_checker_catches_the_real_bug():
    """The regression that motivated this file, and a couple of its cousins.
    A checker nobody has seen fail is a checker nobody should trust."""
    print("\n[js] the checker actually catches what broke")
    cases = [
        ('var a = "opened with a double and closed with a single\';\n', "string"),
        ("var a = 'never closed at all;\n", "string"),
        ('function f() { return 1;\n', "bracket"),
        ('var a = [1, 2;\n', "bracket"),
    ]
    for src, kind in cases:
        probs = scan(src)
        check(any(k == kind for _l, k, _d in probs),
              "catches a %s error in %r" % (kind, src.strip()[:46]))
    # and does NOT fire on the constructs that fool a naive counter
    safe = [
        r'''var s = x.replace(/"/g, '""');''',
        r'''var s = "it's fine";''',
        r"""var s = 'say "hi"';""",
        r'''var r = /[/'"]/g, q = a / b;''',
        'var t = `a\nmultiline template`;',
        '// a comment with an unbalanced ( and a "quote\nvar ok = 1;',
        '/* block with a stray \' and { */\nvar ok = 2;',
    ]
    for src in safe:
        probs = scan(src)
        check(not probs, "no false alarm on %r" % src[:44])


def test_css_braces_balance():
    print("\n[css] stylesheets balance")
    for f in sorted(x for x in os.listdir(CSS_DIR) if x.endswith(".css")):
        src = open(os.path.join(CSS_DIR, f), encoding="utf-8").read()
        # strip comments and strings before counting
        out, i, n = [], 0, len(src)
        while i < n:
            if src.startswith("/*", i):
                j = src.find("*/", i + 2)
                i = n if j < 0 else j + 2
                continue
            if src[i] in "\"'":
                q, j = src[i], i + 1
                while j < n and src[j] != q:
                    j += 2 if src[j] == "\\" else 1
                i = j + 1
                continue
            out.append(src[i])
            i += 1
        body = "".join(out)
        check(body.count("{") == body.count("}"),
              "%s: %d { vs %d }" % (f, body.count("{"), body.count("}")))


def main():
    for fn in (test_js_parses, test_checker_catches_the_real_bug, test_css_braces_balance):
        fn()
    print("\n" + ("=" * 52))
    if _fails:
        print("FAILED: %d check(s)" % len(_fails))
        for m in _fails:
            print("  - " + m)
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
