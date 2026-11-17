"""Configuration and command-line orchestration."""
import argparse
from importlib.metadata import version
import contextlib
import fcntl
import hashlib
import json
import re
import subprocess
import sys
import audio_io
from pathlib import Path
import yaml
from settings import VALUES
import refresh
import metadata
from configuration import DEFAULT_ANALYSIS, locate


def matches(rule, row):
    if len(rule) == 1:
        if 'all' in rule:
            return all(matches(r, row) for r in rule['all'])
        if 'any' in rule:
            return any(matches(r, row) for r in rule['any'])
        if 'not' in rule:
            return not matches(rule['not'], row)
    field = rule['field']
    if field not in ('genre', 'album', 'artist', 'title'):
        raise ValueError('Unsupported selection field: ' + field)
    value = str(row.get(field, ''))
    ops = set(rule) - {'field'}
    if len(ops) != 1:
        raise ValueError('A selection leaf requires exactly one operator')
    op = ops.pop()
    target = str(rule[op])
    if op == 'equals':
        return value.casefold() == target.casefold()
    if op == 'contains':
        return target.casefold() in value.casefold()
    if op == 'regex':
        return re.search(target, value, re.I) is not None
    raise ValueError('Unknown selection operator: ' + op)


def path(value, base):
    result = Path(value).expanduser()
    return (result if result.is_absolute() else base / result).resolve()


def main():
    parser = argparse.ArgumentParser(description='Select Apple Music tracks by audio tempo coverage.')
    parser.add_argument('--version', action='version', version='beatpick ' + version('beatpick'))
    parser.add_argument('command', choices=['run', 'apply'])
    config_options = parser.add_mutually_exclusive_group()
    config_options.add_argument('--config', type=Path)
    config_options.add_argument('--no-config', action='store_true', help='Ignore automatic configuration discovery; use CLI settings only')
    for key in VALUES:
        parser.add_argument('--' + key.replace('_', '-'), type=float)
    for key in ('state-dir', 'media-root', 'select', 'duplicate-marker'):
        parser.add_argument('--' + key)
    for key in ('write-bpm', 'duplicates'):
        parser.add_argument('--' + key, action=argparse.BooleanOptionalAction, default=None)
    for key in ('all', 'refresh', 'apply', 'json'):
        parser.add_argument('--' + key, action='store_true')
    args = parser.parse_args()
    try:
        args.config = locate(args)
        config = yaml.safe_load(args.config.read_text()) or {} if args.config else {}
        base = args.config.resolve().parent if args.config else Path.cwd()
        for key in VALUES:
            VALUES[key] = getattr(args, key) if getattr(args, key) is not None else config.get('analysis', {}).get(key, DEFAULT_ANALYSIS[key])
        if not 90 <= VALUES['bpm_min'] <= VALUES['bpm_max'] <= 200:
            raise ValueError('BPM bounds must be between 90 and 200')
        if not 0 < VALUES['coverage_percent'] <= 100 or min(VALUES.values()) <= 0:
            raise ValueError('Coverage must be in (0, 100] and durations must be positive')
        if VALUES['context_seconds'] < max(4, VALUES['window_seconds']):
            raise ValueError('Context must be at least four seconds and at least the window size')
        state = path(args.state_dir or config.get('state_dir', './data'), Path.cwd() if args.state_dir else base)
        root = path(args.media_root or config.get('library', {}).get('media_root', '~/Music'), Path.cwd() if args.media_root else base)
        rule = yaml.safe_load(args.select) if args.select else config.get('library', {}).get('select')
        include_all = args.all or config.get('library', {}).get('all', False)
        if not isinstance(include_all, bool):
            raise ValueError('library.all must be true or false')
        if not rule and not include_all:
            raise ValueError('Specify a selection rule or --all')
        if rule:
            matches(rule, {})
        write = args.write_bpm if args.write_bpm is not None else config.get('write_bpm', False)
        duplicates = args.duplicates if args.duplicates is not None else config.get('duplicates', {}).get('enabled', True)
        marker = metadata.validate_marker(args.duplicate_marker if args.duplicate_marker is not None else config.get('duplicates', {}).get('marker', metadata.MARKER))
        effective = dict(marker=marker, analysis=VALUES, root=str(root), select=rule, write_bpm=write, duplicates=duplicates)
        signature = hashlib.sha256(json.dumps(effective, sort_keys=True).encode()).hexdigest()
        state.mkdir(parents=True, exist_ok=True)
        (state / 'tmp').mkdir(exist_ok=True)
        audio_io.SCRATCH_DIR = str(state / 'tmp')
        with (state / '.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.command == 'run':
                (state / 'metadata-plan.json').unlink(missing_ok=True)
                script = Path(__file__).with_name('inventory.js')
                rows = json.loads(subprocess.check_output(['osascript', '-l', 'JavaScript', str(script)], text=True))
                rows = [r for r in rows if Path(r['path']).resolve().is_relative_to(root) and (not rule or matches(rule, r))]
                if not rows:
                    raise ValueError('No local tracks match the selection')
                old_inventory = refresh.inventory
                refresh.inventory = lambda _: rows
                refresh.sys = sys
                old = sys.argv
                sys.argv = ['refresh', '--state-dir', str(state), '--input-tsv', 'unused'] + (['--refresh'] if args.refresh else [])
                try:
                    with contextlib.redirect_stdout(sys.stderr):
                        refresh.main()
                finally:
                    sys.argv = old
                    refresh.inventory = old_inventory
                result = metadata.plan(state, write, duplicates, marker)
                result['config_signature'] = signature
                refresh.write_json(state / 'metadata-plan.json', result)
            if args.command == 'apply' or args.apply:
                plan = json.loads((state / 'metadata-plan.json').read_text())
                if plan.get('config_signature') != signature:
                    raise ValueError('Configuration changed; create a new preview')
                result = metadata.apply(state)
            print(json.dumps(result, indent=2) if args.json else f"Completed {args.command}. Results: {state}")
    except (EOFError, KeyboardInterrupt):
        print('beatpick: Interrupted.', file=sys.stderr)
        raise SystemExit(130) from None
    except Exception as exc:
        print(f'beatpick: {exc}', file=sys.stderr)
        raise SystemExit(1) from exc
