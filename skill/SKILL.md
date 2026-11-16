---
name: beatpick
description: Use the beatpick CLI to analyse local Apple Music tracks by tempo coverage, explain previews, and apply requested BPM or audio-duplicate metadata updates.
---

# beatpick

Use the installed `beatpick` CLI as the source of analysis and metadata decisions. Do not reimplement tempo detection, infer duplicates from names, or edit Music metadata directly.

## Configure and preview

- Requires a local Mac with Apple Music, readable local audio, FFmpeg, and the installed CLI. A remote agent without access to that Mac cannot operate its library.
- Locate the configuration explicitly provided by the user. Otherwise check for `config.yaml` in the working directory; ask for its location if absent. Do not substitute the fictional example configuration for personal settings.
- Inspect `beatpick --help` and the configuration before constructing commands. Resolve the config to an absolute path so later commands use the same file. CLI overrides take precedence over YAML.
- Preserve the requested selection and parameters. Do not broaden selection to `--all` unless requested. For a one-off change, use CLI overrides rather than modifying the configuration unless asked.
- Run `beatpick run --config /path/to/config.yaml --json` with any requested overrides. This writes local analysis and preview files, but no Music metadata.
- Read the JSON result and `delta.json` in the resolved state directory. Relative YAML state paths resolve against the config directory; CLI state paths resolve against the working directory.
- Summarize matching tracks, new and removed matches, skipped tracks, analysis errors, proposed BPM/comment changes, and duplicate groups. Percentages and BPM values are estimates; the written BPM is the median of confirmed target windows.

## Apply a requested update

A preview-only request never authorizes metadata writes. If the user requests updating BPM or duplicate comments, that authorizes the corresponding CLI apply operation; do not request the same permission again.

Use `--write-bpm` for requested BPM updates. Duplicate comments are independently controlled by `--duplicates` / `--no-duplicates`; for a BPM-only request, use `--no-duplicates`. For a duplicate-only request, use `--no-write-bpm --duplicates`. An unrestricted request to apply the configured preview follows the configuration.

First generate and inspect the preview with the intended settings, then run `beatpick apply --config /path/to/config.yaml --json` with exactly the same overrides. Never apply after an analysis error or bypass a stale-plan/configuration check. Do not invent reviews or change thresholds to force a track to qualify.

Report verified changes and any remaining errors. If application partially fails, inspect the backup and actual state and explain the failure. Do not blindly retry an old plan; prepare a fresh preview and stop if the same failure recurs.

## Boundaries

Do not create playlists or claim to sync devices: beatpick only analyses and optionally writes Music metadata. Explain how the user can create a Smart Playlist from the configured BPM range and exclude `beatpick-duplicate` comments. Mention that stale BPM values on tracks that no longer qualify are not automatically cleared.

Keep personal configurations, audio, paths, inventory exports, and state out of commits and uploads. This skill ships no personal library data and needs no model API key; it uses the local CLI through the user's chosen agent.
