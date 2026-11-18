#!/usr/bin/env bash
# Installs the third-party agent skills used to build this kit (pinned by commit) into ~/.claude/skills.
# Idempotent. Nothing is executed: skills are folders of Markdown. Not vendored: their licences differ.
set -euo pipefail
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$DEST"

# repo commit licence path1 path2 ...
SOURCES=(
  "obra/superpowers 22f0b463e7a5e579904dd6211a520321035526f7 MIT skills/test-driven-development skills/systematic-debugging skills/verification-before-completion skills/writing-plans skills/executing-plans skills/receiving-code-review"
  "trailofbits/skills 149d7b21f4067765b82e67029730b42d228ef4b4 CC-BY-SA-4.0 plugins/sharp-edges/skills/sharp-edges plugins/differential-review/skills/differential-review plugins/supply-chain-risk-auditor/skills/supply-chain-risk-auditor plugins/static-analysis/skills/semgrep plugins/modern-python/skills/modern-python plugins/property-based-testing/skills/property-based-testing plugins/agentic-actions-auditor/skills/agentic-actions-auditor plugins/spec-to-code-compliance/skills/spec-to-code-compliance"
  "hashicorp/agent-skills 5e30fa5c867ba6777c37e4206babfd08049c396f MPL-2.0 plugins/terraform/skills/terraform-test plugins/terraform/skills/terraform-style-guide"
  "anthropics/skills 1780c5e5a552fd4d1c9d6a7b0cab26b0c2bef064 Apache-2.0 skills/mcp-builder"
  "hardikpandya/stop-slop 8da1f030185bdfe8471220585162991eaeb970e9 MIT ."
  "JuliusBrussee/caveman 9b243662ff98d392bc0a95b865a554583d71be75 Apache-2.0 skills/caveman"
)

for spec in "${SOURCES[@]}"; do
  read -r repo commit licence paths <<<"$spec"
  dir="$TMP/${repo//\//_}"
  git init -q "$dir"
  git -C "$dir" fetch -q --depth 1 "https://github.com/$repo" "$commit"
  git -C "$dir" checkout -q FETCH_HEAD
  for path in $paths; do
    src="$dir/$path"
    [[ -f $src/SKILL.md ]] || { echo "SKILL.md missing: $repo/$path" >&2; exit 1; }
    name=$(sed -n 's/^name:[[:space:]]*//p' "$src/SKILL.md" | head -1 | tr -d '"'\''')
    [[ $name =~ ^[a-z0-9-]+$ ]] || { echo "invalid skill name: $name" >&2; exit 1; }
    target="$DEST/$name"
    if [[ -f $target/.source && $(<"$target/.source") == "$repo@$commit:$path" ]]; then continue; fi
    mkdir -p "$target.new"
    (cd "$src" && tar --exclude=.git -cf - .) | tar -xf - -C "$target.new"
    printf '%s\n' "$repo@$commit:$path" > "$target.new/.source"
    printf 'Source : https://github.com/%s/tree/%s/%s\nLicence : %s\n' "$repo" "$commit" "$path" "$licence" > "$target.new/ATTRIBUTION"
    if [[ -e $target ]]; then mv "$target" "$target.old"; fi
    mv "$target.new" "$target"
    if [[ -e $target.old ]]; then find "$target.old" -mindepth 0 -delete; fi
    echo "installed: $name ($repo)"
  done
done
