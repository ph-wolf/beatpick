# beatpick

**Turn your Apple Music library into workout playlists that match your rhythm.**

Whether you are running, cycling, or working out, the right beat can help you keep your pace. But finding music at that tempo starts with a more basic problem: the BPM field in your local music files may be empty. Without tempo metadata, filtering your Apple Music library by BPM is not much help.

beatpick analyses your local audio to find tracks that fit your chosen tempo range and can write the results to Apple Music. It also looks beyond a single BPM value: a long ambient intro, a slow breakdown, or a change in tempo can make a track less suitable for a steady workout. You choose how much of each track must match your target range.

Preview the results, optionally write BPM values, and use them to build a Smart Playlist in Apple Music. Optional audio-based duplicate detection helps you avoid repeated recordings across your selection. Sync the playlist to your supported devices, and take your rhythm with you.

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

## Optional AI skill: installation and usage

The portable [skill/SKILL.md](skill/SKILL.md) lets Codex or Claude Code operate the CLI and explain results. It contains generic instructions, no personal library data. The CLI owns the analysis; no separate model API integration is required by beatpick.

Install the CLI first and prepare your personal `config.yaml`. Use a local agent session on the Mac that has access to Music and your audio files. A cloud session does not automatically have access to that library.

### Install for Codex

From the root of your beatpick checkout, copy the skill into your personal skills directory:

```sh
mkdir -p ~/.agents/skills/beatpick
cp skill/SKILL.md ~/.agents/skills/beatpick/SKILL.md
```

Start a new session, then invoke it with `$beatpick`. See the official [Codex skill documentation](https://developers.openai.com/codex/skills).

### Install for Claude Code

From the same checkout:

```sh
mkdir -p ~/.claude/skills/beatpick
cp skill/SKILL.md ~/.claude/skills/beatpick/SKILL.md
```

Start a new session and invoke `/beatpick`. See the official [Claude Code skill documentation](https://code.claude.com/docs/en/skills).

These commands copy the skill; repeat the copy after updating the repository. They replace an existing skill with the same name, so preserve any custom version first. Installing the skill does not install the CLI or change your configuration. No `AGENTS.md` or `CLAUDE.md` is needed.

### Example prompts

For Codex, use `$beatpick`; for Claude Code, replace it with `/beatpick`. Provide your actual configuration path in place of the example placeholder.

**Preview only:**

```text
$beatpick Use /path/to/config.yaml to analyse my selected tracks.
Explain new matches, removed matches, and proposed metadata changes.
Do not change Apple Music metadata.
```

**Try a different tempo without editing the configuration:**

```text
$beatpick Preview tracks at 170–180 BPM with at least 60% coverage,
using /path/to/config.yaml. Keep its selection unchanged.
Do not edit the configuration or apply metadata changes.
```

**Update BPM, leaving comments untouched:**

```text
$beatpick Using /path/to/config.yaml, analyse the selected tracks,
inspect the preview, and apply BPM updates only.
Leave all comments unchanged and report the verified changes.
```

**Apply the configured BPM and duplicate settings:**

```text
$beatpick Using /path/to/config.yaml, refresh the analysis, inspect
its preview, and apply the configured metadata updates if analysis
succeeds. Explain duplicate groups and any remaining issues.
```

Preview requests never authorize Music writes. Explicit update requests authorize the corresponding apply step. The skill does not create Smart Playlists or sync devices; follow the playlist instructions above after applying results.

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
