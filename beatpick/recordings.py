"""Conservative cross-album recording grouping, independent of BPM analysis."""
import hashlib
import itertools
import json
import re
import subprocess
import unicodedata

VERSION = 'recording-waveform-v1'


def normalized(value):
    # Keep remix/edit/version text: never collapse it into the base song.
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value).casefold()).strip()


def version_key(title):
    # Preserve every explicit bracketed version plus unbracketed remix/edit suffixes.
    title = normalized(title)
    bracketed = re.findall(r'\([^)]*\)|\[[^]]*\]', title)
    suffix = re.search(r'\s[-–—]\s(.+)$', title)
    tail = re.search(r'\b(?:\w+\s+){0,3}(?:remix|mix|edit|version|rework|bootleg)\b.*$', title)
    return tuple(bracketed), suffix.group(1) if suffix else (tail.group(0) if tail else '')


def compare_audio(a, b):
    import numpy as np
    from scipy import signal
    if min(len(a), len(b)) / max(len(a), len(b)) < .97:
        return dict(same=False, reason='different length')
    cc = signal.correlate(a, b, method='fft')
    lags = signal.correlation_lags(len(a), len(b))
    valid = np.flatnonzero(abs(lags) <= 40000)  # max. ten seconds offset
    lag = int(lags[valid[np.argmax(abs(cc[valid]))]])
    aa = a[max(lag, 0):min(len(a), len(b)+lag)]
    bb = b[max(-lag, 0):min(len(b), len(a)-lag)]
    coverage = len(aa) / max(len(a), len(b))
    def correlation(x, y):
        denominator = float(np.linalg.norm(x)*np.linalg.norm(y))
        return abs(float(np.dot(x, y))/denominator) if denominator else 0.
    score = correlation(aa, bb)
    sections = [correlation(x, y) for x, y in zip(np.array_split(aa, 4), np.array_split(bb, 4))]
    return dict(same=bool(coverage >= .97 and score >= .94 and min(sections) >= .90),
                correlation=round(score, 5), sections=[round(x, 5) for x in sections],
                coverage=round(coverage, 5), offset_seconds=lag/4000)


def group_recordings(rows, state, identity):
    import numpy as np
    hits = sorted((r for r in rows if r.get('passes')), key=lambda r: r['persistent_id'])
    cache_path = state/'recording-cache.json'
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    audio, evidence, matches = {}, [], set()
    def decode(row):
        pid = row['persistent_id']
        if pid not in audio:
            raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', row['path'],
                '-ac', '1', '-ar', '4000', '-f', 'f32le', '-'], stderr=subprocess.PIPE)
            y = np.frombuffer(raw, dtype='<f4').copy()
            if abs(len(y)/4000-row.get('analysis_duration', row['duration'])) > 3:
                raise ValueError('Incomplete audio decoding during duplicate comparison: '+pid)
            audio[pid] = y
        return audio[pid]
    for a, b in itertools.combinations(hits, 2):
        if version_key(a['title']) != version_key(b['title']):
            continue
        da, db = a.get('analysis_duration', a['duration']), b.get('analysis_duration', b['duration'])
        if min(da, db)/max(da, db) < .97:
            continue
        key = hashlib.sha256(json.dumps([VERSION, identity(a), identity(b)]).encode()).hexdigest()
        if key not in cache:
            cache[key] = compare_audio(decode(a), decode(b))
        result = dict(cache[key], persistent_ids=[a['persistent_id'], b['persistent_id']])
        evidence.append(result)
        if result['same']:
            matches.add(frozenset(result['persistent_ids']))
    # Complete-link grouping: A=B and B=C alone must not imply A=C.
    groups = []
    for row in hits:
        for group in groups:
            if all(frozenset([row['persistent_id'], r['persistent_id']]) in matches for r in group):
                group.append(row)
                break
        else:
            groups.append([row])
    tmp = cache_path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    tmp.replace(cache_path)
    return groups, evidence
