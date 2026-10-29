# -*- coding: utf-8 -*-
"""The ad-video engine: scenes drawn frame by frame (PIL), ElevenLabs voice-over,
synth music, sound effects, ffmpeg montage -> 1080x1920 MP4.

Ported from the Enevie films (`Enevie lp/outils/video_lib.py`) with the solar
drawing cut out and the brand swapped to Ashfall. The engine itself — timing,
voice, music, ducking, encode — is unchanged, so a fix there is worth carrying
back to the other project.

A scene's LENGTH IS ITS VOICE LINE: `render()` measures the rendered speech and
gives the scene `vo_delay + speech + hold` seconds. Write the line, not a
duration. `min_dur` is only a floor for a scene that has no voice.

Environment:
    ELEVEN_VOICE_ID   voice to speak with (default: Will, the owner's pick)
    ELEVEN_LANG       language code sent to the model (default: en)
    ELEVEN_MODEL      default eleven_multilingual_v2
    NO_VO=1           render the pictures with music only, spends no credits

The key is read from ~/.elevenlabs_key and never printed. Every line is cached
under tools/.cache/tts by a hash of (voice, model, settings, text), so a re-render
after a visual change costs nothing.
"""
import math, os, subprocess, sys, wave, hashlib
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))          # site/tools
ROOT = os.path.dirname(HERE)                                # site
sys.path.insert(0, os.path.join(ROOT, 'src'))
import data as D                                            # noqa: E402  tier colours, prices, copy

FONT = os.path.join(HERE, 'fonts', 'Montserrat.ttf')
# Already exported for Google Ads, transparent and drawn for a dark ground.
LOGO = os.path.join(ROOT, 'assets-out', 'google-ads', 'logo-4x1-1200x300-transparent-dark-bg-only.png')
CACHE = os.path.join(HERE, '.cache', 'tts')
W, H, FPS, SR = 1080, 1920, 30, 44100

# Ashfall, the site's own tokens (site/public/assets/css/ashfall.css). A video
# that quotes a price has to look like the page that charges it.
BG = (6, 6, 10); BG2 = (8, 8, 13); BG3 = (10, 10, 17); PANEL = (14, 14, 22)
INK = (244, 241, 236)          # --text, the ink on this brand is LIGHT
TEXT2 = (168, 165, 178); TEXT3 = (139, 139, 153)
EMBER = (255, 74, 31); EMBER_LIT = (255, 106, 61); EMBER_WARM = (255, 138, 76)
AMBER = (255, 184, 76); AMBER_PALE = (255, 214, 140)
GREEN = (52, 199, 123); GREEN_D = (28, 150, 92)     # free / included / live
RED = (224, 87, 79); SKY = (95, 147, 222)
WHITE = (255, 255, 255); HAIR = (38, 38, 50); GREY = (120, 120, 134)
YELLOW = AMBER; MINT = PANEL; MINT2 = HAIR; ORANGE = EMBER; SUN = AMBER
TERRA = EMBER_WARM; CREAM = INK; SKY_BG = (18, 26, 42); GREEN_BG = (12, 30, 22)


# ——— Animation ———
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def prog(t, start, dur): return clamp((t - start) / dur) if dur > 0 else float(t >= start)
def ease_out(x): return 1 - (1 - x) ** 3
def ease_io(x): return x * x * (3 - 2 * x)
def back(x, s=1.70158):
    x -= 1
    return x * x * ((s + 1) * x + s) + 1
def lerp(a, b, k): return a + (b - a) * k
def lerp_pt(p, q, k): return (lerp(p[0], q[0], k), lerp(p[1], q[1], k))
def lerp_col(c1, c2, k): return tuple(round(lerp(a, b, k)) for a, b in zip(c1, c2))
def pop(p): return back(p) if p > 0 else 0


# ——— Texte et sprites ———
@lru_cache(None)
def font(size, weight):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_axes([weight])
    return f

@lru_cache(None)
def text(s, size, weight=800, color=INK):
    f = font(size, weight)
    asc, desc = f.getmetrics()
    im = Image.new('RGBA', (math.ceil(f.getlength(s)) + 8, asc + desc + 8), color + (0,))
    ImageDraw.Draw(im).text((4, 4 + asc), s, font=f, fill=color + (255,), anchor='ls')
    return im

def fit(s, size, weight=800, color=INK, maxw=960):
    """Texte réduit si besoin pour tenir dans maxw."""
    w = font(size, weight).getlength(s)
    if w > maxw: size = int(size * maxw / w)
    return text(s, size, weight, color)

def wrap(s, size, weight, maxw):
    words, lines, cur = [], [], ''
    for wd in s.split():
        if wd in ('?', '!', ':', ';') and words: words[-1] += ' ' + wd
        else: words.append(wd)
    for wd in words:
        test = (cur + ' ' + wd).strip()
        if font(size, weight).getlength(test) <= maxw or not cur: cur = test
        else: lines.append(cur); cur = wd
    if cur: lines.append(cur)
    return lines

@lru_cache(None)
def alpha_lut(a100): return [int(v * a100 / 100) for v in range(256)]

def put(cv, sp, cx, cy, a=1.0, s=1.0, rot=0.0):
    """Colle un sprite centré en (cx, cy) avec opacité, échelle, rotation."""
    if a <= 0.01 or s <= 0.01: return
    if abs(s - 1) > 1e-3:
        sp = sp.resize((max(1, round(sp.width * s)), max(1, round(sp.height * s))), Image.BICUBIC)
    if abs(rot) > 0.05: sp = sp.rotate(rot, Image.BICUBIC, expand=True)
    if a < 0.995:
        sp = sp.copy(); sp.putalpha(sp.getchannel('A').point(alpha_lut(round(a * 100))))
    x, y = round(cx - sp.width / 2), round(cy - sp.height / 2)
    l, t, r, b = max(0, -x), max(0, -y), min(sp.width, W - x), min(sp.height, H - y)
    if r <= l or b <= t: return
    if (l, t, r, b) != (0, 0, sp.width, sp.height): sp = sp.crop((l, t, r, b))
    cv.alpha_composite(sp, (x + l, y + t))

SS = 3
def shape(w, h, fn):
    """Dessin suréchantillonné (bords lisses). fn(draw, k) avec k = facteur d'échelle."""
    im = Image.new('RGBA', (w * SS, h * SS), (255, 255, 255, 0))
    fn(ImageDraw.Draw(im), SS)
    return im.resize((w, h), Image.LANCZOS)

def rrect(w, h, r, fill, outline=None, width=0):
    return shape(w, h, lambda d, k: d.rounded_rectangle((0, 0, w * k - 1, h * k - 1), r * k, fill=fill + (255,),
                                                       outline=(outline + (255,)) if outline else None, width=width * k))

def card(w, h, r=36, fill=PANEL, shadow=120, blur=26, dy=14):
    pad = blur * 2
    im = Image.new('RGBA', (w + 2 * pad, h + 2 * pad), INK + (0,))
    sh = Image.new('RGBA', im.size, INK + (0,))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + dy, pad + w, pad + h + dy), r, fill=INK + (shadow,))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    im.alpha_composite(rrect(w, h, r, fill), (pad, pad))
    return im

def card_pad(c, w): return (c.width - w) // 2

def pill(label, size, weight, fg, bg, padx=34, pady=16):
    t = text(label, size, weight, fg)
    w, h = t.width + 2 * padx, t.height + 2 * pady
    im = rrect(w, h, h // 2, bg)
    im.alpha_composite(t, (padx, pady))
    return im

def circle(d, fill):
    return shape(d, d, lambda dr, k: dr.ellipse((0, 0, d * k - 1, d * k - 1), fill=fill + (255,)))

def headline(cv, t, lines, start=0.0, step=0.14, rise=46, x=W / 2):
    """Lignes qui montent en fondu : [(texte, y, taille, couleur, graisse)]"""
    for i, (s, y, size, color, weight) in enumerate(lines):
        p = ease_out(prog(t, start + i * step, 0.38))
        put(cv, fit(s, size, weight, color), x, y + (1 - p) * rise, a=p)


# ——— Icônes ———
def check_icon(size, bg=GREEN, fg=WHITE):
    def fn(d, k):
        s = size * k
        d.ellipse((0, 0, s - 1, s - 1), fill=bg + (255,))
        pts = [(0.28 * s, 0.53 * s), (0.44 * s, 0.68 * s), (0.73 * s, 0.37 * s)]
        d.line(pts, fill=fg + (255,), width=round(0.095 * s), joint='curve')
        r = 0.047 * s
        for x, y in (pts[0], pts[-1]): d.ellipse((x - r, y - r, x + r, y + r), fill=fg + (255,))
    return shape(size, size, fn)

BOLT = [(0.55, 0.02), (0.16, 0.58), (0.46, 0.58), (0.36, 0.98), (0.86, 0.40), (0.56, 0.40), (0.80, 0.02)]
def bolt_icon(size, color=ORANGE):
    return shape(size, size, lambda d, k: d.polygon([(x * size * k, y * size * k) for x, y in BOLT], fill=color + (255,)))

def arrow_right(size, color=WHITE):
    def fn(d, k):
        s, wd = size * k, round(size * k * 0.14)
        d.line(((0.12 * s, 0.5 * s), (0.86 * s, 0.5 * s)), fill=color + (255,), width=wd)
        d.line(((0.55 * s, 0.2 * s), (0.86 * s, 0.5 * s), (0.55 * s, 0.8 * s)), fill=color + (255,), width=wd, joint='curve')
    return shape(size, size, fn)

def arrow_up(size, color=RED):
    pts = [(0.5, 0.02), (0.95, 0.48), (0.68, 0.48), (0.68, 0.98), (0.32, 0.98), (0.32, 0.48), (0.05, 0.48)]
    return shape(size, size, lambda d, k: d.polygon([(x * size * k, y * size * k) for x, y in pts], fill=color + (255,)))

def shield_icon(size, color=GREEN):
    def fn(d, k):
        s = size * k
        pts = [(0.5, 0.03), (0.92, 0.18), (0.88, 0.55), (0.5, 0.97), (0.12, 0.55), (0.08, 0.18)]
        d.polygon([(x * s, y * s) for x, y in pts], fill=color + (255,))
        c = [(0.3 * s, 0.5 * s), (0.45 * s, 0.64 * s), (0.71 * s, 0.37 * s)]
        d.line(c, fill=WHITE + (255,), width=round(0.09 * s), joint='curve')
    return shape(size, size, fn)

def star_pts(c, R, inner=0.45):
    import math as _m
    pts = []
    for i in range(10):
        a = -_m.pi / 2 + i * _m.pi / 5
        r = R if i % 2 == 0 else R * inner
        pts.append((c[0] + _m.cos(a) * r, c[1] + _m.sin(a) * r))
    return pts

def sparkle(size, color=YELLOW):
    return shape(size, size, lambda d, k: d.polygon(star_pts((size * k / 2, size * k / 2), size * k / 2, inner=0.22)[::1][:10], fill=color + (255,)))


# ——— Fonds ———
def bg_soft(top=BG2, bottom=BG, glow=(60, 24, 10), glow2=BG3):
    bg = Image.new('RGBA', (W, H), bottom + (255,))
    grad = Image.linear_gradient('L').resize((W, H))
    bg.paste(Image.new('RGBA', (W, H), top + (255,)), (0, 0), grad.point(lambda v: 255 - v))
    g = Image.new('RGBA', (W, H), glow + (0,))
    ImageDraw.Draw(g).ellipse((W - 420, -260, W + 320, 480), fill=glow + (120,))
    ImageDraw.Draw(g).ellipse((-380, H - 700, 420, H + 100), fill=glow2 + (150,))
    bg.alpha_composite(g.filter(ImageFilter.GaussianBlur(120)))
    return bg

def bg_grad(c1, c2):
    bg = Image.new('RGBA', (W, H), c2 + (255,))
    grad = Image.linear_gradient('L').resize((W, H))
    bg.paste(Image.new('RGBA', (W, H), c1 + (255,)), (0, 0), grad.point(lambda v: 255 - v))
    return bg

def bg_solid(c): return Image.new('RGBA', (W, H), c + (255,))

_logo = Image.open(LOGO).convert('RGBA')
def logo(scale=0.8):
    """The 1200x300 wordmark, scaled. 0.8 lands it at 960 wide in a 1080 frame."""
    return _logo.resize((round(_logo.width * scale), round(_logo.height * scale)), Image.LANCZOS)
def logo_badge(scale=0.8):
    lg = logo(scale)
    b = rrect(lg.width + 60, lg.height + 30, (lg.height + 30) // 2, WHITE)
    b.alpha_composite(lg, (30, 15))
    return b


# ——— Voix off ———
def tts(textv, length_scale=0.95):
    """ElevenLabs unless TTS_ENGINE=piper and a local model is configured."""
    if os.environ.get('TTS_ENGINE', 'eleven') == 'eleven': return tts_eleven(textv)
    os.makedirs(CACHE, exist_ok=True)
    model = os.environ['PIPER_MODEL']
    key = hashlib.sha1(f'{os.path.basename(model)}|{length_scale}|{textv}'.encode()).hexdigest()[:16]
    path = os.path.join(CACHE, key + '.wav')
    if not os.path.exists(path):
        env = dict(os.environ, PYTHONPATH=os.environ['PIPER_PYTHONPATH'])
        subprocess.run([sys.executable, '-m', 'piper', '-m', model, '-f', path, '--length-scale', str(length_scale),
                        '--sentence-silence', '0.18', '--', textv], env=env, check=True, capture_output=True)
    with wave.open(path) as wf:
        sr, n = wf.getframerate(), wf.getnframes()
        x = np.frombuffer(wf.readframes(n), dtype=np.int16).astype(np.float64) / 32768
    if sr != SR: x = np.interp(np.arange(int(len(x) * SR / sr)) * sr / SR, np.arange(len(x)), x)
    nz = np.nonzero(np.abs(x) > 0.01)[0]
    if len(nz): x = x[max(0, nz[0] - 400): nz[-1] + 2000]
    x = x / (np.max(np.abs(x)) + 1e-9) * 0.9
    x = np.tanh(1.6 * x) / np.tanh(1.6)
    return x


ELEVEN_SETTINGS = dict(stability=0.45, similarity_boost=0.8, style=0.2, use_speaker_boost=True)

# The owner listened to three English voices on a real script line and picked
# this one (2026-10-29). Override with ELEVEN_VOICE_ID.
VOICE_WILL = 'bIHbv24MWmeRgasZH58o'      # American, young, relaxed — the pick
VOICE_LIAM = 'TX3LPaxmHKxFdv7VOQHJ'      # American, young, social-media energy
VOICE_BRIAN = 'nPczCjzI2devNBz1zQrb'     # American, deep, trailer register

def tts_eleven(textv, voice=None):
    """Voix ElevenLabs (clé lue dans ~/.elevenlabs_key, jamais affichée). Voix : ELEVEN_VOICE_ID."""
    import json, urllib.request
    os.makedirs(CACHE, exist_ok=True)
    voice = voice or os.environ.get('ELEVEN_VOICE_ID', VOICE_WILL)
    model = os.environ.get('ELEVEN_MODEL', 'eleven_multilingual_v2')
    h = hashlib.sha1(f'eleven|{voice}|{model}|{json.dumps(ELEVEN_SETTINGS, sort_keys=True)}|{textv}'.encode()).hexdigest()[:16]
    mp3, wav_p = os.path.join(CACHE, h + '.mp3'), os.path.join(CACHE, h + '.wav')
    if not os.path.exists(wav_p):
        with open(os.path.expanduser('~/.elevenlabs_key')) as f: key = f.read().strip()
        lang = os.environ.get('ELEVEN_LANG', 'en')
        body = json.dumps({'text': textv, 'model_id': model, 'language_code': lang, 'voice_settings': ELEVEN_SETTINGS}).encode()
        req = urllib.request.Request(f'https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128', data=body,
                                     headers={'xi-api-key': key, 'Content-Type': 'application/json', 'Accept': 'audio/mpeg'})
        try:
            data = urllib.request.urlopen(req, timeout=120).read()
        except urllib.error.HTTPError as e:
            if e.code != 400: raise
            body = json.dumps({'text': textv, 'model_id': model, 'voice_settings': ELEVEN_SETTINGS}).encode()
            req = urllib.request.Request(req.full_url, data=body, headers=dict(req.header_items()))
            data = urllib.request.urlopen(req, timeout=120).read()
        with open(mp3, 'wb') as f: f.write(data)
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error', '-i', mp3, '-ac', '1', '-ar', str(SR), wav_p], check=True)
    with wave.open(wav_p) as wf:
        x = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    nz = np.nonzero(np.abs(x) > 0.01)[0]
    if len(nz): x = x[max(0, nz[0] - 600): nz[-1] + 3000]
    x = x / (np.max(np.abs(x)) + 1e-9) * 0.9
    return np.tanh(1.2 * x) / np.tanh(1.2)


# ——— Musique de synthèse (originale, libre de droits) ———
RNG = np.random.default_rng(11)
def midi(m): return 440.0 * 2 ** ((m - 69) / 12)
def tarr(n): return np.arange(n) / SR
def env_exp(n, decay, attack=0.002):
    e = np.exp(-tarr(n) / decay)
    a = max(1, int(attack * SR)); e[:a] *= np.linspace(0, 1, a)
    return e
def osc(kind, freq, n):
    ph = 2 * np.pi * np.cumsum(np.broadcast_to(np.asarray(freq, float), (n,))) / SR
    if kind == 'sine': return np.sin(ph)
    if kind == 'tri': return 2 / np.pi * np.arcsin(np.sin(ph))
    if kind == 'saw': return 2 * ((ph / (2 * np.pi)) % 1) - 1
    return np.sign(np.sin(ph))
def filt(x, lo=None, hi=None):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR); g = np.ones_like(f)
    if hi: g *= 1 / np.sqrt(1 + (f / hi) ** 4)
    if lo: g *= (f / lo) ** 2 / np.sqrt(1 + (f / lo) ** 4)
    return np.fft.irfft(X * g, n=len(x))
def noise(n): return RNG.standard_normal(n)
def fade_tail(x, ms=30):
    k = min(len(x), int(ms * SR / 1000)); x[-k:] *= np.linspace(1, 0, k); return x

def kick(g=1.0):
    n = int(0.35 * SR); t = tarr(n)
    x = np.sin(2 * np.pi * np.cumsum(45 + 110 * np.exp(-t / 0.035)) / SR) * env_exp(n, 0.2)
    x += 0.25 * filt(noise(n), lo=2000) * env_exp(n, 0.004)
    return x * g
def clap(g=1.0, lo=900, hi=4500, tail=0.09):
    n = int(0.3 * SR); t = tarr(n); e = np.zeros(n)
    for k in range(3):
        m = t >= k * 0.011; e[m] += np.exp(-(t[m] - k * 0.011) / 0.007)
    e += 0.6 * np.exp(-t / tail)
    return filt(noise(n), lo=lo, hi=hi) * e * 0.5 * g
def hat(g=1.0, open_=False):
    n = int((0.25 if open_ else 0.08) * SR)
    return filt(noise(n), lo=7000) * env_exp(n, 0.16 if open_ else 0.03) * 0.35 * g
def shaker(g=1.0):
    n = int(0.12 * SR)
    return filt(noise(n), lo=4000, hi=10000) * env_exp(n, 0.05, attack=0.015) * 0.3 * g
def bass(m, dur, g=1.0):
    n = int(dur * SR); f = midi(m)
    x = 0.6 * osc('saw', f, n) + 0.8 * osc('sine', f, n)
    x = filt(x, hi=520) * np.exp(-tarr(n) / 1.2)
    a = int(0.004 * SR); x[:a] *= np.linspace(0, 1, a)
    return fade_tail(x, 25) * 0.5 * g
def pluck(m, dur=0.35, g=1.0):
    n = int(dur * SR); f = midi(m)
    x = filt(osc('tri', f, n) + 0.3 * osc('sq', f, n), hi=3500) * env_exp(n, 0.16)
    return fade_tail(x) * 0.35 * g
def marimba(m, dur=0.45, g=1.0):
    n = int(dur * SR); f = midi(m)
    x = osc('sine', f, n) * env_exp(n, 0.3) + 0.35 * osc('sine', 4 * f, n) * env_exp(n, 0.05)
    return fade_tail(x) * 0.4 * g
def piano(m, dur=1.4, g=1.0):
    n = int(dur * SR); f = midi(m); x = np.zeros(n)
    for h, a in ((1, 1), (2, 0.45), (3, 0.22), (4, 0.12), (5, 0.06)):
        x += a * osc('sine', f * h * (1 + 0.0004 * h), n) * env_exp(n, 1.1 / h ** 0.7, attack=0.003)
    return fade_tail(x, 60) * 0.3 * g
def pad(chord, dur, g=1.0, hi=1400):
    n = int(dur * SR); x = np.zeros(n)
    for m in chord:
        for det in (-0.004, 0.004): x += osc('saw', midi(m) * (1 + det), n)
        x += 0.5 * osc('sine', midi(m - 12), n)
    x = filt(x, hi=hi)
    e = np.ones(n); a, r = int(0.25 * SR), int(0.3 * SR)
    e[:a] = np.linspace(0, 1, a); e[-r:] *= np.linspace(1, 0, r)
    return x * e * 0.08 * g
def stab(chord, g=1.0):
    n = int(0.3 * SR); x = np.zeros(n)
    for m in chord: x += osc('saw', midi(m), n) + osc('saw', midi(m) * 1.005, n)
    return filt(x, hi=2600) * env_exp(n, 0.09) * 0.12 * g
def ks(m, dur=1.6, g=1.0, damp=0.996):
    f = midi(m); N = max(2, int(SR / f)); n = int(dur * SR)
    y = np.zeros(n + N + 1)
    y[:N] = filt(RNG.uniform(-1, 1, N * 8), hi=3500)[:N]
    y[N] = damp * 0.5 * y[0]
    s = N + 1
    while s < n + N + 1:
        e = min(s + N, n + N + 1)
        y[s:e] = damp * 0.5 * (y[s - N:e - N] + y[s - N - 1:e - N - 1])
        s = e
    return fade_tail(y[N:N + n], 60) * 0.5 * g

MOODS = {
    'pop':     dict(bpm=116, prog=[(36, [60, 64, 67]), (43, [59, 62, 67]), (45, [60, 64, 69]), (41, [60, 65, 69])], style='pop'),
    'electro': dict(bpm=126, prog=[(45, [57, 60, 64]), (41, [57, 60, 65]), (48, [55, 60, 64]), (43, [55, 59, 62])], style='electro'),
    'playful': dict(bpm=108, prog=[(41, [65, 69, 72]), (48, [64, 67, 72]), (38, [62, 65, 69]), (46, [62, 65, 70])], style='playful'),
    'calm':    dict(bpm=90,  prog=[(45, [57, 60, 64]), (41, [57, 60, 65]), (48, [55, 60, 64]), (43, [55, 59, 62])], style='calm'),
    'promo':   dict(bpm=124, prog=[(36, [60, 64, 67]), (43, [59, 62, 67]), (45, [60, 64, 69]), (41, [60, 65, 69])], style='promo'),
    'warm':    dict(bpm=100, prog=[(38, [62, 66, 69]), (45, [61, 64, 69]), (47, [62, 66, 71]), (43, [62, 67, 71])], style='warm'),
}

def music(mood, total):
    M = MOODS[mood]; beat = 60 / M['bpm']; bar = 4 * beat; st = M['style']
    n = int((total + 2) * SR); L = np.zeros(n); R = np.zeros(n)
    def add(sig, t, g=1.0, pan=0.0):
        i = int(t * SR)
        if i >= n: return
        sig = sig[:n - i]; a = (pan + 1) * math.pi / 4
        L[i:i + len(sig)] += sig * g * math.cos(a); R[i:i + len(sig)] += sig * g * math.sin(a)
    for b in range(int(total / bar) + 1):
        t0 = b * bar; root, ch = M['prog'][b % len(M['prog'])]
        if st in ('pop', 'promo', 'electro'):
            for q in range(4): add(kick(), t0 + q * beat, 0.9)
            for q in (1, 3): add(clap(), t0 + q * beat, 0.7, 0.1)
            hats = 16 if st != 'pop' else 8
            for h in range(hats):
                tt = t0 + h * bar / hats
                if st == 'pop' and h % 2 == 0: continue
                add(hat(open_=(st == 'electro' and h % 4 == 2)), tt, 0.5 if h % 2 else 0.3, 0.3)
            if st == 'electro':
                for e in range(8):
                    if e % 2: add(bass(root, beat / 2 * 0.9), t0 + e * beat / 2, 0.9)
                for q in (1.5, 3.5): add(stab([m + 12 for m in ch]), t0 + q * beat, 0.8, -0.2)
                add(pad(ch, bar, hi=900), t0, 0.6)
            else:
                for e in range(8): add(bass(root + (12 if e % 2 else 0), beat / 2 * 0.9), t0 + e * beat / 2, 0.8)
                arp = [0, 1, 2, 1] * (4 if st == 'promo' else 2)
                step = bar / len(arp)
                for i, k in enumerate(arp): add(pluck(ch[k] + 12, step * 1.6), t0 + i * step, 0.7, (-0.3, 0.3)[i % 2])
                add(pad(ch, bar), t0, 0.8)
        elif st == 'playful':
            for q in (0, 2): add(kick(), t0 + q * beat, 0.7)
            for q in (1, 3): add(clap(lo=1500, hi=6000, tail=0.04), t0 + q * beat, 0.6, 0.2)
            for h in range(16): add(shaker(), t0 + h * beat / 4, 0.6 if h % 2 else 0.3, 0.4)
            for q in range(4): add(bass(root, beat * 0.8), t0 + q * beat, 0.8)
            for i, k in enumerate([0, 2, 1, 2, 0, 2, 1, 2]): add(marimba(ch[k] + 12), t0 + i * beat / 2, 0.8, (-0.3, 0.3)[i % 2])
        elif st == 'calm':
            add(kick(), t0, 0.45)
            add(kick(), t0 + 2 * beat, 0.35)
            for h in range(8): add(shaker(), t0 + h * beat / 2, 0.35, 0.3)
            for hb in (0, 2): add(bass(root, beat * 1.9), t0 + hb * beat, 0.7)
            for i, k in enumerate([0, 1, 2, 1, 0, 1, 2, 1]): add(piano(ch[k] + 12, 1.4), t0 + i * beat / 2, 0.55, (-0.25, 0.25)[i % 2])
            add(pad(ch, bar, hi=1000), t0, 0.7)
        elif st == 'warm':
            add(kick(), t0, 0.6); add(kick(), t0 + 2 * beat, 0.5)
            for q in (1, 3): add(clap(lo=1800, hi=5000, tail=0.03), t0 + q * beat, 0.4, -0.2)
            for h in range(8): add(shaker(), t0 + h * beat / 2, 0.4, 0.3)
            for hb in (0, 2): add(bass(root, beat * 1.8), t0 + hb * beat, 0.75)
            for q in (0, 1.5, 2, 3, 3.5):
                for j, m in enumerate(sorted(ch + [ch[0] + 12])): add(ks(m, 1.4), t0 + q * beat + j * 0.012, 0.35, (-0.3, 0.3)[j % 2])
    st_ = np.stack([L, R], 1)[:int(total * SR)]
    st_ /= np.sqrt(np.mean(st_ ** 2)) + 1e-9
    fo = int(1.2 * SR); st_[-fo:] *= np.linspace(1, 0, fo)[:, None]
    fi = int(0.05 * SR); st_[:fi] *= np.linspace(0, 1, fi)[:, None]
    return st_ * 0.16


# ——— Bruitages ———
def sfx(name):
    if name == 'whoosh':
        n = int(0.5 * SR); t = tarr(n)
        e = np.sin(np.pi * t / t[-1]) ** 2
        return filt(noise(n), lo=400, hi=4000) * e * 0.35
    if name == 'pop':
        n = int(0.12 * SR)
        return osc('sine', 500 + 900 * (1 - np.exp(-tarr(n) / 0.02)), n) * env_exp(n, 0.04) * 0.5
    if name == 'tap':
        n = int(0.05 * SR)
        return (osc('sine', 1800, n) * 0.5 + filt(noise(n), lo=3000) * 0.3) * env_exp(n, 0.008)
    if name == 'ding':
        n = int(1.2 * SR); f = 1318.5; x = np.zeros(n)
        for h, a, d in ((1, 1, 0.9), (2.0, 0.5, 0.6), (3.01, 0.3, 0.4), (4.2, 0.2, 0.3)): x += a * osc('sine', f * h, n) * env_exp(n, d)
        return x * 0.22
    if name == 'check':
        a = marimba(84, 0.3); b = marimba(91, 0.4); x = np.zeros(len(b) + int(0.07 * SR))
        x[:len(a)] += a; x[int(0.07 * SR):] += b
        return x * 0.9
    if name == 'boom':
        n = int(0.7 * SR); t = tarr(n)
        return (np.sin(2 * np.pi * np.cumsum(35 + 60 * np.exp(-t / 0.08)) / SR) * env_exp(n, 0.35) + filt(noise(n), hi=500) * env_exp(n, 0.1) * 0.5) * 0.7
    if name == 'riser':
        n = int(0.9 * SR); t = tarr(n); e = (t / t[-1]) ** 2
        return (filt(noise(n), lo=1500) * 0.4 + osc('sine', 300 + 900 * t / t[-1], n) * 0.15) * e * 0.5
    if name == 'sparkle':
        n = int(0.6 * SR); x = np.zeros(n)
        for i in range(6):
            s = int(i * 0.07 * SR); m = n - s
            x[s:] += osc('sine', 2000 + 350 * i, m) * env_exp(m, 0.08) * 0.25
        return x
    if name == 'buzz':   # vibreur de téléphone (2 impulsions)
        n = int(0.62 * SR); t = tarr(n); g = ((t % 0.34) < 0.24).astype(float)
        return filt(osc('saw', 165, n), hi=900) * filt(g, hi=60) * 0.3
    if name == 'ring':   # sonnerie douce à deux notes
        n = int(1.1 * SR); t = tarr(n); x = np.zeros(n)
        for k, f in enumerate((1046.5, 1318.5, 1046.5, 1318.5)):
            s = int(k * 0.13 * SR); m = n - s; x[s:] += osc('sine', f, m) * env_exp(m, 0.12) * (0.5 if k < 2 else 0.35)
        return x * 0.3
    if name == 'nope':   # erreur : deux notes graves descendantes
        x = np.zeros(int(0.42 * SR))
        for k, f in enumerate((330, 247)):
            s = int(k * 0.15 * SR); m = int(0.26 * SR); x[s:s + m] += filt(osc('square', f, m), hi=2000) * env_exp(m, 0.09) * 0.22
        return x
    if name == 'coin':   # pièce de jeu vidéo
        x = np.zeros(int(0.45 * SR)); a = int(0.07 * SR)
        x[:a] += osc('square', 988, a) * 0.12; m = len(x) - a; x[a:] += osc('square', 1319, m) * env_exp(m, 0.12) * 0.12
        return filt(x, hi=6000)
    raise ValueError(name)


# ——— Montage ———
class Scene:
    def __init__(self, fn, vo=None, min_dur=2.0, hold=0.55, sfx=(), vo_delay=0.18):
        self.fn, self.vo, self.min_dur, self.hold, self.sfx, self.vo_delay = fn, vo, min_dur, hold, list(sfx), vo_delay

class Ctx:
    def __init__(self, d, vo_len, vo_start): self.d, self.vo, self.vo_start, self.vo_end = d, vo_len, vo_start, vo_start + vo_len

XF = 0.24

def render(name, scenes, mood, out_dir, voice_speed=0.95, logo_mode='plain', preview=None, transition='fade'):
    """logo_mode : 'plain' (logo seul), 'badge' (logo sur pastille blanche) ou None. Le logo reste fixe sauf sur la dernière scène."""
    vos = [tts(s.vo, voice_speed) if s.vo else np.zeros(0) for s in scenes]
    durs = [max(s.min_dur, s.vo_delay + len(v) / SR + s.hold) for s, v in zip(scenes, vos)]
    starts = list(np.cumsum([0] + durs[:-1]))
    total = float(sum(durs))
    ctxs = [Ctx(d, len(v) / SR, s.vo_delay) for d, v, s in zip(durs, vos, scenes)]
    lg = logo_badge(0.8) if logo_mode == 'badge' else logo(0.8) if logo_mode else None

    def frame(t):
        i = max(k for k, s in enumerate(starts) if t >= s)
        cur = scenes[i].fn(t - starts[i], ctxs[i])
        if i > 0 and transition == 'fade' and t - starts[i] < XF:
            k = (t - starts[i]) / XF
            prev = scenes[i - 1].fn(t - starts[i - 1], ctxs[i - 1])
            base = Image.new('RGBA', (W, H), (255, 255, 255, 255))
            cur = Image.blend(prev, base, ease_io(k * 2)) if k < 0.5 else Image.blend(base, cur, ease_io(k * 2 - 1))
        if lg is not None:
            put(cur, lg, W / 2, 300, a=ease_out(prog(t, 0, 0.3)) * (1 - prog(t, starts[-1], XF / 2)))
        return cur.convert('RGB')

    os.makedirs(out_dir, exist_ok=True)
    if preview is not None:
        ims = [frame(starts[i] + min(durs[i] - 0.3, max(1.2, durs[i] * 0.7))).resize((270, 480), Image.LANCZOS) for i in range(len(scenes))]
        sheet = Image.new('RGB', (len(ims) * 280, 480), (40, 40, 40))
        for i, im in enumerate(ims): sheet.paste(im, (i * 280, 0))
        sheet.save(preview, quality=88)
        return total

    return mix_and_encode(name, scenes, vos, starts, durs, mood, out_dir, frame)


def mix_and_encode(name, scenes, vos, starts, durs, mood, out_dir, frame):
    """Bande-son (voix + musique baissée sous la voix + bruitages) puis encodage MP4 des images frame(t)."""
    total = float(sum(durs))
    ctxs = [Ctx(d, len(v) / SR, s.vo_delay) for d, v, s in zip(durs, vos, scenes)]
    N = int(total * SR)
    vo = np.zeros(N)
    for s, v, st in zip(scenes, vos, starts):
        i = int((st + s.vo_delay) * SR); vo[i:i + len(v)] += v[:max(0, N - i)]
    fx = np.zeros((N, 2))
    def add_fx(name, t, g=1.0):
        x = sfx(name); i = int(t * SR)
        if 0 <= i < N: x = x[:N - i]; fx[i:i + len(x)] += x[:, None] * g
    for k, st in enumerate(starts[1:]): add_fx('whoosh', st - 0.25, 0.8)
    for s, st, c in zip(scenes, starts, ctxs):
        for item in s.sfx:
            t, nm = item[0], item[1]; g = item[2] if len(item) > 2 else 1.0
            add_fx(nm, st + (t(c) if callable(t) else t), g)
    hop = 441; fr = np.sqrt(np.convolve(vo ** 2, np.ones(hop) / hop, 'same')[::hop])
    envd = np.zeros_like(fr); e = 0.0
    for j, v in enumerate(fr):
        e = max(v, e * 0.975); envd[j] = e
    duck = 1 - 0.6 * np.clip(envd / 0.06, 0, 1)
    duck = np.interp(np.arange(N) / hop, np.arange(len(duck)), duck)
    mus = music(mood, total)[:N] * duck[:, None]
    mix = mus + vo[:, None] * (0.0 if os.environ.get('NO_VO') else 0.95) + fx * 0.8
    mix = np.tanh(1.1 * mix) / np.tanh(1.1)
    mix *= 0.93 / (np.max(np.abs(mix)) + 1e-9)
    wav_path = os.path.join(out_dir, f'.{name}.wav')
    with wave.open(wav_path, 'wb') as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes((mix * 32767).astype(np.int16).tobytes())

    out = os.path.join(out_dir, f'{name}.mp4')
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', wav_path,
           '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-b:a', '160k', '-t', f'{total:.3f}', '-movflags', '+faststart', out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(total * FPS)):
        proc.stdin.write(frame(f / FPS).tobytes())
    proc.stdin.close(); proc.wait()
    os.remove(wav_path)
    return out, total


# ——— eSports Boost: the brand's own objects ———
# Everything below is drawn from data.py rather than from constants here, so a
# rank in a video is the same colour as the same rank on the site.

def hexc(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

LOL = next(g for g in D.GAMES if 'League' in g['name'])

def tier_rgb(tier):
    """The site's ONE rank colour table (D.tier_color), as RGB."""
    return hexc(D.tier_color(LOL, tier))

def tier_of(rank):
    """'Gold IV' -> 'Gold'. A rank with no division ('Master') is its own tier."""
    parts = rank.split()
    return ' '.join(parts[:-1]) if len(parts) > 1 and parts[-1].strip('IV') == '' else rank

def lift(col, k=0.45):
    """Toward the text colour: a 26px mark colour reads as disabled text at 90px.
    The rank keeps its hue, the contrast stays legible. Same trick as .ob-climb."""
    return lerp_col(col, INK, k)

def rank_mark(rank, size=190, ring=True):
    """A rank as the site draws it: the division numeral in the tier's colour.
    Never the publisher's emblem — same trademark rule as pay_marks()."""
    col = tier_rgb(tier_of(rank))
    div = rank.split()[-1] if len(rank.split()) > 1 else rank[:2].upper()
    im = Image.new('RGBA', (size, size), col + (0,))
    d = ImageDraw.Draw(im)
    if ring:
        d.ellipse((2, 2, size - 2, size - 2), fill=col + (38,), outline=col + (190,), width=max(3, size // 32))
    sp = fit(div, int(size * 0.46), 900, lift(col, 0.25), maxw=int(size * 0.72))
    im.alpha_composite(sp, ((size - sp.width) // 2, (size - sp.height) // 2))
    return im

def rank_word(rank, size=96, weight=900):
    """The whole rank name in its own tier colour, lifted to stay readable."""
    return fit(rank, size, weight, lift(tier_rgb(tier_of(rank))), maxw=980)

def lp_bar(pct, w=620, h=26, col=EMBER):
    im = rrect(w, h, h // 2, HAIR)
    if pct > 0:
        im.alpha_composite(rrect(max(h, round(w * clamp(pct))), h, h // 2, col), (0, 0))
    return im

def tiers_of():
    """The ladder's tiers in order, each with its rungs — the shape the game
    page's track draws (one segment per tier, striped into its divisions)."""
    out = []
    for r in LOL['ladder']:
        t = tier_of(r)
        if not out or out[-1][0] != t: out.append((t, []))
        out[-1][1].append(r)
    return out

def ladder(from_rank, to_rank, w=960, h=40, caps=True, fill_to=1.0):
    """The tier track: ONE SEGMENT PER TIER, not per rung — 29 rungs across a
    phone screen is a 32px smear and the span reads as a blob. The crossed
    tiers fill in their own colours, a ring marks `from` and a dot `to`.

    `fill_to` (0..1) animates the span filling from `from` toward `to`."""
    lad, tiers = LOL['ladder'], tiers_of()
    i, j = lad.index(from_rank), lad.index(to_rank)
    lo, hi = min(i, j), max(i, j)
    gap = 6
    seg_w = (w - gap * (len(tiers) - 1)) / len(tiers)
    im = Image.new('RGBA', (w, h + (74 if caps else 36)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top = 18
    k = 0
    for n, (tname, rungs) in enumerate(tiers):
        x = n * (seg_w + gap)
        d.rounded_rectangle((x, top, x + seg_w, top + h), 8, fill=HAIR + (255,))
        col = tier_rgb(tname)
        # the part of this tier inside the climb, limited by fill_to
        reach = lo + (hi - lo) * clamp(fill_to)
        a, b = k, k + len(rungs)
        if reach > a and hi >= a and lo <= b:
            f0 = max(a, lo); f1 = min(b, reach)
            if f1 > f0:
                x0 = x + seg_w * (f0 - a) / len(rungs)
                x1 = x + seg_w * (f1 - a) / len(rungs)
                d.rounded_rectangle((x0, top, max(x1, x0 + 6), top + h), 8, fill=col + (240,))
        if caps:
            cap = fit(tname, 26, 700, lift(col, 0.3) if (hi >= a and lo < b) else TEXT3, maxw=seg_w + gap)
            im.alpha_composite(cap, (round(x + (seg_w - cap.width) / 2), top + h + 14))
        k = b
    def mark_x(idx):
        for n, (tname, rungs) in enumerate(tiers):
            if idx < sum(len(r[1]) for r in tiers[:n + 1]):
                a = sum(len(r[1]) for r in tiers[:n])
                return n * (seg_w + gap) + seg_w * (idx - a + 0.5) / len(rungs)
        return w
    xr = mark_x(i)
    d.ellipse((xr - 17, top + h / 2 - 17, xr + 17, top + h / 2 + 17), outline=INK + (255,), width=5)
    if fill_to >= 0.999:
        xd = mark_x(j)
        d.ellipse((xd - 19, top + h / 2 - 19, xd + 19, top + h / 2 + 19), fill=EMBER + (255,))
    return im

def typo(items, bg=None, icon=None, icon_y=1380, icon_spin=0, y_mid=860):
    """Full-bleed type: one line lands per beat of the voice.
    items: [(text, size, colour)]. Returns (scene_fn, times) — `times` is where
    the lines land, so the caller can hang a 'pop' on each one."""
    base = bg if bg is not None else bg_solid(BG)
    sprites = [fit(t_, size, 900, col, maxw=980) for t_, size, col in items]
    gap = 12
    total_h = sum(sp.height for sp in sprites) + gap * (len(sprites) - 1)
    ys, y = [], y_mid - total_h / 2
    for sp in sprites:
        ys.append(y + sp.height / 2); y += sp.height + gap
    def fn(t, c):
        cv = base.copy()
        span = max(0.6, c.vo * 0.75)
        for i, (sp, yy) in enumerate(zip(sprites, ys)):
            p = prog(t, c.vo_start + span * i / max(1, len(sprites)), 0.2)
            if p > 0:
                put(cv, sp, W / 2, yy, a=clamp(p * 3), s=lerp(1.7, 1, ease_out(p)), rot=lerp(-5, 0, ease_out(p)))
        if icon is not None:
            p = prog(t, c.vo_start + span, 0.3)
            put(cv, icon, W / 2, icon_y + math.sin(t * 5) * 8, a=clamp(p * 2), s=pop(p), rot=-t * icon_spin)
        return cv
    def times(c):
        span = max(0.6, c.vo * 0.75)
        return [c.vo_start + span * i / max(1, len(items)) for i in range(len(items))]
    return fn, times

def cta_button(label, color=None, w=900, h=152, fg=(6, 6, 10)):
    """Filled with the ember and carrying its glow — the design system's rule:
    a primary button here is never an outline."""
    color = color or EMBER
    im = Image.new('RGBA', (w + 90, h + 90), color + (0,))
    sh = Image.new('RGBA', im.size, color + (0,))
    ImageDraw.Draw(sh).rounded_rectangle((45, 64, 45 + w, 64 + h), h // 2, fill=color + (120,))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(20)))
    im.alpha_composite(rrect(w, h, h // 2, color), (45, 45))
    lab = fit(label, 56, 850, fg, maxw=w - 170)
    arr = arrow_right(54, fg)
    x = 45 + (w - lab.width - 20 - arr.width) // 2
    im.alpha_composite(lab, (x, 45 + (h - lab.height) // 2))
    im.alpha_composite(arr, (x + lab.width + 20, 45 + (h - arr.height) // 2))
    return im


class EndCard:
    """The close: logo, one headline, the price line, the CTA and the three
    guarantees.

    ⚠ IT CARRIES NO RATING AND NO COUNT. The review score, the review count, the
    client count and the roster size in data.py are invented placeholders (see
    *Placeholder data* in CLAUDE.md), and an ad is the one surface where that
    stops being a to-do. The three lines it does show are GUARANTEES_INLINE,
    which is signed-off policy copy."""

    GUARANTEES = ("Money back until a booster takes it", "Pause anytime", "VPN in your region")

    def __init__(self, title=("Pick your rank.", "We climb it."), sub=None, button="Start my climb",
                 domain="esportsboost.com"):
        self.bg = bg_soft()
        self.title, self.sub = title, sub
        self.button = cta_button(button)
        self.logo = logo(0.78)
        self.dom = text(domain, 44, 700, TEXT2)
        self.rows = [(check_icon(42, GREEN, BG), text(g, 38, 600, TEXT2)) for g in self.GUARANTEES]

    def __call__(self, t, ctx):
        cv = self.bg.copy()
        p = prog(t, 0.0, 0.35)
        put(cv, self.logo, W / 2, 420, a=clamp(p * 2), s=lerp(0.86, 1, ease_out(p)))
        headline(cv, t, [(self.title[0], 700, 104, INK, 850),
                         (self.title[1], 820, 104, EMBER, 900)], start=0.12)
        if self.sub:
            headline(cv, t, [(self.sub, 950, 52, TEXT2, 650)], start=0.42)
        p = prog(t, 0.58, 0.4)
        pulse = 1 + (0.035 * math.sin((t - 1.1) * 2 * math.pi * 1.4) if t > 1.1 else 0)
        put(cv, self.button, W / 2, 1150, a=clamp(p * 2), s=pop(p) * pulse)
        y = 1340
        for i, (ic, lab) in enumerate(self.rows):
            a = ease_out(prog(t, 0.8 + 0.12 * i, 0.35))
            tot = ic.width + 16 + lab.width
            put(cv, ic, W / 2 - tot / 2 + ic.width / 2, y, a=a)
            put(cv, lab, W / 2 + tot / 2 - lab.width / 2, y, a=a)
            y += 86
        put(cv, self.dom, W / 2, y + 30, a=ease_out(prog(t, 1.2, 0.4)) * 0.9)
        return cv
