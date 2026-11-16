from settings import VALUES as S
"""Read-only Music inventory and incremental audio analysis; stage persistent JSON."""
import argparse
import concurrent.futures
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import time

METHOD_VERSION = 'window-v2-bass-crosscheck-165-185-v6'
DEFAULT_STATE = Path('data')


def write_json(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    tmp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def identity(row):
    p = Path(row['path'])
    s = p.stat()
    return hashlib.sha256(json.dumps([METHOD_VERSION, S, str(p.resolve()), s.st_size, s.st_mtime_ns, row['duration']]).encode()).hexdigest()


def inventory(path):
    result = []
    with path.open() as handle:
        for row in csv.reader(handle, delimiter='\t'):
            if not row:
                continue
            if len(row) != 7:
                raise ValueError('Invalid inventory row; export again')
            db, pid, title, artist, album, duration, local = row
            result.append(dict(database_id=db, persistent_id=pid, title=title, artist=artist,
                               album=album, duration=float(duration.replace(',', '.')), path=local))
    if not result or len({x['persistent_id'] for x in result}) != len(result):
        raise ValueError('Empty inventory or duplicate persistent ID')
    return result


def measure_envelopes(envelopes, rate, duration, decoded):
    """Original v2 window voting: isolated missing attacks do not split tempo regions."""
    import numpy as np
    from scipy import signal
    segments = []
    for a in np.arange(0, duration, S['window_seconds']):
        b = min(a+S['window_seconds'], duration)
        center = (a+b)/2
        left, right = max(0, center-S['context_seconds']/2), min(decoded, center+S['context_seconds']/2)
        votes = []
        if a < decoded-2:
            for env in envelopes:
                e = env[int(left*rate):int(right*rate)]
                if len(e) < rate*4 or e.max() < 1e-5:
                    continue
                for threshold in (.2, .35, .5):
                    peaks, _ = signal.find_peaks(e, distance=int(rate*.27),
                        prominence=max(np.quantile(e, .95)*threshold, 1e-7))
                    intervals = np.diff(peaks)/rate
                    valid = intervals[(intervals >= .29) & (intervals <= .9)]
                    if len(valid) < 6:
                        continue
                    median = float(np.median(valid))
                    regular = valid[abs(valid-median) < .035]
                    if len(regular)/len(valid) >= .65:
                        votes.append(60/float(np.mean(regular)))
        # Inclusive upper bound at 185 BPM; original v2 onset detector unchanged.
        target = [v for v in votes if S['bpm_min']-.5 <= v <= S['bpm_max'] + 1e-9]
        yes = len(votes) >= 6 and len(target)/len(votes) >= .8
        status = 'Target range' if yes else ('Other tempo' if len(votes) >= 6 and len(target)/len(votes) <= .2 else 'Uncertain')
        segments.append(dict(start=round(float(a),2), end=round(float(b),2), status=status,
            bpm=round(float(np.median(votes)),2) if votes else None,
            votes=[round(v,2) for v in votes]))
    seconds = sum(s['end']-s['start'] for s in segments if s['status']=='Target range')
    percent = 100*seconds/duration
    accepted = [s for s in segments if s['status']=='Target range']
    bpm = round(float(np.median([s['bpm'] for s in accepted])),2) if accepted else None
    return dict(passes=bool(percent >= S['coverage_percent']), target_percent=round(percent,3), bpm=bpm,
                segments=segments, method=METHOD_VERSION)


def analyze_audio(path, metadata_duration):
    import numpy as np
    from scipy import signal
    if metadata_duration > S['max_track_seconds']:
        return dict(skipped='Duration exceeds configured maximum', passes=False)
    from audio_io import decode_audio
    raw, analysis_duration, diagnostics = decode_audio(path,metadata_duration)
    y = np.frombuffer(raw,dtype='<f4')
    sr, hop = 11025, 64
    rate = sr/hop
    if len(y) < sr*12:
        raise ValueError('Less than 12 seconds of decodable audio')
    f, _, z = signal.stft(y,fs=sr,nperseg=1024,noverlap=1024-hop)
    mag = np.abs(z)
    envelopes = []
    energies = []
    for lo,hi in [(30,160),(40,250),(30,100)]:
        energies.append(np.mean(mag[(f>=lo)&(f<=hi)]**2, axis=0))
        band = np.log1p(mag[(f>=lo)&(f<=hi)]*100)
        e = np.maximum(np.diff(band,axis=1),0).sum(axis=0)
        envelopes.append(np.maximum(e-signal.medfilt(e,51),0))
    original = measure_envelopes(envelopes,rate,metadata_duration,len(y)/sr)
    from bass_crosscheck import measure
    historical_original = None
    if analysis_duration != metadata_duration:
        historical_original = original
        original = measure_envelopes(envelopes,rate,analysis_duration,len(y)/sr)
    result = measure(original,energies,rate,analysis_duration,len(y)/sr)
    result.update(diagnostics)
    result['analysis_duration'] = analysis_duration
    if historical_original is not None:
        result['historical_original'] = historical_original
    result['decoded_duration'] = round(len(y)/sr,3)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--input-tsv', type=Path)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    state = args.state_dir
    state.mkdir(parents=True, exist_ok=True)
    previous = json.loads((state/'committed.json').read_text()) if (state/'committed.json').exists() else None
    if args.input_tsv:
        export = args.input_tsv
    else:
        export = state/'inventory.tsv'
        subprocess.run(['osascript', str(Path(__file__).with_name('export-library.applescript')), str(export)], check=True)
    rows = inventory(export)
    cache_path = state/'audio-cache.json'
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    old_rows = {x['persistent_id']: x for x in previous['rows']} if previous else {}
    old_hits = {x['persistent_id'] for x in previous['rows'] if x.get('passes')} if previous else set()
    errors = []
    count = {'analyzed': 0, 'cached': 0, 'skipped': 0}

    def worker(row):
        if row['duration'] > S['max_track_seconds']:
            return dict(row, skipped='Duration exceeds configured maximum', passes=False), None, None, 'skipped'
        try:
            row = row.copy()
            if not Path(row['path']).exists():
                old_path = Path(row['path'])
                alternative = Path.home()/'Music/Medien/Music/Compilations'/row['album']/old_path.name
                if not alternative.is_file():
                    raise FileNotFoundError(row['path'])
                duration = float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(alternative)],text=True).strip())
                if abs(duration-row['duration'])>2:
                    raise ValueError('Alternative file duration differs; identity not confirmed')
                row['library_path'] = row['path']
                row['path'] = str(alternative)
            key = identity(row)
            if not args.refresh and key in cache:
                return dict(row, **cache[key], analysis_file_signature=key), None, None, 'cached'
            result = analyze_audio(row['path'], row['duration'])
            if identity(row) != key:
                raise ValueError('File changed during analysis')
            return dict(row, **result, analysis_file_signature=key), key, result, 'analyzed'
        except Exception as exc:
            return dict(row, error=str(exc), passes=False), None, None, 'error'

    results = []
    dirty_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i, (x, key, measurement, status) in enumerate(pool.map(worker, rows), 1):
            results.append(x)
            if key:
                cache[key] = measurement
                dirty_count += 1
            if status == 'error':
                errors.append(dict(persistent_id=x['persistent_id'], title=x['title'], error=x['error']))
            else:
                count[status] += 1
            if i % 50 == 0:
                if dirty_count >= 100:
                    write_json(cache_path, cache)
                    dirty_count = 0
                print(f'{i}/{len(rows)} checked', flush=True)
    if dirty_count:
        write_json(cache_path, cache)
    # Reuse individual uncertainty reviews only for this exact method/file.
    reviews = []
    previous_reviews = {r["persistent_id"]: r for r in (previous or {}).get("selection_reviews", [])}
    for row in results:
        review = previous_reviews.get(row["persistent_id"])
        if not review or review.get("method") != METHOD_VERSION or row.get("skipped") or row.get("error"):
            continue
        if identity(row) != review["file_signature"]:
            errors.append(dict(persistent_id=row["persistent_id"],title=row["title"],error="File changed since individual review; review required"))
            continue
        row["automatic_passes"] = row["passes"]
        row["passes"] = False
        row["selection_review"] = review
        reviews.append(review)
    new_ids = set(x['persistent_id'] for x in rows) - set(old_rows) if previous else set()
    hits = [x for x in results if x.get('passes')]
    delta = dict(method=METHOD_VERSION, initial_migration=previous is None,
                 counts=dict(total=len(rows), hits=len(hits), **count), errors=errors, selection_reviews=reviews,
                 new_library_tracks=[x for x in results if x['persistent_id'] in new_ids],
                 new_matching_library_tracks=[x for x in hits if x['persistent_id'] in new_ids],
                 newly_matching_existing=[x for x in hits if x['persistent_id'] not in old_hits and x['persistent_id'] not in new_ids],
                 no_longer_matching=sorted(old_hits - {x['persistent_id'] for x in hits}),
                 removed_from_library=sorted(set(old_rows) - {x['persistent_id'] for x in rows}))
    write_json(state/'delta.json', delta)
    write_json(state/'pending.json', dict(method=METHOD_VERSION, rows=results, errors=errors, selection_reviews=reviews, timestamp=time.time()))
    if errors:
        # Do not leave an installable stale proposal around after a failed run.
        raise RuntimeError(f'{len(errors)} analysis errors; do not apply metadata. See delta.json')
    print(json.dumps(delta['counts'], ensure_ascii=False), flush=True)
    print('Analysis:', state/'pending.json')


if __name__ == '__main__':
    main()
