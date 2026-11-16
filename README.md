# beatpick

**Find music that keeps up with your rhythm.**

Finding music for a run or a cycling session sounds simple: pick tracks with the right BPM. But a single tempo value rarely tells the whole story. A track might have a long ambient intro, a slow breakdown, or only a short section that matches your pace. Albums can also contain the same recording several times.

beatpick selects local Apple Music tracks by how much of their playing time matches your chosen tempo range. Preview the results, optionally write BPM values and duplicate markers, and use those fields in a Smart Playlist for your next workout.

```text
Local audio → beatpick CLI → optional AI skill → Apple Music Smart Playlist → devices
```

## Install

Requires macOS, Python 3.11+, Apple Music, `ffmpeg` and `ffprobe` on PATH. Audio analysis stays local. DRM-protected streaming files are not supported.

```sh
brew install ffmpeg uv
uv tool install .
cp config.example.yaml config.yaml
beatpick --help
```

Allow your terminal to control Music when macOS requests Automation access. Edit `config.yaml` to match your actual music; the example artists and albums are fictional. Your personal `config.yaml` and `data/` are ignored by Git.

## Quick start

```sh
# Analyse and prepare a preview; no Music metadata is changed.
beatpick run --config config.yaml --write-bpm
# Inspect data/delta.json and data/metadata-plan.json, then apply the same settings.
beatpick apply --config config.yaml --write-bpm
# Or explicitly combine analysis and application.
beatpick run --config config.yaml --write-bpm --apply
```

`write_bpm` defaults to false. `duplicates.enabled` defaults to true and independently controls duplicate-comment updates when applying. Set `--no-duplicates` to leave all comments unchanged. Analysis and preview never write Music metadata. The application does not create playlists or edit audio tempo. Metadata writes go through Apple Music; direct ID3 editing is not provided.

## Configuration

See [config.example.yaml](config.example.yaml) for every setting. All settings have equivalent flags: `--bpm-min`, `--bpm-max`, `--coverage-percent`, `--window-seconds`, `--context-seconds`, `--max-track-seconds`, `--media-root`, `--state-dir`, `--select`, `--write-bpm` / `--no-write-bpm`, and `--duplicates` / `--no-duplicates`.

CLI values override the explicit YAML configuration, which overrides defaults. No configuration is loaded implicitly. Relative YAML paths resolve against the configuration directory; CLI paths resolve against the working directory. The default data directory is `./data`. The active Music library supplies metadata; `media_root` restricts files to that directory. It does not open another `.musiclibrary`.

Selectors support `all`, `any`, `not` and case-insensitive `equals`, `contains`, `regex` on `genre`, `album`, `artist`, `title`:

```yaml
library:
  media_root: ~/Music
  select:
    all:
      - field: genre
        equals: Trance
      - any:
          - field: artist
            equals: The Lunar Echoes
          - field: album
            contains: Neon Horizon
```

No artist or album filter is built in. A selector or explicit `--all` is required.

```sh
beatpick run --media-root ~/Music --state-dir ./data \
  --bpm-min 165 --bpm-max 185 --coverage-percent 50 \
  --select '{field: genre, equals: Trance}' --no-duplicates --json
```

`--refresh` recomputes audio results. `--json` returns detailed results on stdout; progress goes to stderr. Errors return a nonzero status.

## Smart Playlist and devices

For a 165–185 BPM workout, create a Smart Playlist in Music on your Mac with **all** conditions:

- BPM is in the range 165 to 185.
- Comment does not contain `beatpick-duplicate`.
- Enable live updating.

beatpick writes the rounded median tempo of confirmed target windows, not a global tempo or percentage. It enforces coverage during analysis; Music cannot infer that coverage from BPM alone. Existing BPM values of tracks that stop qualifying are reported but never cleared automatically: review these before relying on a BPM-only playlist.

With an Apple Music subscription, enable Sync Library on your Mac and supported devices using the same Apple Account. Let local tracks finish matching/uploading, then check playlist availability and download for offline exercise. Files that cannot upload or match will not become available simply because a playlist exists. Smart Playlist rules are not universally synchronized as executable rules; maintain them on your Mac and verify resulting contents on each device. Without a subscription, use supported manual device synchronization instead.

See Apple's [Sync Library instructions](https://support.apple.com/en-ca/118285) and [library synchronization limitations](https://support.apple.com/en-lamr/guide/music/musa3dd5209/mac). beatpick does not perform synchronization itself.

## Optional AI skill

An AI skill can invoke these same commands, explain new and removed matches, and summarize the preview before applying an authorized update. The CLI owns analysis and verification, so it also works without AI. No skill integration is installed by this repository.

## Architecture and method

`cli` resolves configuration, selection, and a per-directory process lock. `refresh` runs incremental analysis; `audio_io` validates decoding and trailing MP3 metadata. `bass_crosscheck` combines onset estimates and bass-energy evidence. `recordings` verifies duplicate audio. `metadata` prepares and verifies Music changes through a JavaScript Automation bridge.

Defaults preserve the original v6 method: 4-second weighted windows with 12-second context, three bass bands, onset voting and bass autocorrelation cross-checks. At least 50% of the entire duration must qualify between 165 and 185 BPM. The lower bound includes a 0.5 BPM rounding tolerance; the upper bound is exact. Pauses and uncertain windows stay in the denominator. Missing individual kicks do not impose an additional continuous-beat requirement. There is no automatic tempo doubling or 4:3 reinterpretation.

The configurable BPM range is limited to 90–200; this is a technical boundary, not a guarantee of reliable detection for every genre. Context must be at least four seconds and at least as long as the window. Tracks longer than the configured maximum (720 seconds by default) are skipped before decoding. Decodable audio shorter than 12 seconds is rejected. Estimates can confuse rhythmic bass figures with the beat: inspect ambiguous results and do not treat percentages as ground truth.

Duplicates require conservative version compatibility, at least 97% shared duration, waveform correlation ≥0.94 overall and ≥0.90 in every quarter. All pairs within a group must agree. The highest target percentage wins; persistent ID breaks ties. Other qualifying copies receive a standalone `beatpick-duplicate` comment line. Unrelated comment text is preserved.

## State, recovery and migration

YAML is for human configuration; JSON stores machine-managed state:

- `audio-cache.json`, `recording-cache.json`: reusable measurements and pair comparisons.
- `pending.json`, `delta.json`: analysis and differences.
- `metadata-plan.json`: exact before/after metadata preview.
- `committed.json`: last verified application.
- `metadata-backup-*.json`: pre-application recovery evidence.

Decoder scratch files live under `data/tmp/`. Keep the other state files between runs. Pass an existing legacy directory through `--state-dir` to use its committed baseline; incompatible audio signatures are recomputed. Originals are not deleted. A new preview replaces pending planning files, so retain backups of valuable historical state.

Before applying, beatpick checks configuration, analysis hash, file signatures, persistent IDs, identities, and previous metadata. It writes a backup and verifies Music readback before committing success. On failure, inspect the backup and live values, generate a fresh preview, and apply remaining differences. Never blindly replay a stale plan. Files changed by Music metadata writes may require reanalysis.

## Development

```sh
uv sync
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q beatpick
```

Tests use synthetic audio and simulated Music calls; they do not modify your Music library. Audio and personal state must never be committed.

Licensed under [MIT](LICENSE).
