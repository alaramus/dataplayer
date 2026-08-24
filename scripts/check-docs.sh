#!/usr/bin/env bash
#
# Three assertions about the documentation:
#
#   1. every relative link in a tracked .md file resolves to something that
#      exists;
#   2. every decision listed in the AGENTS.md table has exactly one home in
#      docs/architecture/, and no decision lives there unlisted;
#   3. AGENTS.md stays under the size budget — it is loaded into every session,
#      which is the whole reason it was split up. Raised from 16 KB to 24 KB in
#      round 8: the file had 142 bytes left, and the first thing the budget
#      would have evicted was a trap that belongs in every session. A ceiling
#      that pushes out what the file exists to hold is set too low.
#
set -euo pipefail

cd "$(dirname "$0")/.."

BUDGET=24576
failed=0

note() {
    printf '%s\n' "$1" >&2
    failed=1
}

# 1. Links -------------------------------------------------------------------

while IFS= read -r file; do
    dir=$(dirname "$file")
    while IFS= read -r link; do
        case "$link" in
            '' | '#'* | http://* | https://* | mailto:*) continue ;;
        esac
        path=${link%%#*}
        [ -n "$path" ] || continue
        if [ ! -e "$dir/$path" ]; then
            note "broken link: $file -> $link"
        fi
    done < <(awk '/^```/ { fenced = !fenced; next } !fenced' "$file" |
        grep -o '](\([^)]*\))' | sed -e 's/^](//' -e 's/)$//')
done < <(git ls-files '*.md')

# 2. Decisions ---------------------------------------------------------------

listed=$(sed -n 's/^| \(D[0-9][0-9a-z]*\) |.*/\1/p' AGENTS.md | tr '\n' ' ')

if [ -z "$listed" ]; then
    note "the decision table in AGENTS.md is empty or its shape changed"
fi

for id in $listed; do
    homes=$(grep -l "^## $id\." docs/architecture/*.md || true)
    count=$(printf '%s' "$homes" | grep -c . || true)
    case "$count" in
        1) ;;
        0) note "decision $id is listed in AGENTS.md and documented nowhere" ;;
        *) note "decision $id is documented in several files: $(echo $homes)" ;;
    esac
done

while IFS= read -r id; do
    case " $listed " in
        *" $id "*) ;;
        *) note "decision $id is documented but missing from the AGENTS.md table" ;;
    esac
done < <(sed -n 's/^## \(D[0-9][0-9a-z]*\)\..*/\1/p' docs/architecture/*.md)

# 3. Size --------------------------------------------------------------------

# Carriage returns are stripped before counting: a Windows working tree holds
# the same file 2% larger, and the budget must mean one thing on both.
size=$(tr -d '\r' < AGENTS.md | wc -c | tr -d ' ')
if [ "$size" -gt "$BUDGET" ]; then
    note "AGENTS.md is $size bytes, over the $BUDGET budget; move a section into docs/architecture/"
fi

if [ "$failed" -eq 0 ]; then
    printf 'docs ok: links resolve, decisions have one home each, AGENTS.md is %s of %s bytes\n' "$size" "$BUDGET"
fi

exit "$failed"
