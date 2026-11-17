"""Discover configuration and set up a new user's first analysis run."""
import os
from pathlib import Path
import sys

import yaml
from settings import VALUES

DEFAULT_ANALYSIS = VALUES.copy()


def ask(message, default=None):
    suffix = f' [{default}]' if default is not None else ''
    print(f'{message}{suffix}: ', end='', file=sys.stderr, flush=True)
    answer = input().strip()
    return answer or (str(default) if default is not None else '')


def number(message, default, valid):
    while True:
        try:
            value = float(ask(message, default))
            if valid(value):
                return value
        except ValueError:
            pass
        print('Please enter a number within the stated range.', file=sys.stderr)


def yes_no(message, default):
    while True:
        answer = ask(message, 'yes' if default else 'no').casefold()
        if answer in ('yes', 'y', 'no', 'n'):
            return answer in ('yes', 'y')
        print('Please enter yes or no.', file=sys.stderr)


def first_run(destination):
    print('Welcome to beatpick. Set up your first analysis; no Music metadata is changed unless you explicitly apply it.', file=sys.stderr)
    while True:
        media_root = Path(ask('Local music folder', '~/Music')).expanduser().resolve()
        if media_root.is_dir():
            break
        print('That folder does not exist. Enter a local audio folder.', file=sys.stderr)
    while True:
        field = ask('Select tracks by genre, album, artist, or all', 'genre').casefold()
        if field in ('genre', 'album', 'artist', 'all'):
            break
        print('Choose genre, album, artist, or all.', file=sys.stderr)
    library = {'media_root': str(media_root)}
    if field == 'all':
        library['all'] = True
    else:
        value = ''
        while not value:
            value = ask(f'{field.title()} to match' + (' (exact, ignoring case)' if field == 'genre' else ' (contains, ignoring case)'))
        library['select'] = {'field': field, 'equals' if field == 'genre' else 'contains': value}
    low = number('Minimum BPM (90-200)', 165, lambda v: 90 <= v <= 200)
    high = number(f'Maximum BPM ({low:g}-200)', 185 if low <= 185 else low, lambda v: low <= v <= 200)
    coverage = number('Minimum matching playback percentage (>0-100)', 50, lambda v: 0 < v <= 100)
    analysis = dict(DEFAULT_ANALYSIS, bpm_min=low, bpm_max=high, coverage_percent=coverage)
    config = {'analysis': analysis, 'library': library, 'state_dir': './data',
              'write_bpm': yes_no('Prepare BPM updates for an explicit apply', False),
              'duplicates': {'enabled': yes_no('Compare duplicate audio and prepare duplicate comments', True),
                             'marker': 'beatpick-duplicate'}}
    comments = {'analysis': 'Analysis settings; omitted values use defaults. Do not use blank/null values.',
                'window_seconds': 'Seconds counted per decision; examined contexts overlap, counted time does not.',
                'context_seconds': 'Surrounding audio examined per decision; at least 4 seconds and at least the window size.',
                'max_track_seconds': 'Longer tracks are skipped before decoding.',
                'coverage_percent': 'Minimum percentage of the entire track confirmed in the target BPM range.',
                'library': 'Your local file selection. Text matching ignores case.',
                'all': 'Explicitly include every local track beneath media_root.',
                'state_dir': 'Persistent state; relative to this config file, independent of the current directory.',
                'write_bpm': 'Only takes effect during apply or run --apply.',
                'duplicates': 'Independent of BPM writing; false leaves comments unchanged.',
                'marker': 'Own standalone comment line. Keep stable after applying it.'}
    lines = ['# Personal beatpick configuration. Existing files are never overwritten.\n']
    for line in yaml.safe_dump(config, sort_keys=False, allow_unicode=True).splitlines(keepends=True):
        key = line.strip().split(':', 1)[0]
        if key in comments:
            lines.append(' ' * (len(line) - len(line.lstrip())) + '# ' + comments[key] + '\n')
        lines.append(line)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError(f'Configuration appeared during setup; not overwritten: {destination}. Run again.') from exc
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(''.join(lines))
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    print(f'Saved {destination}. Continuing with analysis. Future runs use this configuration automatically.', file=sys.stderr)
    return destination


def locate(args):
    if args.no_config:
        return None
    if args.config is not None:
        return args.config.expanduser()
    for candidate in (Path.cwd() / 'config.yaml', Path.home() / '.beatpick/config.yaml'):
        if candidate.exists():
            return candidate
    # A complete CLI selection needs neither a config file nor an interactive setup.
    if args.select or args.all:
        return None
    if args.command == 'run' and not args.json and sys.stdin.isatty():
        return first_run(Path.home() / '.beatpick/config.yaml')
    raise ValueError('No configuration found. Run beatpick run in an interactive terminal for first-time setup, '
                     'or provide --config, --select, or --all. No files were created.')
