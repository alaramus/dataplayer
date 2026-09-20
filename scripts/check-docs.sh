#!/usr/bin/env bash
#
# Eight assertions about the documentation:
#
#   1. every relative link in a tracked .md file resolves to something that
#      exists, and a link carrying a `#fragment` into a .md file names a
#      heading that is actually in it;
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
#      every file under docs/architecture/. This is the ceiling
#      adapters.md never had, and it reached 114 KB;
#   6. no file under docs/architecture/ is an orphan — something in AGENTS.md
#      or in another architecture file links to it;
#   7. every decision the code names in a comment exists in the AGENTS.md
#      table. Pointing at a decision is how a comment stays short: the
#      argument lives once, in docs/architecture/, and the code names it.
#      That only works while the name resolves;
#   8. every architecture file holding decisions lists exactly them in a
#      `Decisions here:` line. That line is how a session decides whether to
#      spend ten thousand tokens on the file, so it has to be true; eight
#      files had none and workspace.md's had been wrong since D112.
#
# And one warning, which does not fail the run:
#
#   a file past WARN_AT is told how much is left. The per-file budget used to
#   arrive as a failure on the commit that crossed it — workspace.md sat at 44
#   bytes free and services.md at 276 — so what had to be split was discovered
#   at the worst moment. Splitting is the answer to the warning; raising the
#   budget is not, because a session pays for the whole file it opens.
#
set -euo pipefail

cd "$(dirname "$0")/.."

AGENTS_BUDGET=24576
FILE_BUDGET=40960
WARN_AT=32768
failed=0

note() {
    printf '%s\n' "$1" >&2
    failed=1
}

warn() {
    printf 'warning: %s\n' "$1" >&2
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

# The heading a fragment would have to match, GitHub's slug rules: lowercased,
# anything but a word character, a space or a hyphen dropped, spaces hyphenated.
slugs_of() {
    sed -n 's/^#\{1,6\} //p' "$1" |
        tr '[:upper:]' '[:lower:]' |
        sed -e 's/[^a-z0-9 _-]//g' -e 's/ /-/g'
}

while IFS= read -r file; do
    while IFS=$'\t' read -r link target; do
        if [ ! -e "$target" ]; then
            note "broken link: $file -> $link"
            continue
        fi
        # A fragment into a document nobody checked is how a split breaks a
        # link while leaving it pointing at a file that still exists: five of
        # them survived the move of D91, D76 and three of contract.md's own.
        case "$link" in *'#'*) ;; *) continue ;; esac
        case "$target" in *.md) ;; *) continue ;; esac
        fragment=${link#*#}
        [ -n "$fragment" ] || continue
        if ! slugs_of "$target" | grep -qxF "$fragment"; then
            note "broken anchor: $file -> $link"
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


# 7. Decisions named in code -------------------------------------------------

# Skips the generated client, which has no comments of ours in it.
named_in_code=$(git ls-files --cached --others --exclude-standard \
    'frontend/src/*.ts' 'frontend/src/*.vue' 'backend/app/*.py' |
    grep -v '^frontend/src/client/' |
    xargs grep -hoE '\bD[0-9]{1,3}[a-z]?\b' 2>/dev/null | sort -u || true)

while IFS= read -r id; do
    [ -n "$id" ] || continue
    case " $listed " in
        *" $id "*) ;;
        *) note "the code names decision $id, which is not in the AGENTS.md table" ;;
    esac
done < <(printf '%s\n' "$named_in_code")

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
    elif [ "$bytes" -gt "$WARN_AT" ]; then
        warn "$file is $bytes bytes, $((FILE_BUDGET - bytes)) short of the budget; plan the split now"
    fi
done < <(architecture_files)

# 8. Every file says which decisions it holds ---------------------------------

while IFS= read -r file; do
    [ -e "$file" ] || continue
    here=$(sed -n 's/^## \(D[0-9][0-9a-z]*\)\..*/\1/p' "$file" | tr '\n' ' ')
    [ -n "$here" ] || continue
    line=$(sed -n 's/^Decisions here: //p' "$file" | head -1)
    if [ -z "$line" ]; then
        note "$file holds ${here% } and carries no 'Decisions here:' line"
        continue
    fi
    said=$(printf '%s' "$line" | grep -oE 'D[0-9]+[a-z]?' | tr '\n' ' ')
    for id in $here; do
        case " $said " in
            *" $id "*) ;;
            *) note "$file holds $id, which its 'Decisions here:' line does not name" ;;
        esac
    done
    for id in $said; do
        case " $here " in
            *" $id "*) ;;
            *) note "$file names $id in 'Decisions here:' and does not hold it" ;;
        esac
    done
done < <(architecture_files)

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
    printf 'docs ok: links resolve, decisions sit where the table says and where the code names them, every decision names a spec, AGENTS.md is %s of %s bytes\n' "$size" "$AGENTS_BUDGET"
fi

exit "$failed"
