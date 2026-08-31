#!/usr/bin/env bash
#
# Six assertions about the documentation:
#
#   1. every relative link in a tracked .md file resolves to something that
#      exists;
#   2. every decision listed in the AGENTS.md table lives in exactly the file
#      the table names, and no decision lives in docs/architecture/ unlisted.
#      The table names a file rather than an area, so it is a checked index
#      rather than a hint that drifts silently;
#   3. AGENTS.md stays under its size budget — it is loaded into every session,
#      which is the whole reason it was split up. Raised from 16 KB to 24 KB in
#      round 8: the file had 142 bytes left, and the first thing the budget
#      would have evicted was a trap that belongs in every session. A ceiling
#      that pushes out what the file exists to hold is set too low;
#   4. every decision carries exactly one `Spec:` line, so the argument behind
#      a statement is reachable from the statement. The path used to run one
#      way only, from the spec index, and finding the argument meant guessing
#      a filename;
#   5. no documentation file that a session loads exceeds the per-file budget:
#      every file under docs/architecture/ and the roadmap. This is the ceiling
#      adapters.md never had, and it reached 114 KB;
#   6. no file under docs/architecture/ is an orphan — something in AGENTS.md
#      or in another architecture file links to it.
#
set -euo pipefail

cd "$(dirname "$0")/.."

AGENTS_BUDGET=24576
FILE_BUDGET=40960
failed=0

note() {
    printf '%s\n' "$1" >&2
    failed=1
}

# Tracked files plus new ones that are not ignored: a file being added in this
# commit must be checked before it is committed, not after.
ALL_DOCS=$(git ls-files --cached --others --exclude-standard '*.md')
ARCHITECTURE=$(printf '%s\n' "$ALL_DOCS" | grep '^docs/architecture/.*\.md$' || true)

docs() { printf '%s\n' "$ALL_DOCS"; }
architecture_files() { printf '%s\n' "$ARCHITECTURE"; }

# Collapse . and .. without spawning a process per link. This runs for every
# link in every tracked file, and realpath made the whole check take 40 seconds.
normalize() {
    local out=() seg
    local IFS=/
    for seg in $1; do
        case "$seg" in
            '' | '.') continue ;;
            '..') [ ${#out[@]} -gt 0 ] && unset 'out[${#out[@]}-1]' ;;
            *) out+=("$seg") ;;
        esac
    done
    printf '%s' "${out[*]}"
}

# Every relative link in a file, resolved to a repository-relative path.
links_of() {
    local file=$1 dir link path
    dir=$(dirname "$file")
    while IFS= read -r link; do
        case "$link" in
            '' | '#'* | http://* | https://* | mailto:*) continue ;;
        esac
        path=${link%%#*}
        [ -n "$path" ] || continue
        printf '%s\t%s\n' "$link" "$(normalize "$dir/$path")"
    done < <(awk '/^```/ { fenced = !fenced; next } !fenced' "$file" |
        grep -o '](\([^)]*\))' | sed -e 's/^](//' -e 's/)$//')
}

# 1. Links -------------------------------------------------------------------

while IFS= read -r file; do
    while IFS=$'\t' read -r link target; do
        if [ ! -e "$target" ]; then
            note "broken link: $file -> $link"
        fi
    done < <(links_of "$file")
done < <(docs)

# 2. Decisions ---------------------------------------------------------------

registry=$(sed -n 's/^| \(D[0-9][0-9a-z]*\) | \[[^]]*\](\([^)]*\)) |.*/\1 \2/p' AGENTS.md)

if [ -z "$registry" ]; then
    note "the decision table in AGENTS.md is empty or its shape changed"
fi

listed=$(printf '%s\n' "$registry" | awk '{ print $1 }' | tr '\n' ' ')

# One pass over every architecture file, giving "<id> <file>" per heading, so
# the loop below reads a variable instead of running a grep per decision.
documented=$(printf '%s\n' "$ARCHITECTURE" | xargs grep -H '^## D[0-9]' |
    sed -n 's|^\([^:]*\):## \(D[0-9][0-9a-z]*\)\..*|\2 \1|p')

while read -r id declared; do
    [ -n "$id" ] || continue
    homes=$(printf '%s\n' "$documented" | awk -v want="$id" '$1 == want { print $2 }')
    count=$(printf '%s' "$homes" | grep -c . || true)
    case "$count" in
        1)
            if [ "$homes" != "$declared" ]; then
                note "decision $id is documented in $homes but the AGENTS.md table names $declared"
            fi
            ;;
        0) note "decision $id is listed in AGENTS.md and documented nowhere" ;;
        *) note "decision $id is documented in several files: $(echo $homes)" ;;
    esac
done < <(printf '%s\n' "$registry")

while IFS= read -r id; do
    case " $listed " in
        *" $id "*) ;;
        *) note "decision $id is documented but missing from the AGENTS.md table" ;;
    esac
done < <(printf '%s\n' "$documented" | awk '{ print $1 }')


# 3. AGENTS.md size ----------------------------------------------------------

# Carriage returns are stripped before counting: a Windows working tree holds
# the same file 2% larger, and the budget must mean one thing on both.
size=$(tr -d '\r' < AGENTS.md | wc -c | tr -d ' ')
if [ "$size" -gt "$AGENTS_BUDGET" ]; then
    note "AGENTS.md is $size bytes, over the $AGENTS_BUDGET budget; move a section into docs/architecture/"
fi

# 4. Every decision names its spec -------------------------------------------

while IFS= read -r file; do
    while read -r id specs; do
        case "$specs" in
            1) ;;
            0) note "decision $id in $file names no spec; add a 'Spec:' line" ;;
            *) note "decision $id in $file names $specs specs; exactly one is the home of the argument" ;;
        esac
    done < <(awk '
        /^## D[0-9]/ {
            if (id != "") print id, specs
            id = $2
            sub(/\.$/, "", id)
            specs = 0
            next
        }
        /^Spec: / { if (id != "") specs++ }
        END { if (id != "") print id, specs }
    ' "$file")
done < <(architecture_files)

# 5. Per-file size -----------------------------------------------------------

while IFS= read -r file; do
    [ -e "$file" ] || continue
    bytes=$(tr -d '\r' < "$file" | wc -c | tr -d ' ')
    if [ "$bytes" -gt "$FILE_BUDGET" ]; then
        note "$file is $bytes bytes, over the $FILE_BUDGET per-file budget; split it by the work it serves"
    fi
done < <(architecture_files; echo docs/migration-roadmap.md)

# 6. No orphan architecture file ---------------------------------------------

reachable=$( { echo AGENTS.md; architecture_files; } | while IFS= read -r file; do
    links_of "$file" | cut -f2
done | sort -u)

while IFS= read -r file; do
    if ! printf '%s\n' "$reachable" | grep -qxF "$file"; then
        note "$file is an orphan: neither AGENTS.md nor another architecture file links to it"
    fi
done < <(architecture_files)

if [ "$failed" -eq 0 ]; then
    printf 'docs ok: links resolve, decisions sit where the table says, every decision names a spec, AGENTS.md is %s of %s bytes\n' "$size" "$AGENTS_BUDGET"
fi

exit "$failed"
