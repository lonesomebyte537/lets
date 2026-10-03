# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""\
Lets is a command‑line interpreter designed to make task execution more natural and intuitive. \
Instead of memorizing complex commands, users interact with Lets by typing simple, verb‑based instructions written in plain language. \
In addition, Lets offers a framework that makes it straightforward for developers to create plugins and extend functionality.
"""

import importlib.util
import inspect
import os
import pathlib
import re
import shutil
import sys
import textwrap
import unicodedata
import yaml
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TypedDict, Union

class LetsExcept(Exception):
    """ General exception that cause the execution to stop immediately """


class Password:
    """Type used for settings containing passwords."""


def _display_width(s: str) -> int:
    """Return the display width of a string, accounting for wide Unicode characters."""
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)


def _display_ljust(s: str, width: int) -> str:
    """Left-justify a string to the given display width."""
    return s + ' ' * (width - _display_width(s))


def _split_regex_alternatives(pattern: str) -> List[str]:
    """Split a regular expression into its top-level alternatives.

    The pattern is split on '|' characters that are not nested inside a group
    (...) or a character class [...]. This is used to derive the concrete
    option values a regex matcher accepts (e.g. 'debug|release' ->
    ['debug', 'release']).
    """
    parts: List[str] = []
    current: List[str] = []
    depth = 0
    in_class = False
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if in_class:
            current.append(c)
            if c == "]":
                in_class = False
        elif c == "\\" and i + 1 < len(pattern):
            current.append(c)
            current.append(pattern[i + 1])
            i += 1
        elif c == "[":
            in_class = True
            current.append(c)
        elif c == "(":
            depth += 1
            current.append(c)
        elif c == ")":
            depth -= 1
            current.append(c)
        elif c == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(c)
        i += 1
    parts.append("".join(current))
    return parts


LETS_NAMESPACE = "lets"

VerbProcessFuncType = Callable[["Lets", str, List[str]], int]
ArgMatcherFuncType = Callable[["Lets", List[str]], Tuple[Any, List[str]]]

VerbType = TypedDict("VerbType", {"namespace": str, "verb": List[str], "process_func": VerbProcessFuncType})
RegisteredVerbType = TypedDict("RegisteredVerbType", {"name": List[str], "func": VerbProcessFuncType})
SettingType = Dict[str, Any]
SettingNameSpaceType = Dict[str, SettingType]
SettingsType = Dict[str, SettingNameSpaceType]

# List of registered verbs. Each function decorated with @verb will be automatically registered
_registered_verbs: List[RegisteredVerbType] = []

def _get_namespace() -> Optional[str]:
    """ Get the namespace of the caller."""
    caller_frame = inspect.currentframe().f_back.f_back
    caller_globals = caller_frame.f_globals
    namespace = caller_globals.get("LETS_NAMESPACE")
    if not namespace:
        raise ValueError("No namespace found. Please define LETS_NAMESPACE variable in the plugin module.")
    return namespace


class LetsCore:
    """Class that offers methods to make simple calls to complex tasks."""

    def __init__(self) -> None:
        self._registered_settings: SettingsType = {}
        self._verbs: List[VerbType] = []
        self._load_plugins()
        _registered_verbs.append({"name": ["help"], "func": self._help, "namespace": "lets"})
        _registered_verbs.append({"name": ["get"], "func": self._get, "namespace": "lets"})
        _registered_verbs.append({"name": ["set"], "func": self._set, "namespace": "lets"})
        _registered_verbs.append({"name": ["add"], "func": self._add, "namespace": "lets"})
        _registered_verbs.append({"name": ["remove"], "func": self._remove, "namespace": "lets"})
        # Check whether verb already exists and register new ones
        seen = {(c["namespace"], tuple(c["verb"])) for c in self._verbs}
        for _verb in _registered_verbs:
            name_val = _verb["name"]
            # Normalize: accept both strings ("show memory") and lists (["show", "memory"])
            key = (_verb["namespace"], tuple(name_val))
            if key in seen:
                continue  # already registered this verb
            seen.add(key)
            self._verbs.append({"namespace": _verb["namespace"], "verb": list(name_val), "process_func": _verb["func"]})

        self.register_setting("plugins", "List of plugins to load at startup", None, set())
        self.register_setting("verbose", "Sets the default verbose mode", ["on", "off"], "off")
        terminal_width = min((shutil.get_terminal_size()[0], 100))
        self._wrapper = textwrap.TextWrapper(width=terminal_width)
        self._load_settings()
        self._one_time_verbose = False

    def _load_plugins(self) -> None:
        # Load folders from settings file. Other settings are loaded after all plugins are discovered
        config_files = [pathlib.Path.home() / ".lets"]
        # Recurse upwards to find .lets files until the filesystem root is reached
        current = pathlib.Path.cwd()
        while True:
            candidate = current / ".lets"
            if candidate.is_file():
                config_files.append(candidate)
            if current.parent == current:
                # Reached filesystem root
                break
            current = current.parent

        plugin_files = []

        for file in list(set(config_files)):
            if file.exists():
                with open(file, "r", encoding="utf-8") as f:
                    file_settings = yaml.safe_load(f)
                    if file_settings and "lets" in file_settings and "plugins" in file_settings["lets"]:
                        plugin_files.extend([file.parent / f for f in file_settings["lets"]["plugins"]])

        for file in plugin_files:
            spec = importlib.util.spec_from_file_location(file.stem, str(file))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                # Register the dynamic plugin module so functions can resolve back to it via __module__.
                sys.modules[spec.name] = mod
                spec.loader.exec_module(mod)
                if hasattr(mod, "init"):
                    mod.init(self)
                # Get value of LETS_NAMESPACE
                if hasattr(mod, "LETS_NAMESPACE"):
                    namespace = getattr(mod, "LETS_NAMESPACE")
                    if namespace not in self._registered_settings:
                        self._registered_settings[namespace] = {}
                else:
                    raise ValueError(f"Plugin {file} does not define LETS_NAMESPACE variable")


    def _load_settings(self) -> None:
        # Check whether rc file exists
        file = pathlib.Path.home() / ".lets"
        if file.exists():
            # Yes, load the settings
            with open(file, "r", encoding="utf-8") as f:
                file_settings = yaml.safe_load(f)
            if not file_settings:
                file_settings = {}
        else:
            file_settings = {}

        # Add for every namespace the _remember setting if not already present to allow plugins to store remembered values
        for namespace in file_settings:
            if namespace not in self._registered_settings:
                continue
        
        # Add default setting "_remember" if not already present
        for namespace in self._registered_settings:
            if "_remember" not in self._registered_settings[namespace]:
                self._registered_settings[namespace]["_remember"] = {
                    "description": "Setting used to store remembered values for the remember function",
                    "options": None,
                    "value": {},
                    "type": dict,
                }

        # Validate settings per namespace
        unknown_settings = {
            f"{c}.{s}" for c in file_settings for s in file_settings[c] if c in self._registered_settings and s not in self._registered_settings[c] and s!="_remember"
        }
        if unknown_settings:
            self.warning(f"Unknown settings found in .lets: {' ,'.join(unknown_settings)}")

        # Update the values
        for c in file_settings:
            if c not in self._registered_settings:
                continue
            for s in file_settings[c]:
                if s not in self._registered_settings[c]:
                    continue
                self._registered_settings[c][s]["value"] = set(file_settings[c][s]) if \
                    self._registered_settings[c][s]["type"] == set else file_settings[c][s]

    def _save_settings(self) -> None:
        file = pathlib.Path.home() / ".lets"
        if file.exists():
            # Yes, load the settings
            with open(file, "r", encoding="utf-8") as f:
                file_settings = yaml.safe_load(f)
            if not file_settings:
                file_settings = {}
        else:
            file_settings = {}

        # Check for new namespaces
        for namespace in self._registered_settings:
            if namespace not in file_settings:
                file_settings[namespace] = {}

        # Merge the current settings with the settings from the file to prevent overwriting unknown settings
        for c in file_settings:
            if c not in self._registered_settings:
                continue
            file_settings[c].update({s: self._registered_settings[c][s]["value"] for s in self._registered_settings[c]})

        with open(file, "w", encoding="utf-8") as f:
            yaml.dump(file_settings, f)

    def _print(self, text: str, indent: int = 0) -> None:
        if text == "":
            print("")
            return
        self._wrapper.initial_indent = ""
        self._wrapper.subsequent_indent = indent * " "
        for idx, paragraph in enumerate(text.splitlines()):
            if idx:
                print("")
            for line in self._wrapper.wrap(paragraph):
                print(line)
            self._wrapper.initial_indent = self._wrapper.subsequent_indent

    def _resolve_setting(self, arg: str, graceful: bool = False, allow_protected: bool = False) -> Optional[SettingType]:
        namespace_setting = arg if "." in arg else "." + arg
        namespace, setting_name = namespace_setting.split(".", 1)

        if setting_name.startswith("_") and not allow_protected:
            self.error(f"Unknown setting: {arg}")
            return None

        settings = [
            (c, s)
            for c, settings in self._registered_settings.items()
            for s in settings
            if s == setting_name and namespace in ["", c]
        ]
        if len(settings) > 1:
            self.warning(
                "Ambiguous setting found. Use one of following settings: "
                + (", ".join([f"{s[0]}.{s[1]}" for s in settings]))
            )
            return None
        if not settings:
            if not graceful:
                self.error(f"Unknown setting {arg}")
            return None

        c, s = settings[0]
        setting = self._registered_settings[c][s]
        return setting

    def _remember_setting(self, setting: str, value: Any, namespace: str, error: Optional[str] = None) -> Any:
        """Remember the given value for the given setting.

        If value is None, [] or {}, the previously remembered value is
        returned. Otherwise the given value is stored and returned.
           
        Args:
            setting: The name of the setting to remember the value for
            value: The value to remember. If this is None, [] or {}, the remembered value will be returned instead.
            error: The error message to display if no value is given and there is no remembered value. If this is None, a default error message will be displayed.
        Returns:
            The remembered value if value is None, [] or {}, otherwise the value itself.
        """
        if namespace not in self._registered_settings:
            self._registered_settings[namespace] = {}
        if value is None or value == [] or value == {}:
            s = self._registered_settings[namespace]["_remember"]["value"].get(setting)
            if s is None and error:
                raise LetsExcept(error)
            return s if s else value
        else:
            self._registered_settings[namespace]["_remember"]["value"][setting] = value;
            self._save_settings()
            return value
    def _get(self, _: "Lets", __: str, args: List[str]) -> int:
        """Print the value of the given settings. If no settings are given, all settings are printed."""
        if len(args) < 1:
            args = [
                f"{namespace}.{setting}"
                for namespace, settings in self._registered_settings.items()
                for setting in settings
            ]
        results = {}
        for arg in args:
            # Check whether the argument matches a namespace
            if arg in self._registered_settings:
                settings = [(arg, s) for s in self._registered_settings[arg]]
            else:
                namespace_setting = arg if "." in arg else "." + arg
                namespace, setting = namespace_setting.split(".", 1)
                # Search matching settings
                settings = [
                    (c, s)
                    for c, settings in self._registered_settings.items()
                    for s in settings
                    if s == setting and namespace in ["", c]
                ]

            if not settings:
                self.error(f"Unknown setting {arg}")
                return -1

            for c, s in settings:
                # Skip protected settings
                if not s.startswith("_"):
                    results[f"{c}.{s}"] = self._registered_settings[c][s]
        max_length = max(len(r) for r in results)
        for name, setting in results.items():
            value = ", ".join(setting["value"]) if isinstance(setting["value"], list) or \
                isinstance(setting["value"], set) else ", ".join([f"{key}:{val}" for key,val in setting["value"].items()]) \
                if isinstance(setting["value"], dict) else "***" if setting["type"] == Password else setting["value"]
            self.info(f"{name:>{max_length}}: {value}")
        return 0

    def _set(self, _: "Lets", __: str, args: List[str]) -> int:
        """Assign the value to the given setting."""
        if len(args) < 2:
            self.warning("Usage: set [setting] [value1] [value2]")
            return -1

        setting = self._resolve_setting(args[0])
        if not setting:
            return -1

        if (
            setting["options"] is not None
            and (args[1].split(":", 1)[1] if setting["type"] is dict else args[1]) not in setting["options"]
        ):
            self.error(f"Unsupported value {args[1]}. Choose between {', '.join(setting['options'])}")
            return -1

        # Determine value from type of default value
        new_value: Union[str, List[str], Dict[str, str]] = args[1:] if setting["type"] in [list, dict] else args[1]
        if setting["type"] == dict:
            # Check whether all values are in the form of key:value
            invalid_values = [val for val in new_value if ":" not in val]
            if invalid_values:
                self.error(
                    f"Invalid values found for dictionary setting: {', '.join(invalid_values)}. "
                    + "Values must be in the form of key:value"
                )
                return -1
            new_value = {val[0]: val[1] for val in [key_val.split(":", 1) for key_val in new_value]}
        if setting["value"] != new_value:
            setting["value"] = new_value
            self._save_settings()
        return 0

    def _add(self, _: "Lets", __: str, args: List[str]) -> int:
        """Add values to a setting of type list or dict."""
        if len(args) < 2:
            self.warning("Usage: add [setting] [value1] [value2]")
            return -1

        setting = self._resolve_setting(args[0])
        if not setting:
            return -1

        if setting["type"] == list:
            setting["value"].extend(args[1:])
        elif setting["type"] == set:
            setting["value"].update(args[1:])
        elif setting["type"] == dict:
            # Check whether all values are in the form of key:value
            invalid_values = [val for val in args[1:] if ":" not in val]
            if invalid_values:
                self.error(
                    f"Invalid values found for dictionary setting: {', '.join(invalid_values)}. "
                    + "Values must be in the form of key:value"
                )
                return -1
            new_values = {val[0]: val[1] for val in [key_val.split(":", 1) for key_val in args[1:]]}
            setting["value"].update(new_values)
        else:
            self.error(f"Setting {args[0]} not a list or dict")
            return -1
        self._save_settings()
        return 0

    def _remove(self, _: "Lets", __: str, args: List[str]) -> int:
        """Remove values from a setting of type list or dict."""
        if len(args) < 2:
            self.warning("Usage: remove [setting] [value1] [value2]")
            return -1

        setting = self._resolve_setting(args[0])
        if not setting:
            return -1

        if setting["type"] == list:
            for val in args[1:]:
                if val in setting["value"]:
                    setting["value"].remove(val)
        elif setting["type"] == dict:
            for val in args[1:]:
                if val in setting["value"]:
                    del setting["value"][val]
        else:
            self.error(f"Setting {args[0]} not a list or dict")
            return -1
        self._save_settings()
        return 0

    def _complete(self, context: List[str]) -> int:
        """Print the options that are possible for the given command prefix.

        If no context is given, all possible first words (verbs) are printed,
        one per line. If the context resolves to a verb, the options accepted
        by that verb are printed, one per line, in the form
        'name=value1|value2'. Options whose matcher is already satisfied by one
        of the context arguments are omitted. If the context is a prefix of one
        or more verbs (including multi-word verbs), the matching verb names are
        printed.
        """
        if not context:
            seen: List[str] = []
            for verb in self._verbs:
                first = verb["verb"][0]
                if first not in seen:
                    seen.append(first)
                    print(first)
            return 0

        match = self._find_match(context)
        if match:
            self._print_verb_options(match[0], match[1])
            return 0

        # The context does not resolve to a full verb; print the verbs whose
        # name the context is a leading prefix of (multi-word verbs included).
        for verb in self._verbs:
            if self._verb_matches_context(verb["verb"], context):
                print(" ".join(verb["verb"]))
        return 0

    @staticmethod
    def _verb_matches_context(verb_words: List[str], context: List[str]) -> bool:
        """Return True when context is a leading prefix of a verb name.

        All context words except the last must equal the corresponding verb
        words; the last context word must be a prefix of the corresponding
        verb word. This lets a multi-word verb such as 'show apps' match the
        context 'show a'.
        """
        if not context or len(context) > len(verb_words):
            return False
        if verb_words[: len(context) - 1] != context[: len(context) - 1]:
            return False
        return verb_words[len(context) - 1].startswith(context[-1])

    def _print_verb_options(self, verb: VerbType, provided_args: Optional[List[str]] = None) -> None:
        """Print the options accepted by the given verb, one per line.

        Options with a remember name are printed as 'name=value1|value2' (or
        just 'name' when no values can be derived), options without a remember
        name (e.g. a 'clean' flag) are printed as their possible values, and
        an option is omitted when one of provided_args already satisfies its
        matcher. The built-in get/set verbs have no @args matchers; for them
        the registered settings are offered as the values of a 'config_name'
        parameter. The full option set is always printed; narrowing candidates
        to a partially typed word is left to the shell (zsh filters the
        candidates by the word being completed).
        """
        provided_args = provided_args or []
        matchers = self._collect_arg_matchers(verb["process_func"])

        if not matchers and verb["namespace"] == "lets" and verb["verb"] in (["get"], ["set"]):
            options = self._available_settings
            if options and not any(
                self._arg_covers_option(arg, option)
                for arg in provided_args
                for option in options
            ):
                print("config_name=" + "|".join(options))
            return

        for matcher, name in matchers:
            if self._matcher_satisfied(matcher, provided_args):
                continue
            options = self._matcher_options(matcher)
            if name is None:
                if options:
                    print("|".join(options))
            elif options:
                print(f"{name}=" + "|".join(options))
            else:
                print(name)

    def _matcher_satisfied(self, matcher: Any, provided_args: List[str]) -> bool:
        """Return True when a provided argument already satisfies the matcher.

        Regex matchers use the same full-match rule as @args. Callable
        matchers are checked against their advertised option values.
        """
        for arg in provided_args:
            if callable(matcher):
                if any(self._arg_covers_option(arg, o) for o in self._matcher_options(matcher)):
                    return True
            elif re.fullmatch(matcher, arg):
                return True
        return False

    @staticmethod
    def _arg_covers_option(arg: str, option: str) -> bool:
        """Return True when a provided argument covers an option value.

        Matches exactly or as a case-insensitive substring, mirroring the
        fuzzy matching used by the callable matchers.
        """
        return arg.lower() in option.lower()

    def _collect_arg_matchers(self, func: Any) -> List[Tuple[Any, Optional[str]]]:
        """Collect all (matcher, remember-name) pairs from the @args chain."""
        matchers: List[Tuple[Any, Optional[str]]] = []
        current = func
        while current is not None:
            own = getattr(current, "__lets_arg_matchers__", None)
            if own:
                matchers.extend(own)
            current = getattr(current, "__wrapped__", None)
        return matchers

    def _matcher_options(self, matcher: Any) -> List[str]:
        """Derive the concrete option values accepted by a single matcher."""
        if callable(matcher):
            options = getattr(matcher, "__lets_options__", None)
            if options is None:
                return []
            if callable(options):
                try:
                    options = options(self)
                except TypeError:
                    options = options()
            return [str(o) for o in options]
        alternatives = _split_regex_alternatives(matcher)
        clean = [a for a in alternatives if re.fullmatch(r"[A-Za-z0-9_.\-/]+", a)]
        return clean if clean else [a for a in alternatives if a]

    @property
    def _available_settings(self) -> List[str]:
        """Return all non-protected settings as 'namespace.name', sorted."""
        return sorted(
            f"{namespace}.{name}"
            for namespace, settings in self._registered_settings.items()
            for name in settings
            if not name.startswith("_")
        )

    # pylint: disable=too-many-statements, too-many-locals, too-many-branches
    def _help(self, _: "Lets", __: str, args: List[str]) -> int:
        """Print this help."""

        def _vstr(verb: VerbType) -> str:
            """Format a verb as 'namespace.verb_name' string."""
            return f"{verb['namespace']}.{' '.join(verb['verb'])}"

        def dissect_doc(func: VerbProcessFuncType) -> Dict[str, Any]:
            summary = ""
            description = ""
            options = []
            examples = []

            if func.__doc__:
                lines = [s.strip() for s in func.__doc__.splitlines()]
                description_index = lines.index("") if "" in lines else len(lines)
                summary = " ".join([l for l in lines[:description_index] if l])
                example_index = (lines.index("Examples:") if "Examples:" in lines else len(lines))
                option_index = (
                    lines[description_index:].index("Options:") + description_index
                    if "Options:" in lines[description_index:]
                    else example_index
                )
                description = "".join([l + " " if l else "\n" for l in lines[description_index + 1 : option_index]])
                options = [l for l in lines[option_index:example_index] if l]
                starts = [idx for idx, l in enumerate(options) if l.startswith("-")] + [len(options) + 1]
                options = [" ".join(options[starts[idx] : starts[idx + 1]]) for idx in range(len(starts) - 1)]

                examples = [l for l in lines[example_index:] if l]
                starts = [idx for idx, l in enumerate(examples) if l.startswith("-")] + [len(examples) + 1]
                examples = [" ".join(examples[starts[idx] : starts[idx + 1]]) for idx in range(len(starts) - 1)]
            return {"summary": summary, "description": description, "options": options, "examples": examples}

        def namespace_help(namespace: str, title: str) -> None:
            self.info(title, title=True, indent=2)
            # Get the description of the plugin from the docstring of the module the first verb is defined in
            plugin_verbs = [c for c in self._verbs if c["namespace"] == namespace]
            if plugin_verbs and plugin_verbs[0]["process_func"].__module__:
                mod = sys.modules.get(plugin_verbs[0]["process_func"].__module__)
                if mod is None:
                    mod = inspect.getmodule(plugin_verbs[0]["process_func"])
                if mod and mod.__doc__:
                    self.info("  " + "".join(["\n" if l.lstrip() == "" else l + " " for l in mod.__doc__.splitlines()]), indent=2)
                    self.info("")
            self.info("  VERBS:", title=True, indent=2)
            namespace_verbs = [c for c in self._verbs if c["namespace"] == namespace]
            max_verb_length = max(len(c["namespace"] + ' '.join(c["verb"])) for c in namespace_verbs) + 1
            for verb in namespace_verbs:
                self.info(
                    f"    {verb['namespace']+'.'+' '.join(verb['verb']): >{max_verb_length}}: "
                    f"{dissect_doc(verb['process_func'])['summary']}",
                        indent=max_verb_length + 6,
                    )
            self.info("")
            self.info("  SETTINGS:", title=True)
            namespace_settings = self._registered_settings[namespace] if namespace in self._registered_settings else {}
            max_setting_length = max(
                len(namespace + name) + 1 for name, setting_info in namespace_settings.items()
            )
            for name, setting_info in namespace_settings.items():
                # Skip protected settings
                if name.startswith("_"):
                    continue
                self.info(
                    f"  {namespace + '.' + name: >{max_setting_length}}: {setting_info['description']}",
                    indent=max_setting_length + 4,
                )

        if not args:
            self.info("Usage: Lets [VERB] [OPTIONS]")
            self.info("")
            namespace_help("lets", "DESCRIPTION")
            namespaces = list(set(c["namespace"] for c in self._verbs if c["namespace"] != "lets"))
            if namespaces:
                self.info("")
                self.info("AVAILABLE PLUGINS:", title=True)

            for namespace in namespaces:
                namespace_help(namespace, namespace.upper())
            self.info("")
            self.info("Use 'lets help [VERB]' for more information about a verb")
            self.info("Use 'lets help [SETTING]' for more information about a setting")
        else:
            # Use _find_match for proper multi-word verb resolution.
            match = self._find_match(args)
            if match:
                cmd = match[0]
                candidate = f"{cmd['namespace']}.{' '.join(cmd['verb'])}"
            else:
                candidate = " ".join(args)
            verbs = []
            if match:
                verbs = [match[0]]
            setting = self._resolve_setting(candidate, True)
            namespaces = list(set(c["namespace"] for c in self._verbs if c["namespace"].lower() == args[0].lower()))
            if not verbs and not setting and not namespaces:
                self.info(f"Unknown option: {candidate}")
                return -1
            if len(verbs) > 1:
                self.warning(
                    "Ambiguous verb found. Use one of following verbs: "
                    + (", ".join([f"{c['namespace']}.{_vstr(c)}" for c in verbs]))
                )
                return -1
            if verbs:
                cmd = verbs[0]
                self.info(f"Usage: lets {candidate} [OPTIONS]")
                doc = dissect_doc(cmd["process_func"])
                self.info("")
                self.info("SUMMARY", title=True)
                self.info(f"  {doc['summary']}", indent=2)
                if doc["description"]:
                    self.info("")
                    self.info("DESCRIPTION", title=True)
                    self.info("  " + doc["description"], indent=2)
                if doc["options"]:
                    self.info("")
                    self.info("OPTIONS", title=True)
                    for option in doc["options"]:
                        self.info("  " + option, indent=len(option.split(":")[0]) + 4)
                if doc["examples"]:
                    self.info("")
                    self.info("EXAMPLES", title=True)
                    for example in doc["examples"]:
                        self.info("  " + example, indent=len(example.split(":")[0]) + 4)
            if setting:
                self.info("DESCRIPTION", title=True)
                self.info("  " + setting["description"], indent=2)
                setting_type = (
                    "Dictionary" if setting["type"] == dict else "List" if setting["type"] == list else "String"
                )
                self.info(f"  Type: {setting_type}")
                self.info(f"  Current value: {setting['value']}", indent=2)
                if setting["options"]:
                    self.info(f"  Valid options: {', '.join(setting['options'])}")
                self.info("")
                self.info("USAGE", title=True)
                if setting["type"] == dict:
                    self.info(f"  lets set {candidate} [key1:value1] [key2:value2] ...")
                    self.info(f"  lets add {candidate} [key1:value1] [key2:value2] ...")
                    self.info(f"  lets remove {candidate} [key1] [key2] ...")
                elif setting["type"] == list:
                    self.info(f"  lets set {candidate} [value1] [value2] ...")
                    self.info(f"  lets add {candidate} [value1] [value2] ...")
                    self.info(f"  lets remove {candidate} [value1] [value2] ...")
                else:
                    self.info(
                        f"  lets set {candidate} [{'|'.join(setting['options']) if setting['options'] else 'value'}]"
                    )
                self.info(f"  lets get {candidate}")
            if namespaces:
                namespace_help(namespaces[0], "DESCRIPTION")
        return 0

    def _resolve_verbs(self, arg: str) -> List[VerbType]:
        namespace_verb = arg if "." in arg else "." + arg
        namespace, _verb = namespace_verb.split(".", 1)

        results = []
        for c in self._verbs:
            verb_str = ' '.join(c['verb'])
            if verb_str == _verb or verb_str.startswith(_verb + ' ') or (not _verb):
                if namespace in ["", c["namespace"]]:
                    results.append(c)
        return results

    def _find_match(self, args: List[str]) -> Optional[tuple]:
        """Find a verb match from the argument list using longest-match-first.

        Returns (verb_type, remaining_args) or None.
        The first word can optionally be preceded by a namespace+dot (e.g. "demo.show").
        """
        # Parse optional namespace prefix from args[0]
        ns = None
        if '.' in args[0] and args[0].split('.', 1)[0] in self._registered_settings:
            ns = args[0].split('.', 1)[0]

        for verb_type in sorted(self._verbs, key=lambda v: len(v['verb']), reverse=True):
            vwords_list = verb_type['verb']  # always a list now

            # Namespace filter (only when explicit ns was given)
            if ns is not None and verb_type['namespace'] != ns:
                continue

            # Determine candidate words for matching
            candidates = args[0].split('.', 1)[-1:] + args[1:]

            # Verb must exactly match the first len(vwords_list) candidate words
            if vwords_list != candidates[:len(vwords_list)]:
                continue

            return (verb_type, args[len(vwords_list):])

        return None

    def _process_arguments(self, args: List[str]) -> int:
        """Process the arguments and executes the correct verb."""
        # When LETS_COMPLETE is defined, print completions for the given
        # parameter list instead of executing the matched verb.
        if os.environ.get("LETS_COMPLETE"):
            return self._complete(args)
        if not args:
            self._help(self, "help", [])
            return -1
        # Find matching verb using longest-match-first for multi-word verbs
        match = self._find_match(args)
        if not match:
            self.error(f"Unknown verb {args[0]}")
            return -1
        _verb, args = match

        # Check for lets settings
        if _verb["namespace"] != "lets" and _verb["verb"][0] not in ["get", "set"]:
            if "verbose" in args or "lets.verbose" in args:
                self._one_time_verbose = True
                while "verbose" in args:
                    del args[args.index("verbose")]

        # Check whether the user is asking for help
        if "help" in args:
            self._help(self, "help", ['.'.join([_verb["namespace"]] + [_verb["verb"][0]])]+_verb["verb"][1:])
            return 0

        try:
            result = _verb["process_func"](self, None, args)
        except LetsExcept as e:
            self.error(str(e))
            return -1
        return result
