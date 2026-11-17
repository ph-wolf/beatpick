"""Preview and verify BPM and duplicate-comment updates; never writes playlists or vault."""
import argparse
import datetime
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import subprocess
from refresh import DEFAULT_STATE, METHOD_VERSION, identity, sha, write_json
from recordings import group_recordings

MARKER = 'beatpick-duplicate'
HERE = Path(__file__).parent


def validate_marker(marker):
    if not isinstance(marker, str) or not marker.strip() or any(c in marker for c in ('\n', '\r')):
        raise ValueError('Duplicate marker must be a non-empty single line')
    return marker


def comment_value(comment, duplicate, marker=MARKER):
    validate_marker(marker)
    # Own a standalone line only, preserve all other comment text exactly.
    lines = comment.splitlines(keepends=True)
    clean = ''.join(line for line in lines if line.rstrip('\r\n') != marker)
    if duplicate:
        return clean + ('' if not clean or clean.endswith(('\n', '\r')) else '\n') + marker
    return clean


def select_winners(groups):
    return [min(group, key=lambda row: (-row['target_percent'], row['persistent_id'])) for group in groups]


def music(mode, rows, state):
    request = state/'metadata-request.json'
    write_json(request, rows)
    output = subprocess.check_output(['osascript', '-l', 'JavaScript', str(HERE/'music-metadata.js'), mode, str(request)], text=True)
    result = json.loads(output)
    if len(result) != len(rows) or {r['persistent_id'] for r in result} != {r['persistent_id'] for r in rows}:
        raise ValueError('Incomplete Music export')
    return {r['persistent_id']: r for r in result}


def load_pending(state):
    pending = json.loads((state/'pending.json').read_text())
    if pending['errors'] or pending['method'] != METHOD_VERSION or not pending['rows']:
        raise ValueError('No valid current analysis')
    return pending


def plan(state, write_bpm=True, duplicates_enabled=True, marker=MARKER):
    validate_marker(marker)
    (state/'metadata-plan.json').unlink(missing_ok=True)
    pending = load_pending(state)
    source_hash = sha(state/'pending.json')
    hits = [r for r in pending['rows'] if r.get('passes')]
    for row in hits:
        if row.get('analysis_file_signature') != identity(row):
            raise ValueError('File changed since analysis; rerun analysis: '+row['persistent_id'])
    groups, evidence = group_recordings(hits, state, identity) if duplicates_enabled else ([[r] for r in hits], [])
    winners = {r['persistent_id'] for r in select_winners(groups)}
    duplicates = {r['persistent_id'] for r in hits} - winners
    previous = json.loads((state/'committed.json').read_text()) if (state/'committed.json').exists() else {}
    managed = set(previous.get('managed_comment_ids', []))
    if duplicates_enabled and managed and previous.get('duplicate_marker', MARKER) != marker:
        raise ValueError('Duplicate marker changed; migrate managed comment lines before changing it')
    # Include previous managed IDs to remove a stale marker after selection changes.
    rows = [r for r in pending['rows'] if r.get('passes') or r['persistent_id'] in managed]
    live = music('inspect', rows, state) if rows else {}
    changes = []
    for row in rows:
        before = live[row['persistent_id']]
        after = {key: before[key] for key in ('bpm', 'comment')}
        if write_bpm and row.get('passes'):
            after['bpm'] = int(Decimal(str(row['bpm'])).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        after['comment'] = comment_value(before['comment'], row['persistent_id'] in duplicates, marker) if duplicates_enabled else before['comment']
        changes.append(dict(row, before=before, after=after,
                            file_signature=identity(row) if not row.get('skipped') else None))
    if sha(state/'pending.json') != source_hash:
        raise ValueError('Analysis changed during planning')
    data = dict(duplicate_marker=marker, duplicates_enabled=duplicates_enabled, source_sha256=source_hash, rows=changes, duplicate_ids=sorted(duplicates),
                selected_ids=sorted(winners), groups=[[r['persistent_id'] for r in g] for g in groups if len(g)>1],
                evidence=evidence, previous_managed_ids=sorted(managed))
    write_json(state/'metadata-plan.json', data)
    return data


def verify_files(data):
    for row in data['rows']:
        if row['file_signature'] is not None and identity(row) != row['file_signature']:
            raise ValueError('Audio changed since preview: '+row['persistent_id'])


def apply(state):
    data = json.loads((state/'metadata-plan.json').read_text())
    pending = load_pending(state)
    if sha(state/'pending.json') != data['source_sha256']:
        raise ValueError('Analysis changed; create a new preview')
    verify_files(data)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = state/('metadata-backup-'+stamp+'.json')
    write_json(backup, data)
    # Bridge checks every current value against the preview before writing anything.
    live = music('apply', data['rows'], state) if data['rows'] else {}
    for row in data['rows']:
        if any(live[row['persistent_id']][k] != row['after'][k] for k in ('bpm','comment')):
            raise ValueError('Metadata verification failed; backup: '+str(backup))
    receipt = dict(source_sha256=data['source_sha256'], status='verified', backup=str(backup),
                   checked=len(data['rows']), bpm_changed=sum(r['before']['bpm']!=r['after']['bpm'] for r in data['rows']),
                   comments_changed=sum(r['before']['comment']!=r['after']['comment'] for r in data['rows']))
    write_json(state/'metadata-last-success.json', receipt)
    # Keep vanished IDs managed so their marker can be cleaned if they reappear.
    present = {r['persistent_id'] for r in pending['rows']}
    pending['duplicate_marker'] = data.get('duplicate_marker', MARKER)
    pending['managed_comment_ids'] = (sorted(set(data['duplicate_ids']) | (set(data['previous_managed_ids'])-present))
                                      if data.get('duplicates_enabled', True) else data['previous_managed_ids'])
    write_json(state/'committed.json', pending)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.apply:
        result = apply(args.state_dir)
    else:
        data = plan(args.state_dir)
        result = dict(checked=len(data['rows']), duplicate_groups=len(data['groups']),
                      duplicate_ids=data['duplicate_ids'], selected=len(data['selected_ids']))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
