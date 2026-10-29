# -*- coding: utf-8 -*-
"""ElevenLabs voice-over with PER-WORD timing, then the voice + music + sfx mix.

Ported verbatim from the Enevie films (outils/hyperframes/voix.py), English voice.
Everything here is a decision the owner already made and validated there — the
dates are his:

  · 25 Oct — a RETOUCHED take (speed 0.85, silences closed up between sentences)
    was judged "catastrophique". The take is used AS RECORDED: one call for the
    whole film, natural speed, NO cutting, NO silence added, NO trimming.
  · 28 Oct — music at 0.45 (about -7 dB under the voice) is the validated level.
  · The take is ONE request to the `with-timestamps` endpoint, which returns the
    time of every character; words are rebuilt from it so animation beats can be
    hung on the word being spoken (`word_t`), never on a hardcoded second.

This is the opposite of the older per-scene engine (site/tools/video_lib.py),
where each line was its own request, trimmed of silence and padded with a hold —
which is exactly the chopped delivery he rejected.""" 
import base64, json, os, re, subprocess, sys, urllib.request, wave
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import video_lib as V   # the older engine, kept for its synth music and sfx
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
SR = V.SR
VOICE = 'bIHbv24MWmeRgasZH58o'   # Will — the owner picked it from three English takes (29 Oct)
MODEL = os.environ.get('ELEVEN_MODEL', 'eleven_v4')   # the model he validated
LANG = os.environ.get('ELEVEN_LANG', 'en')
SETTINGS = {'stability': 0.5, 'similarity_boost': 0.75}


def tts(lines, path_base, model=MODEL, settings=SETTINGS, voice_id=None):
    """Appelle ElevenLabs une seule fois (cache path_base.mp3 / .json, refait si le texte, le modèle ou les réglages changent)."""
    voice_id = voice_id or VOICE
    text = ' '.join(lines)
    vjson, vmp3 = path_base + '.json', path_base + '.mp3'
    if os.path.exists(vjson):
        c = json.load(open(vjson, encoding='utf-8'))
        if c['text'] == text and c.get('voice') == voice_id and c.get('model') == model and c.get('settings') == settings:
            return vmp3, c['alignment']
    key = open(os.path.expanduser('~/.elevenlabs_key')).read().strip()
    body = {'text': text, 'model_id': model, 'language_code': LANG, 'voice_settings': settings}
    req = urllib.request.Request(f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128',
                                 data=json.dumps(body).encode(), headers={'xi-api-key': key, 'Content-Type': 'application/json'})
    r = json.load(urllib.request.urlopen(req, timeout=240))
    open(vmp3, 'wb').write(base64.b64decode(r['audio_base64']))
    json.dump({'lines': lines, 'text': text, 'voice': voice_id, 'model': model, 'settings': settings, 'alignment': r['alignment']},
              open(vjson, 'w'), ensure_ascii=False)
    return vmp3, r['alignment']


def voice(lines, path_base, build_dir, offset=0.3, speed=1.0, voice_id=None):
    """Renvoie (voix numpy mono, mots [{w,s,e}], lignes [{text,start,end}]) : la prise telle quelle, sans découpage.
    speed < 1 étire toute la prise (hauteur conservée) ; les minutages restent ceux de la prise d'origine,
    le film les divise par speed (voir mix() et la composition)."""
    vmp3, al = tts(lines, path_base, voice_id=voice_id)
    text = ' '.join(lines)
    chars = al['characters']
    cs = [t + offset for t in al['character_start_times_seconds']]
    ce = [t + offset for t in al['character_end_times_seconds']]
    os.makedirs(build_dir, exist_ok=True)
    wav_vo = os.path.join(build_dir, 'vo.wav')
    af = ['-af', f'atempo={speed}'] if speed != 1.0 else []
    subprocess.run([FF, '-loglevel', 'error', '-y', '-i', vmp3, *af, '-ac', '1', '-ar', str(SR), wav_vo], check=True)
    with wave.open(wav_vo) as wf:
        vo = np.frombuffer(wf.readframes(wf.getnframes()), np.int16).astype(np.float64) / 32768
    words, cur = [], None
    for ch, s, e in zip(chars, cs, ce):
        if ch.isspace():
            if cur: words.append(cur); cur = None
            continue
        if cur is None: cur = {'w': ch, 's': s, 'e': e}
        else: cur['w'] += ch; cur['e'] = e
    if cur: words.append(cur)
    for k in range(len(words) - 1, 0, -1):          # « ! », « ? » restent collés au mot
        if not re.search(r'\w', words[k]['w']):
            words[k - 1]['w'] += '\u00a0' + words[k]['w']; words[k - 1]['e'] = words[k]['e']; del words[k]
    out_lines, pos = [], 0
    for l in lines:
        i = text.index(l, pos); pos = i + len(l)
        out_lines.append({'text': l, 'start': round(cs[i], 3), 'end': round(ce[max(x for x in range(i, i + len(l)) if text[x].isalnum())], 3)})
    for w in words: w['s'], w['e'] = round(w['s'], 3), round(w['e'], 3)
    print(f'voice: natural take ({MODEL}, {LANG}), {len(vo) / SR:.2f} s at speed {speed}')
    return vo, words, out_lines


def word_t(words, w, after=0.0, end=False):
    """Instant (début ou fin) du premier mot `w` prononcé après `after`."""
    w = w.lower()
    for x in words:
        if x['s'] >= after - 1e-6 and re.sub(r"[^\w']", '', x['w'].lower()) == w:
            return x['e'] if end else x['s']
    raise KeyError(w)


def mix(vo, total, cues, out_wav, mood='pop', offset=0.3, speed=1.0, music_gain=0.45):   # 0,45 ≈ −7 dB : niveau validé par le client le 28 oct. 2026, à garder
    """Voix + musique (baissée sous la voix, retour lent) + bruitages [(nom, t, gain)].
    `total` est la durée du film ; les instants des bruitages et `offset` sont en temps de la prise (divisés par speed)."""
    vo = vo / (np.max(np.abs(vo)) + 1e-9) * 0.9
    N = int(total * SR)
    v = np.zeros(N); i0 = int(offset / speed * SR); v[i0:i0 + len(vo)] = vo[:N - i0]
    fx = np.zeros((N, 2))
    for name, t, g in cues:
        x = V.sfx(name); i = int(t / speed * SR)
        if 0 <= i < N: x = x[:N - i]; fx[i:i + len(x)] += x[:, None] * g
    hop = 441
    fr = np.sqrt(np.convolve(v ** 2, np.ones(hop) / hop, 'same')[::hop])
    envd = np.zeros_like(fr); e = 0.0
    for j, a in enumerate(fr): e = max(a, e * 0.99); envd[j] = e
    duck = np.interp(np.arange(N) / hop, np.arange(len(envd)), 1 - 0.55 * np.clip(envd / 0.06, 0, 1))
    m = V.music(mood, total)[:N] * duck[:, None] * music_gain + v[:, None] * 0.95 + fx * 0.75   # music_gain : niveau de la musique (0,45 par défaut)
    m = np.tanh(1.1 * m) / np.tanh(1.1); m *= 0.93 / (np.max(np.abs(m)) + 1e-9)
    with wave.open(out_wav, 'wb') as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR); wf.writeframes((m * 32767).astype(np.int16).tobytes())
