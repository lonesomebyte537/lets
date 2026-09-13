# Test harness for the lets zsh completion (_lets).
#
# Run from the repository root with the `lets` executable on the PATH:
#
#     PATH="$PWD/.venv/bin:$PATH" zsh completions/_lets.test.zsh
#
# It mocks compdef/compadd, sources the completion function, and simulates a
# number of command lines (the demo plugin is used, so it runs from example/).

set -u

# --- mocks -----------------------------------------------------------------
compdef() { :; }                      # registration: ignore in tests

# Each completed candidate is stored as "candidate" or "candidate<TAB>description".
PAIRS=()
compadd() {
    local -a a=("$@")
    local i n=${#a}
    local desc="" cand=""
    for (( i = 1; i <= n; i++ )); do
        case "${a[i]}" in
            -d)  desc="${a[i+1]}"; (( i++ )) ;;
            --)  ;;
            -*)  ;;
            *)   cand="${a[i]}" ;;
        esac
    done
    if [[ -n $desc ]]; then
        PAIRS+=("$cand"$'\t'"$desc")
    else
        PAIRS+=("$cand")
    fi
}

# --- load the completion function -----------------------------------------
source "$(dirname "$0")/_lets"

# --- scenario runner -------------------------------------------------------
# usage: run_case "description" "current_word" lets <complete words...>
# "current_word" is the (possibly empty) word being completed; the remaining
# arguments are the complete words already on the line (including 'lets').
run_case() {
    local desc="$1"; shift
    local current="$1"; shift
    local -a prefix=("$@")
    if [[ -n $current ]]; then
        words=("${prefix[@]}" "$current")
        CURRENT=${#words}
    else
        words=("${prefix[@]}")
        CURRENT=$(( ${#words} + 1 ))
    fi
    PAIRS=()
    _lets
    printf '=== %-24s -> ' "$desc"
    if (( ${#PAIRS[@]} )); then
        local i p
        for (( i = 1; i <= ${#PAIRS[@]}; i++ )); do
            p="${PAIRS[i]}"
            (( i > 1 )) && printf ', '
            if [[ $p == *$'\t'* ]]; then
                printf '"%s"[%s]' "${p%%$'\t'*}" "${p#*$'\t'}"
            else
                printf '"%s"' "$p"
            fi
        done
    else
        printf '(none)'
    fi
    printf '\n'
}

# The completion resolves the demo plugin, so run from the example directory.
cd "$(dirname "$0")/../example"

# --- scenarios -------------------------------------------------------------
run_case "lets <TAB>"            ""  lets
run_case "lets b<TAB>"           b   lets
run_case "lets bu<TAB>"          bu  lets
run_case "lets show<TAB>"        ""  lets show
run_case "lets show a<TAB>"      a   lets show
run_case "lets build<TAB>"       ""  lets build
run_case "lets build d<TAB>"     d   lets build
run_case "lets build re<TAB>"    re  lets build
run_case "lets build c<TAB>"     c   lets build
run_case "lets build de<TAB>"    de  lets build
run_case "lets build hello<TAB>" hello lets build
run_case "lets build debug<TAB>" debug lets build
run_case "lets build xyz<TAB>"   xyz lets build
run_case "lets monitor<TAB>"        ""  lets monitor
run_case "lets flash<TAB>"          ""  lets flash
run_case "lets set<TAB>"            ""  lets set
run_case "lets get<TAB>"            ""  lets get
run_case "lets set v<TAB>"          v   lets set
# Multi-word context (more than one complete word already typed). A "␣" in the
# label marks the empty word being completed after a space. These must be
# passed to lets as separate arguments, not one space-joined word (which lets
# would not match to any verb and thus return no completions).
run_case "lets build debug␣<TAB>"              "" lets build debug
run_case "lets build debug hello_cruel_world␣<TAB>" "" lets build debug hello_cruel_world
run_case "lets flash erase␣<TAB>"              "" lets flash erase
