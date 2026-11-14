#!/usr/bin/env bash
# Install the skills in this repo into a DeepSeek Harness local skill root.
#
#   ./install.sh                 install / update every skill under skills/
#   ./install.sh list            list skills in this repo
#   ./install.sh check           verify installed copies match this repo
#   ./install.sh uninstall NAME  remove one installed skill
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_ROOT="$REPO/skills"
DST_ROOT="${DSH_HOME:-$HOME/.dsh}/skills"

die() { echo "ERROR: $*" >&2; exit 1; }

validate() {
  local file="$1" dir="$2"
  python3 - "$file" "$dir" <<'PY'
import re, sys
path, dirname = sys.argv[1], sys.argv[2]
s = open(path, encoding='utf-8').read()
m = re.match(r'---\n(.*?)\n---\n', s, re.S)
if not m:
    sys.exit(f'{path}: frontmatter missing')
fm = {}
for line in m.group(1).strip().splitlines():
    k, _, v = line.partition(':')
    fm[k.strip()] = v.strip()
name = fm.get('name', '')
if name != dirname:
    sys.exit(f'{path}: name {name!r} does not match directory {dirname!r}')
if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
    sys.exit(f'{path}: name is not kebab-case')
desc = fm.get('description', '')
if not desc:
    sys.exit(f'{path}: description missing')
if len(desc) > 500:
    sys.exit(f'{path}: description {len(desc)} chars > 500 (DSH truncates it)')
print(f'  ok  {name:<28} description={len(desc)}ch body={len(s) - m.end()}ch')
PY
}

skills() {
  local d
  for d in "$SRC_ROOT"/*/; do
    [ -f "${d}SKILL.md" ] && basename "$d"
  done
}

case "${1:-install}" in
  install)
    [ -d "$SRC_ROOT" ] || die "no skills/ directory in $REPO"
    mkdir -p "$DST_ROOT"
    echo "installing into $DST_ROOT"
    while read -r name; do
      [ -n "$name" ] || continue
      validate "$SRC_ROOT/$name/SKILL.md" "$name"
      rm -rf "$DST_ROOT/$name"
      mkdir -p "$DST_ROOT/$name"
      cp -R "$SRC_ROOT/$name/." "$DST_ROOT/$name/"
      echo "  -> $DST_ROOT/$name/"
    done < <(skills)
    echo "done. DSH watches this root and refreshes its catalog automatically."
    ;;
  list)
    skills
    ;;
  check)
    status=0
    while read -r name; do
      [ -n "$name" ] || continue
      validate "$SRC_ROOT/$name/SKILL.md" "$name" || status=1
      if [ ! -f "$DST_ROOT/$name/SKILL.md" ]; then
        echo "  --  $name not installed"
        status=1
      elif diff -r -q "$SRC_ROOT/$name" "$DST_ROOT/$name" >/dev/null 2>&1; then
        echo "  =   $name in sync"
      else
        echo "  !=  $name differs; run ./install.sh"
        status=1
      fi
    done < <(skills)
    exit "$status"
    ;;
  uninstall)
    name="${2:-}"
    [ -n "$name" ] || die "usage: ./install.sh uninstall <name>"
    [ -d "$DST_ROOT/$name" ] || die "not installed: $DST_ROOT/$name"
    rm -rf -- "$DST_ROOT/$name"
    echo "removed: $DST_ROOT/$name"
    ;;
  *)
    die "unknown action: $1 (use install | list | check | uninstall)"
    ;;
esac
