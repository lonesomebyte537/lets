# Shell completion (`LETS_COMPLETE`)

Specification for Lets' shell completion support: how Lets prints the valid options for a
partially typed command line, and how the zsh completion script turns that output into
candidates.

## Overview

Completion is Lets acting as an oracle: given the words already typed after `lets`, it
prints what can validly follow. It is triggered by the **`LETS_COMPLETE` environment
variable** (defined and non-empty) — there is no `complete` verb or token. When the variable
is set, `_process_arguments` calls `_complete(args)` and returns before any verb dispatch,
so the normal lets logic never runs.

Output contract: plain text on stdout (no ANSI codes, no wrapping), one option per line.
The **full option set** for the resolved context is always printed; narrowing candidates to
the partially typed word is deliberately left to the shell (zsh filters candidates by the
word being completed).

## Background

Completion builds on the standard lets engine. The concepts it relies on:

- **Verbs** – functions registered with `@verb()`, signature
  `(lets_instance, verb_name, args) -> exit_code`. Names are stored as *lists of words* to
  support multi-word verbs (`"show apps"` → `["show", "apps"]`); without an explicit name
  the function name is used, split on `_`.
- **Namespaces** – every verb is logically `[NAMESPACE].[VERB_NAME]`; the namespace comes
  from the plugin module's `LETS_NAMESPACE` constant. Built-in verbs use `"lets"`. The
  prefix may be omitted when the verb name is unique.
- **Verb registry** – the module-level `_registered_verbs` list is the single source of
  truth; `LetsCore.__init__` loads plugins (whose `@verb` decorators append at import
  time), appends the built-in verbs, and merges everything (dedup by `(namespace, verb)`)
  into `self._verbs`.
- **Plugin discovery** – `_load_plugins()` walks up the directory tree collecting `.lets`
  files (plus `~/.lets`); each may declare `lets.plugins: [paths]`, imported via
  `importlib`, with a required `LETS_NAMESPACE` and optional `init(lets)`.
- **Settings** – `register_setting(name, description, options, default)` stores
  `self._registered_settings[namespace][name]`. Each namespace gets a protected `_remember`
  setting (leading `_`) for persisted values; protected settings are not user-addressable.
- **`@args` decorator** – matchers are regex strings (`re.fullmatch`) or callables
  `(lets, args) -> (matches, remaining_args)`; `remember=[names]` names the extracted
  values for persistence. Each `@args` wrapper records
  `wrapper.__lets_arg_matchers__ = [(matcher, remember_name_or_None), ...]`, which is what
  completion introspects (the `__wrapped__` chain from `functools.wraps` links the
  wrappers to the plain function).
- **Dispatch** – `_process_arguments` checks `LETS_COMPLETE` first (see Overview);
  otherwise: no args → help; `_find_match(args)` resolves the verb using
  longest-match-first with an optional `namespace.` prefix; a `verbose` token enables
  one-time verbose mode; a `help` token shows verb help; finally the verb's
  `process_func` is called.

## Behaviour

The *context* is the argument list as given. Three cases:

1. **Empty context** (`LETS_COMPLETE=1 lets`) — prints the distinct first word of every
   registered verb, in registration order.
2. **Context resolves to a verb** (`LETS_COMPLETE=1 lets build`) — prints that verb's
   options, one per line (see Verb options below).
3. **Context is a verb prefix** (`LETS_COMPLETE=1 lets show a`) — prints the full names
   of the verbs (multi-word included) whose name the context is a leading prefix of.

In `example/` this produces:

```
$ LETS_COMPLETE=1 lets
build
flash
monitor
show
help
get
set
add
remove

$ LETS_COMPLETE=1 lets build
flavor=debug|release
clean
apps=hello_cruel_world|hello_beautiful_world

$ LETS_COMPLETE=1 lets set
config_name=demo.boards|lets.plugins|lets.verbose
```

### Verb options

For a resolved verb, `_print_verb_options(verb, provided_args)` — where `provided_args`
are the context words after the verb — collects the verb's matchers
(`_collect_arg_matchers`) and prints, for each matcher:

- a matcher **with** a `remember` name → `name=value1|value2` (or just `name` when no
  values can be derived);
- a matcher **without** a `remember` name (e.g. the `clean`/`erase` flags) → the possible
  values joined by `|` (a single flag prints just the word, e.g. `clean`);
- the built-in `get`/`set` verbs have no `@args` matchers; instead the registered settings
  are printed as the values of a pseudo-parameter `config_name`
  (`config_name=demo.boards|lets.plugins|lets.verbose`). Settings are listed as
  `namespace.name` (via `_available_settings`); protected settings (leading `_`) are
  excluded.

An option is **omitted** when one of `provided_args` already satisfies it
(`_matcher_satisfied`): regex matchers use the same `re.fullmatch` rule as `@args`;
callable matchers are checked against their advertised option values
(`_arg_covers_option` — exact or case-insensitive substring, mirroring the fuzzy matching
those matchers use at execution time). E.g. `LETS_COMPLETE=1 lets build
hello_cruel_world` no longer lists `apps=...` and prints `flavor=debug|release` + `clean`;
`LETS_COMPLETE=1 lets set verbose` prints nothing.

### Verb names

`_verb_matches_context(verb_words, context)` returns True when the context is a leading
prefix of a (possibly multi-word) verb name: all context words except the last must equal
the corresponding verb words; the last context word must be a prefix of the corresponding
verb word. So `LETS_COMPLETE=1 lets show` prints `show apps` + `show boards`, and
`LETS_COMPLETE=1 lets show a` prints `show apps` (not `add`).

## Output line format

| Line | Meaning |
|------|---------|
| `word` | a verb first word, an unremembered flag, or a name-only option |
| `name=value1\|value2` | an option (remembered option or `config_name`) with its possible values |
| `word word ...` | a full multi-word verb name |

The zsh script distinguishes these by the presence of a space / `=`.

## Architecture

### Engine side (`lets/core.py`)

- `_process_arguments` checks `os.environ.get("LETS_COMPLETE")` first; when defined it
  returns `self._complete(args)` immediately.
- `_complete(context)` implements the three cases above: empty → distinct verb first
  words; `_find_match(context)` resolves a verb → `_print_verb_options(verb,
  provided_args)`; otherwise → `_verb_matches_context` over all verbs.
- `_collect_arg_matchers(func)` walks the `@args` chain via
  `__lets_arg_matchers__` / `__wrapped__`.
- `_matcher_options(matcher)` derives the concrete values a matcher accepts:
  - callable matcher → the optional `matcher.__lets_options__` attribute: a list, or a
    callable invoked with the `lets` instance (falling back to no args);
  - regex matcher → the pattern split on top-level `|` by `_split_regex_alternatives`
    (which respects `(...)` groups and `[...]` character classes), keeping clean literal
    alternatives.
- `_available_settings` → all non-protected settings as sorted `namespace.name` strings.
- Completion output uses plain `print()`, not the coloured/wrapped output helpers, because
  it is machine-consumed.

### Plugin author contract

A verb's options are exactly what its `@args` matchers advertise:

- **Regex matchers** need no extra work: the pattern's alternatives are the option values
  (`r"debug|release"` → `debug`, `release`).
- **Callable matchers** should expose their possible values via `__lets_options__`:

```python
_match_apps.__lets_options__ = _get_apps          # zero-arg callable -> app dir names
_match_boards.__lets_options__ = _board_options   # (lets) -> registered board names
```

`example/demo.py` follows this; it is what makes `LETS_COMPLETE=1 lets build` print
`apps=hello_cruel_world|hello_beautiful_world` and `LETS_COMPLETE=1 lets flash` print
`boards=myboard1|myboard2` (when boards are registered).

### Zsh script (`completions/_lets`)

The function `_lets` runs

```bash
LETS_COMPLETE=1 lets <complete words already typed after 'lets'>
```

and turns each printed line into `compadd` candidates:

- a single word → one candidate;
- `name=value1|value2` → one candidate per value, annotated with the option name
  (`compadd -d`);
- a full multi-word verb name → only the part still to type, i.e. the typed context
  stripped from the front (`show apps` with context `show` → `apps`).

The context is the complete words already typed after `lets` (zsh `words[2, CURRENT-1]`),
**excluding the word being completed**. zsh then filters the candidates by the partially
typed word, which is why Lets can always print the full set.

Implementation notes:

- `compdef _lets lets` registers the function; the `#compdef lets` header also lets
  `compinit` pick it up from `fpath`.
- Loop locals (`line`, `name`, `value`, `rest`, `values`) are declared **once** before the
  loop and only *assigned* inside it: a bare `local x` re-declared while `x` holds a value
  prints `x=value` to stdout under `set -u`, which would corrupt the completion output.
- `"${context[@]}"` (not `${(q)context}`) passes the context: on an empty array the former
  expands to nothing, while the latter yields a single empty word that Lets would treat as
  a (matching) argument and print nothing for.

User-facing installation instructions live in the README ("Shell completion" section).

## Design decisions

- **Environment variable, not a verb.** The env var puts completion on a separate code
  path checked before dispatch: the command line stays free (any word, including
  `complete`, remains a normal token), nothing has to be stripped from the arguments, and
  the shell can enable it per invocation.
- **Lets prints the full option set; zsh does the filtering.** Prefix-narrowing the list
  to a started parameter inside Lets would duplicate what zsh already does with the
  partially typed word, and would require passing that partial word to Lets. Keeping Lets
  an oracle for *complete* words keeps the contract simple and both sides independent.
- **Only complete words are passed as context.** Passing the partial current word would
  create an empty-string edge case in Lets' argument matching, and is unnecessary given
  the point above.
- **One line per option, values joined by `|`.** A trivially parseable line carries both
  the option name (for zsh's candidate annotation) and its values; `|` and spaces do not
  occur in the value sets Lets uses.
- **Multi-word verbs are printed in full.** Lets does not know how many words are already
  on the line; printing the full name and letting the zsh script strip the typed prefix
  keeps both sides simple.
- **`config_name` for `get`/`set`.** The built-in `get`/`set` verbs accept any registered
  setting but have no `@args` matchers to introspect. Offering the settings as the values
  of a pseudo-parameter `config_name` reuses the existing `name=value1|value2` line format
  and the provided-argument exclusion logic without introducing a new line type. Settings
  are qualified (`namespace.name`) so they are always valid input, and protected settings
  are not offered.
- **Already-supplied options are omitted.** Mirrors the execution semantics (a supplied
  value is not missing) and keeps the output short as the command line grows.
- **Plain `print()` for completion output.** The normal output helpers add ANSI colours
  and text wrapping; completion output must stay unformatted for machine consumption.

## Testing

### Unit tests (`tests/test_lets.py`, `TestComplete`)

`TestComplete._run_complete(lets, args)` runs `_process_arguments` with `LETS_COMPLETE`
set (`patch.dict(os.environ, ...)`) and returns `(result, printed_lines)`; every
completion test drives the feature through the public entry point. Coverage:

- no-context first-word listing;
- regex option and callable option (both `()` and `(lets)` `__lets_options__` signatures);
- matchers without a `remember` name (shown, and excluded when provided, e.g. `clean`);
- mixing remembered and unremembered options;
- exclusion of an already-provided option (regex and callable), keeping an unmatched
  option;
- single- and multi-word verb prefix completion;
- `get`/`set` configuration completions (`config_name` listing, settings from other
  namespaces, exclusion of a provided setting — bare and `namespace.`-qualified);
- `_split_regex_alternatives`.

The shared suite conventions apply (cleared `_registered_verbs`, patched
`Path.home`/`Path.cwd` to an empty temp dir so no real `.lets` files load, no-op
`_save_settings`, `LETS_NAMESPACE = "test"` for direct method calls). Run with
`python -m unittest discover -s tests`.

### Zsh harness (`completions/_lets.test.zsh`)

Mocks `compdef`/`compadd`, sources the completion function, and simulates a series of
command lines against the demo plugin (the harness runs from `example/`):

```bash
PATH="$PWD/.venv/bin:$PATH" zsh completions/_lets.test.zsh
```

Scenarios cover first-word listing, verb prefixes (`show a`), verb options (`build d`,
`build de`, `build hello`, `build debug`, `build xyz`, ...), unremembered flags,
multi-word context with a trailing empty word, and the `config_name` listing for
`set`/`get`.

### Manual checks

```bash
cd example
LETS_COMPLETE=1 lets
LETS_COMPLETE=1 lets build
LETS_COMPLETE=1 lets build debug hello_cruel_world   # -> only 'clean'
LETS_COMPLETE=1 lets set
LETS_COMPLETE=1 lets set verbose                     # -> nothing (already supplied)
```

## Files

| File | Role in completion |
|------|--------------------|
| `lets/core.py` | `LETS_COMPLETE` check, `_complete`, `_print_verb_options`, matcher/options/exclusion helpers, `_available_settings`, `_split_regex_alternatives`. |
| `lets/api.py` | `@args` wrappers record `__lets_arg_matchers__` for introspection. |
| `completions/_lets` | zsh completion function; parses Lets' output into `compadd` candidates. |
| `completions/_lets.test.zsh` | zsh test harness (mocked `compdef`/`compadd`). |
| `example/demo.py` | reference plugin; `__lets_options__` wiring for callable matchers. |
| `tests/test_lets.py` | `TestComplete` unit tests. |
| `README.md` | user-facing installation instructions ("Shell completion"). |
