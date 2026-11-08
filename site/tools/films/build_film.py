#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build one film (a HyperFrames project under site/tools/films/<name>/).

    cd site/tools/films
    ../../../../"Enevie lp"/outils/.venv/bin/python build_film.py <name> --new    # once, from _template
    …write <name>/index.html (+ sfx.py)…
    <venv> build_film.py <name>              # voice -> assets/timing.js + the soundtrack
    cd <name> && npx hyperframes check
    npx hyperframes snapshot --at 0.3,2,4.5  # READ the contact sheet before rendering
    cd .. && <venv> build_film.py <name> --render

Ported from the Enevie chain (outils/hyperframes/pubs10/build_pub.py), minus the
3D library and the multi-series output. What it does, in order: one ElevenLabs
take for the whole film with per-word timings -> assets/timing.js -> the film's
length copied into index.html -> soundtrack (voice + music + the cues in
<name>/sfx.py) -> optionally the MP4.

⚠ THE SPOKEN PRICES ARE CHECKED AGAINST pricing.py. A re-price fails the build
instead of shipping a film that says a figure the checkout does not charge; the
voice spells numbers out, so there is no way to patch that automatically.
"""
import importlib.util, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))           # site/tools/films
TOOLS = os.path.dirname(HERE)
SITE = os.path.dirname(TOOLS)
sys.path.insert(0, HERE); sys.path.insert(0, TOOLS); sys.path.insert(0, os.path.join(SITE, 'src'))

import voice                                                # noqa: E402
from voice import word_t                                    # noqa: E402
from scripts import FILMS                                   # noqa: E402
import pricing as PR                                        # noqa: E402
import data as D                                            # noqa: E402
import imageio_ffmpeg                                       # noqa: E402

OUT_DIR = os.path.join(SITE, 'assets-out', 'videos')
BUILD = os.path.join(HERE, 'build')
FF = imageio_ffmpeg.get_ffmpeg_exe()
GAME = next(g for g in D.GAMES if 'League' in g['name'])['name']
# The renderer shells out to ffmpeg/ffprobe and will not start without them on
# PATH. They are the npm static builds under films/bin, installed here rather
# than borrowed from the Enevie folder: a symlink across projects breaks the day
# that folder moves.
BIN = os.path.join(HERE, 'bin')
ENV = dict(os.environ, PATH=BIN + os.pathsep + os.environ.get('PATH', ''),
           DO_NOT_TRACK='1', HYPERFRAMES_NO_TELEMETRY='1')
FFPROBE = os.path.join(BIN, 'ffprobe')

# Spoken forms of the figures the films use. A price the engine returns but this
# table cannot spell is a build error rather than a silent pass.
WORDS = {3: 'three', 4: 'four', 10: 'ten', 16: 'sixteen', 21: 'twenty-one', 24: 'twenty-four',
         25: 'twenty-five', 26: 'twenty-six', 34: 'thirty-four', 36: 'thirty-six',
         39: 'thirty-nine', 48: 'forty-eight', 56: 'fifty-six', 57: 'fifty-seven',
         62: 'sixty-two', 91: 'ninety-one'}


def price(frm, to, mode='Solo'):
    q = PR.quote({'game': GAME, 'service': 'division', 'from': frm, 'to': to, 'mode': mode})
    assert not q['invalid'], (frm, to)
    return int(round(q['total']))


def resolve(spec):
    """What the site charges today for what a line claims.

    ('division', from, to[, mode]) · ('wins', rank, n) · ('placements', rank, n)
    · ('division', 'FLOOR', None) is the cheapest single division on the ladder.

    A DICT is passed straight to `pricing.quote()`, which is how a film quotes a
    ladder other than League's — the hook names Valorant, and a Valorant price
    taken off League's table would be the one thing this check exists to stop."""
    if isinstance(spec, dict):
        q = PR.quote(dict({'service': 'division', 'mode': 'Solo'}, **spec))
        assert not q['invalid'], spec
        return int(round(q['total']))
    kind = spec[0]
    lad = next(g for g in D.GAMES if 'League' in g['name'])['ladder']
    if kind == 'division':
        if spec[1] == 'FLOOR':
            return price(lad[0], lad[1])
        return price(spec[1], spec[2], spec[3] if len(spec) > 3 else 'Solo')
    rank, n = spec[1], spec[2]
    q = PR.quote({'game': GAME, 'service': kind, 'from': rank, 'to': rank, 'mode': 'Solo', kind: n})
    assert not q['invalid'], spec
    return int(round(q['total']))


def check_prices(F):
    """Every price the take SAYS has to be the price the site charges today.

    The voice spells numbers out, so a re-price cannot be patched in the film —
    the line is rewritten and the take re-recorded. Failing the build is the only
    honest outcome, and it is cheap: the take is cached, so only the film whose
    line changed pays for a new one."""
    text = ' '.join(F['lines']).lower()
    for said, spec in F.get('prices', []):
        now = resolve(spec)
        want = WORDS.get(now)
        if said not in text:
            raise SystemExit('scripts.py claims the take says "%s" and it does not. '
                             'Keep `prices` in step with `lines`.' % said)
        if want is None:
            raise SystemExit('%s now costs $%d and WORDS cannot spell it. Add it.' % (spec, now))
        if said != want + ' dollars':
            raise SystemExit('%s now costs $%d ("%s dollars"), but the take says "%s".\n'
                             'Rewrite the line in scripts.py and re-record — the voice '
                             'cannot be patched.' % (spec, now, want, said))
    # And nothing may quote a price it did not declare.
    import re as _re
    for m in _re.finditer(r'\b([a-z-]+) dollars\b', text):
        if not any(m.group(0) == said for said, _ in F.get('prices', [])):
            raise SystemExit('the take says "%s" but scripts.py does not declare it in '
                             '`prices`, so nothing checks it against pricing.py.' % m.group(0))


def sync_assets(proj):
    """Copy anything in _template/assets the project is missing — the per-film
    copies are not in git (five copies of a font and GSAP is 10 MB), so a fresh
    clone has an index.html with nothing to draw with until this runs."""
    src = os.path.join(HERE, '_template', 'assets')
    dst = os.path.join(proj, 'assets')
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        out = os.path.join(dst, rel) if rel != '.' else dst
        os.makedirs(out, exist_ok=True)
        for f in files:
            if not os.path.exists(os.path.join(out, f)):
                shutil.copy(os.path.join(root, f), os.path.join(out, f))


def load(path, name):
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    name = sys.argv[1]
    F = FILMS[name]
    proj = os.path.join(HERE, name)

    if '--new' in sys.argv and not os.path.exists(proj):
        shutil.copytree(os.path.join(HERE, '_template'), proj)
        html = open(os.path.join(proj, 'index.html'), encoding='utf-8').read().replace('__NAME__', F['title'])
        open(os.path.join(proj, 'index.html'), 'w', encoding='utf-8').write(html)
        json.dump({'id': 'esb-%s' % name, 'name': 'esb-%s' % name},
                  open(os.path.join(proj, 'meta.json'), 'w'), indent=2)
        print('project created ->', proj)

    # Keep the project's assets in step with _template. They are NOT in git — five
    # copies of a font, a logo and GSAP is 10 MB of duplication — so a fresh clone
    # has an index.html with nothing to draw with until this runs.
    sync_assets(proj)

    check_prices(F)
    cfg = json.load(open(os.path.join(proj, 'config.json'))) if os.path.exists(os.path.join(proj, 'config.json')) else {}
    end_hold = cfg.get('end_hold', 2.7)          # the hold after the last line, Enevie's validated figure

    vo, words, lines = voice.voice(F['lines'], os.path.join(BUILD, 'voice-' + name), os.path.join(BUILD, name))
    total = round(lines[-1]['end'] + end_hold, 2)
    W = lambda w, after=0.0, end=False: word_t(words, w, after, end)   # noqa: E731
    L = [l['start'] for l in lines]

    os.makedirs(os.path.join(proj, 'assets'), exist_ok=True)
    with open(os.path.join(proj, 'assets', 'timing.js'), 'w', encoding='utf-8') as f:
        f.write('// Written by build_film.py: the voice-over timing (seconds, take time). Do not edit.\nwindow.VO = '
                + json.dumps({'total': total, 'speed': 1.0, 'lines': lines, 'words': words}, ensure_ascii=False) + ';\n')

    p = os.path.join(proj, 'index.html')
    html = open(p, encoding='utf-8').read()
    html = re.sub(r'(data-duration=")[\d.]+("[^>]*data-film)', r'\g<1>%s\2' % total, html)
    html = re.sub(r'(id="bande-son"[^>]*data-duration=")[\d.]+', r'\g<1>%s' % total, html)
    open(p, 'w', encoding='utf-8').write(html)

    sfx = load(os.path.join(proj, 'sfx.py'), 'sfx_%s' % name.replace('-', '_'))
    cues = sfx.cues(W=W, L=L, lines=lines, total=total) if sfx else [('riser', 0.0, 0.3)]
    voice.mix(vo, total, cues, os.path.join(proj, 'assets', 'bande-son.wav'),
              mood=cfg.get('mood', F['mood']), music_gain=cfg.get('music_gain', 0.45))
    print('%s: %.2f s, %d cues, music "%s"' % (name, total, len(cues), cfg.get('mood', F['mood'])))

    if '--render' in sys.argv:
        os.makedirs(OUT_DIR, exist_ok=True)
        out = os.path.join(OUT_DIR, '%d-%s.mp4' % (F['n'], name))
        r = subprocess.run(['caffeinate', '-i', 'npx', 'hyperframes', 'render',
                            '--output', out, '--fps', '30', '--quality', 'high'], cwd=proj, env=ENV)
        if r.returncode != 0:
            raise SystemExit('render failed (%d)' % r.returncode)
        # Enevie's own checks: real duration, black frames, and a contact sheet to READ.
        dur = subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
                              '-of', 'csv=p=0', out], capture_output=True, text=True).stdout.strip()
        black = subprocess.run([FF, '-i', out, '-vf', 'blackdetect=d=0.1:pix_th=0.05', '-an', '-f', 'null', '-'],
                               capture_output=True, text=True).stderr.count('black_start')
        sheet = os.path.join(BUILD, '%s-sheet.jpg' % name)
        subprocess.run([FF, '-v', 'error', '-y', '-i', out, '-vf', 'fps=1/2,scale=216:-1,tile=8x2',
                        '-frames:v', '1', sheet], check=True)
        print('-> %s\n   %s s, black frames: %d, sheet: %s' % (out, dur, black, sheet))


if __name__ == '__main__':
    main()
