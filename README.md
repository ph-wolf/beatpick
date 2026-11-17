# beatpick

**Find your rhythm. AI-assisted playlists for Apple Music.**

Whether you are running, cycling, or working out, the right beat can help you keep your pace. But finding music at that tempo starts with a more basic problem: the BPM field in your local music files may be empty. Without tempo metadata, filtering your Apple Music library by BPM is not much help.

beatpick analyses your local audio to find tracks that fit your chosen tempo range and can write the results to Apple Music. It also looks beyond a single BPM value: a long ambient intro, a slow breakdown, or a change in tempo can make a track less suitable for a steady workout. You choose how much of each track must match your target range.

**Choose how much of a track must match your pace—not just a single BPM value.**

Preview the results, optionally write BPM values, and use them to build a Smart Playlist in Apple Music. Optional audio-based duplicate detection helps you avoid repeated recordings across your selection. Sync the playlist to your supported devices, and take your rhythm with you.

```text
Local audio → beatpick CLI → optional AI skill → Apple Music Smart Playlist → devices
```

## Install

Requires macOS and a local Apple Music library with readable audio files. DRM-protected streaming files are not supported. Homebrew installs Python, FFmpeg, and the analysis dependencies; no separate Python environment is needed for everyday use.

```sh
brew install ph-wolf/tap/beatpick
beatpick --version
```

### Automatic first-run setup

Since version `0.2.1`, setup happens automatically during the first interactive run. No separate `init` command, manual directory creation, or config copying is needed.

```sh
beatpick run
```

If no configuration exists, an interactive `run` asks for your local music folder, genre/album/artist selection (or explicitly all local tracks), target BPM range, minimum coverage, and whether to prepare BPM and duplicate-comment updates. It creates a commented `~/.beatpick/config.yaml` and **continues directly with the analysis**. It does not merely create a file and stop. Nothing is written to Music unless you explicitly request `apply` or `run --apply`.

You do not need to create directories or copy configuration files. Existing files are never overwritten; cancelling setup before it finishes leaves no new config behind. With the generated `state_dir: ./data`, results live under `~/.beatpick/data/`. Your configuration and state are independent of the development checkout and Homebrew upgrades.

Subsequent `beatpick run` and `beatpick apply` commands discover the saved configuration automatically. A config in the current working directory takes precedence over the personal one. Use `--config /path/to/other.yaml` to select another configuration or `--no-config` to use CLI settings only.

Noninteractive and `--json` calls never start a setup dialogue. Without an existing config, supply `--config`, `--select`, or `--all`; otherwise beatpick exits with actionable instructions and creates no files. For example, a complete CLI selection works without configuration:

```sh
beatpick run --no-config --media-root ~/Music \
  --select '{field: genre, equals: Trance}' --no-duplicates
```

Allow your terminal to control Music when macOS requests Automation access. Audio analysis stays local. The application does not modify audio tempo.

To update the CLI and its bundled skill together:

```sh
brew update
brew upgrade beatpick
```

Homebrew installs a versioned release rather than a live development checkout. Uncommitted changes and ordinary pushes do not change your installed version.

## Quick start

```sh
# Analyse and prepare a preview; no Music metadata is changed.
beatpick run --write-bpm
# Inspect ~/.beatpick/data/delta.json and metadata-plan.json, then apply the same settings.
beatpick apply --write-bpm
# Or explicitly combine analysis and application.
beatpick run --write-bpm --apply
```

`write_bpm` defaults to false. `duplicates.enabled` defaults to true and independently controls duplicate-comment updates when applying. Set `--no-duplicates` to leave all comments unchanged. Analysis and preview never write Music metadata. The application does not create playlists or edit audio tempo. Metadata writes go through Apple Music; direct ID3 editing is not provided.

## Configuration

The commented [config.example.yaml](config.example.yaml) explains each setting next to its value. A configuration file is optional: a CLI selection can be supplied directly. Configuration precedence is `--config` (when supplied), otherwise `./config.yaml`, otherwise `~/.beatpick/config.yaml`. CLI values override the selected file. `--no-config` skips discovery and first-run setup; it is mutually exclusive with `--config`. An explicitly supplied missing config is an error, not a request to create one.

### Configuration reference

All individual settings except the selection have omission defaults. **Optional means the key can be omitted; blank is not the same as omitted.** A blank YAML value (`key:`) is `null`. Section headings (`analysis`, `library`, `duplicates`) must contain mappings when present; omit the entire section instead of leaving its heading blank.

| YAML key | Meaning / unit | Default if omitted | Required? / valid values | CLI equivalent |
|---|---|---|---|---|
| `analysis.bpm_min` | Lower target tempo, BPM; includes 0.5 BPM rounding tolerance | `165` | Optional; 90 ≤ min ≤ max ≤ 200 | `--bpm-min` |
| `analysis.bpm_max` | Inclusive upper target tempo, BPM | `185` | Optional; 90 ≤ min ≤ max ≤ 200 | `--bpm-max` |
| `analysis.coverage_percent` | Minimum matching share of the entire track, percent | `50` | Optional; > 0 and ≤ 100 | `--coverage-percent` |
| `analysis.window_seconds` | Playback time represented by one decision, seconds | `4` | Optional; positive | `--window-seconds` |
| `analysis.context_seconds` | Surrounding audio examined for each decision, seconds | `12` | Optional; ≥ 4 and ≥ window size | `--context-seconds` |
| `analysis.max_track_seconds` | Maximum track duration before skipping, seconds | `720` | Optional; positive; exact limit is allowed | `--max-track-seconds` |
| `library.media_root` | Folder containing eligible local audio files | `~/Music` | Optional; a non-empty path | `--media-root` |
| `library.select` | Metadata rules selecting tracks to analyse | None | Required unless using CLI `--select`, explicit `--all`, or `library.all: true` | `--select` |
| `library.all` | Explicitly allow all local files beneath the media root when no selector is present | `false` | Optional; boolean; a present selector still restricts the selection | `--all` |
| `state_dir` | Persistent JSON state and backup folder | `./data` | Optional; a non-empty path | `--state-dir` |
| `write_bpm` | Allow BPM changes when applying | `false` | Optional; `true` / `false` | `--write-bpm` / `--no-write-bpm` |
| `duplicates.marker` | Own standalone duplicate-comment line | `beatpick-duplicate` | Optional; non-blank single-line string | `--duplicate-marker` |
| `duplicates.enabled` | Compare duplicate audio and maintain duplicate comments | `true` | Optional; `true` / `false` | `--duplicates` / `--no-duplicates` |

**Blank / null behavior:** Numeric values, paths, and `duplicates.marker` cannot be blank or `null`. Marker strings must not be whitespace-only or contain line breaks. An omitted or null `library.select` requires explicit `--all`, `library.all: true`, or a CLI selector. `library.all` must be a boolean, not blank/null. Boolean null values currently act as disabled rather than using the default; use explicit `true` or `false` instead. In particular, `duplicates.enabled: null` disables duplicates, whereas omitting `enabled` defaults to `true`.

Omitting BPM bounds uses **165–185 BPM**; it does not request unrestricted tempo analysis. There is currently no `analysis.target` block or general-purpose mode for filling every track's BPM field. Only qualifying tracks receive a BPM write value.

CLI values override the selected YAML configuration, which overrides defaults. Relative YAML paths resolve against the configuration directory; CLI paths resolve against the working directory. The active Music library supplies metadata; `media_root` restricts files to that directory rather than opening another `.musiclibrary`. Duplicate comments are independent of `write_bpm`: applying with BPM writing disabled can still change comments when duplicates are enabled.

### Counted windows and audio context

`window_seconds` and `context_seconds` answer different questions: **how much playback time does this decision represent, and how much audio is examined to make it?** With the defaults, each decision counts four seconds, using twelve seconds of surrounding audio.

For the counted window from 20 to 24 seconds, the midpoint is 22 seconds. The detector examines six seconds on either side, from 16 to 28:

```text
Song time:   16      20   22   24      28 seconds
             |-------|----|----|-------|
Counted window:      [ 4 sec. ]
Audio examined:
             [       12 sec.         ]
```

The next counted window, 24–28 seconds, uses audio from 20–32 seconds. **Examined contexts overlap; counted playback time does not.** The context supplies surrounding beats for a more stable decision. It does not require four seconds of perfectly detected, uninterrupted beats. At the beginning and end of the audio, the examined context is clipped; the last counted window covers only the remaining playback time.

`max_track_seconds` is separate: tracks longer than that limit are skipped before decoding. A track exactly at the limit is allowed.

### How percentage coverage works

`coverage_percent` specifies the minimum percentage of the **entire track** that must be confirmed within the target BPM range. For example:

| A 240-second track | Playback time |
|---|---:|
| Confirmed within the target BPM range | 180 seconds |
| Outside the range, silent, or uncertain | 60 seconds |
| Total | 240 seconds |
| Matching coverage: 180 ÷ 240 × 100 | **75%** |

With `coverage_percent: 50`, this track qualifies; with `coverage_percent: 80`, it does not. Separate matching sections are added together: they need not form one continuous passage. Slower, faster, silent, and uncertain sections remain in the total duration but do not count as matching.

Each decision contributes only its counted window—four seconds by default—even though it examines twelve seconds. Context overlap never counts playback time twice. Near a tempo change, surrounding audio can influence a decision, so coverage is an estimate rather than a second-exact boundary measurement. The threshold is checked before rounding the displayed percentage.

**Coverage decides whether a track qualifies. BPM describes the estimated tempo of its confirmed target windows.** They are different results: 75% coverage is not a BPM value. When enabled, the Music BPM field receives the rounded median tempo of confirmed target windows, not a whole-track tempo or the coverage percentage.

### Selecting tracks and CLI overrides

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

No artist or album filter is built in. A selector or an explicit all-tracks choice is required. First-run setup saves an all-tracks choice as `library.all: true`; it never assumes the whole library by default.

```sh
beatpick run --media-root ~/Music --state-dir ./data \
  --bpm-min 165 --bpm-max 185 --coverage-percent 50 \
  --select '{field: genre, equals: Trance}' --no-duplicates --json
```

`--refresh` recomputes audio results. `--json` returns detailed results on stdout; progress goes to stderr. Errors return a nonzero status.

## Smart Playlist and devices

For a 165–185 BPM workout, create a Smart Playlist in Music on your Mac with **all** conditions:

- BPM is in the range 165 to 185.
- Comment does not contain your configured duplicate marker (`beatpick-duplicate` by default).
- Enable live updating.

beatpick writes the rounded median tempo of confirmed target windows, not a global tempo or percentage. It enforces coverage during analysis; Music cannot infer that coverage from BPM alone. Existing BPM values of tracks that stop qualifying are reported but never cleared automatically: review these before relying on a BPM-only playlist.

With an Apple Music subscription, enable Sync Library on your Mac and supported devices using the same Apple Account. Let local tracks finish matching/uploading, then check playlist availability and download for offline exercise. Files that cannot upload or match will not become available simply because a playlist exists. Smart Playlist rules are not universally synchronized as executable rules; maintain them on your Mac and verify resulting contents on each device. Without a subscription, use supported manual device synchronization instead.

See Apple's [Sync Library instructions](https://support.apple.com/en-ca/118285) and [library synchronization limitations](https://support.apple.com/en-lamr/guide/music/musa3dd5209/mac). beatpick does not perform synchronization itself.

## Optional AI skill: installation and usage

The portable [skill/SKILL.md](skill/SKILL.md) lets Codex or Claude Code operate the CLI and explain results. It contains generic instructions, no personal library data. The CLI owns the analysis; no separate model API integration is required by beatpick.

The Homebrew package includes the skill from the same release as the CLI. Complete `beatpick run` once in an interactive terminal to create your personal config, or provide your own configuration. Automated agent calls use `--json` and do not start the setup dialogue. Use a local agent on the Mac with Music and your audio; cloud sessions do not automatically have access to it.

### Install for Codex

Link the bundled skill once:

```sh
mkdir -p ~/.agents/skills
ln -s "$(brew --prefix beatpick)/share/beatpick/skill" ~/.agents/skills/beatpick
```

Start a new session, then invoke `$beatpick`. See the official [Codex skill documentation](https://developers.openai.com/codex/skills).

### Install for Claude Code

```sh
mkdir -p ~/.claude/skills
ln -s "$(brew --prefix beatpick)/share/beatpick/skill" ~/.claude/skills/beatpick
```

Start a new session, then invoke `/beatpick`. See the official [Claude Code skill documentation](https://code.claude.com/docs/en/skills).

These links use Homebrew's stable `opt` path, so `brew upgrade beatpick` updates both CLI and skill without relinking. If the destination already exists, inspect and preserve any custom skill before replacing it. Homebrew does not create links inside your agent configuration automatically. No `AGENTS.md` or `CLAUDE.md` is needed. The skill uses an explicitly supplied config, otherwise checks `config.yaml` in the working directory and then `~/.beatpick/config.yaml`.

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

Duplicates require conservative version compatibility, at least 97% shared duration, waveform correlation ≥0.94 overall and ≥0.90 in every quarter. All pairs within a group must agree. The highest target percentage wins; persistent ID breaks ties. Other qualifying copies receive a standalone comment line configured by `duplicates.marker` (default `beatpick-duplicate`). Do not change this value after applying it without migrating existing managed markers and updating the playlist rule. The CLI rejects marker changes when the confirmed state still tracks managed entries. Unrelated comment text is preserved.

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

Work on the CLI and `skill/SKILL.md` in the development checkout. `uv` is a development dependency only:

```sh
brew install uv
uv sync
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q beatpick
```

Tests use synthetic audio and simulated Music calls; they do not modify your Music library. Audio and personal state must never be committed.

Licensed under [MIT](LICENSE).

## Releases and versioning

The central version is `[project].version` in `pyproject.toml`. `beatpick --version` reads installed package metadata; the bundled skill shares that version.

Use `MAJOR.MINOR.PATCH`: fixes increment PATCH, new features MINOR, and incompatible stable changes MAJOR. During `0.x`, document incompatible changes explicitly. A release is a deliberate step, separate from everyday commits and pushes:

1. Update `pyproject.toml`, refresh `uv.lock`, run tests and inspect the public diff.
2. Commit and create the corresponding `vX.Y.Z` tag and GitHub Release. Include a source archive containing the CLI, skill, and example configuration.
3. Update `Formula/beatpick.rb` in [ph-wolf/homebrew-tap](https://github.com/ph-wolf/homebrew-tap) with the release asset URL and SHA-256; test installation and `brew test` before publishing the formula change.
4. Users run `brew update` and `brew upgrade beatpick` when ready.

For local development, use `uv run beatpick ...` inside the checkout. Use the plain installed `beatpick` command for normal operation. Tests and development previews should use a separate `--state-dir` so experiments do not overwrite everyday state.
