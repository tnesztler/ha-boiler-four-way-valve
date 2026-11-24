---
name: create-release
description: >-
  Publish a Boiler Four-Way Valve release. Run the mapping tests and the
  Docker setup check, bump the manifest so the tag matches, then push the
  annotated tag and GitHub release. Use when the user asks to release,
  publish, tag, or ship a new version of this integration.
---

# Create a release

Ship the current branch. The GitHub tag is the version HACS installs, and it must equal `version` in `custom_components/boiler_four_way_valve/manifest.json`. Do not tag or publish until both checks pass.

## Checks

```bash
python3 -m unittest discover -s tests -v
tests/run_setup_check.sh
```

The setup check starts the Home Assistant image for the version in `hacs.json` and loads the helper. A missing import fails that run, along with a climate entity, manual position, or recorded sensor that is missing or unavailable. Docker is required. Stop when either command fails.

## Version

Use the version the user names. Otherwise take the latest tag and increment the patch (`0.2.3` → `0.2.4`).

If that version is already in the manifest on `HEAD`, tag `HEAD`. If not, commit only the manifest change:

```
chore: release X.Y.Z

The GitHub release tag has to match the manifest version.
```

Leave every other dirty file unstaged and stop until the tree contains only that change. Do not release when `HEAD` is already the latest tag and the manifest already matches it.

## Publish

Annotated tag. The tag message describes the change since the previous tag, in the same shape as the existing tags. Docs-only commits such as `AGENTS.md` are not the message.

```bash
git tag -a X.Y.Z -m "$(cat <<'EOF'
fix: short summary of the change

Why it matters, in one or two lines.

EOF
)"
git push origin HEAD
git push origin X.Y.Z
gh release create X.Y.Z --title "X.Y.Z" --notes "$(cat <<'EOF'
What the user gets, in one or two sentences.

Restart Home Assistant after updating.

Requires Home Assistant 2026.11 or newer.
EOF
)"
```

The release notes use the major.minor from `hacs.json` (`2026.11.0` → `2026.11`). Home Assistant loads the new code only on restart. Do not force-push, skip hooks, or change git config.

Return the release URL.
