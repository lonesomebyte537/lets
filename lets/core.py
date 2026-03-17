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
Lets is a command‑line interpreter designed to make task execution more natural and intuitive.\
Instead of memorizing complex commands, users interact with Lets by typing simple, verb‑based instructions written in plain language.\
In addition, Lets offers a framework that makes it straightforward for developers to create plugins and extend functionality.
"""

import importlib.util
import inspect
import pathlib
import shutil
import sys
import textwrap
import yaml
from typing import Any, Callable, Dict, List, Optional, Set, TypedDict, Union

class LetsExcept(Exception):
    """ General exception that cause the execution to stop immediately """


class Password:
    """Type used for settings containing passwords."""


LETS_NAMESPACE = "lets"

VerbProcessFuncType = Callable[["Lets", str, List[str]], int]
VerbType = TypedDict("VerbType", {"namespace": str, "verb": str, "process_func": VerbProcessFuncType})
RegisteredVerbType = TypedDict("RegisteredVerbType", {"name": str, "func": VerbProcessFuncType})
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
        _registered_verbs.append({"name": "help", "func": self._help, "namespace": "lets"})
        _registered_verbs.append({"name": "get", "func": self._get, "namespace": "lets"})
        _registered_verbs.append({"name": "set", "func": self._set, "namespace": "lets"})
        _registered_verbs.append({"name": "add", "func": self._add, "namespace": "lets"})
        _registered_verbs.append({"name": "remove", "func": self._remove, "namespace": "lets"})
        # Check whether verb already exists
        for _verb in _registered_verbs:
            namespace = _verb["namespace"]
            name = _verb["name"]
            existing_verbs = [c for c in self._verbs if c["namespace"] == namespace and c["verb"] == name]
            if existing_verbs:
                raise ValueError(f"Verb {namespace}.{name} already exists")
            self._verbs.append({"namespace": namespace, "verb": name, "process_func": _verb["func"]})

        self.register_setting("plugins", "List of plugins to load at startup", None, set())
        self.register_setting("verbose", "Sets the default verbose mode", ["on", "off"], "off")
        terminal_width = min((shutil.get_terminal_size()[0], 100))
        self._wrapper = textwrap.TextWrapper(width=terminal_width)
        self._load_settings()

    def _load_plugins(self) -> None:
        # Load folders from settings file. Other settings are loaded after all plugins are discovered
        config_files = [pathlib.Path.home() / ".letsrc"]
        # Recurse upwards to find .letsrc files until the filesystem root is reached
        current = pathlib.Path.cwd()
        while True:
            candidate = current / ".letsrc"
            if candidate.is_file():
                config_files.append(candidate)
            if current.parent == current:
                # Reached filesystem root
                break
            current = current.parent

        plugin_files = []

        for file in config_files:
            if file.exists():
                with open(file, "r", encoding="utf-8") as f:
                    file_settings = yaml.safe_load(f)
                    if file_settings and "lets" in file_settings and "plugins" in file_settings["lets"]:
                        plugin_files.extend([pathlib.Path(f) for f in file_settings["lets"]["plugins"]])

        for file in plugin_files:
            spec = importlib.util.spec_from_file_location(file.stem, str(file))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
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
        file = pathlib.Path.home() / ".letsrc"
        if file.exists():
            # Yes, load the settings
            with open(file, "r", encoding="utf-8") as f:
                file_settings = yaml.safe_load(f)
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
            raise AttributeError(f"Unknown settings found in .letsrc: {' ,'.join(unknown_settings)}")

        # Update the values
        for c in file_settings:
            if c not in self._registered_settings:
                continue
            for s in file_settings[c]:
                self._registered_settings[c][s]["value"] = set(file_settings[c][s]) if \
                    self._registered_settings[c][s]["type"] == set else file_settings[c][s]

    def _save_settings(self) -> None:
        file = pathlib.Path.home() / ".letsrc"
        if file.exists():
            # Yes, load the settings
            with open(file, "r", encoding="utf-8") as f:
                file_settings = yaml.safe_load(f)
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

    @property
    def _available_settings(self) -> Set[str]:
        return {
            s["setting"] if namespace is None else f"{namespace}.{s['setting']}"
            for namespace, s in self._registered_settings.items()
        }

    # pylint: disable=too-many-statements, too-many-locals, too-many-branches
    def _help(self, _: "Lets", __: str, args: List[str]) -> int:
        """Print this help."""

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

        if not args:
            self.info("Usage: Lets [VERB] [OPTIONS]")
            self.info("")
            self.info("DESCRIPTION", title=True)
            self.info(sys.modules[__name__].__doc__)
            self.info("")
            self.info("AVAILABLE VERBS:", title=True)
            max_verb_length = max(len(c["namespace"] + c["verb"]) for c in self._verbs) + 1
            for cmd in self._verbs:
                self.info(
                    f"  {cmd['namespace']+'.'+cmd['verb']: >{max_verb_length}}: "
                    f"{dissect_doc(cmd['process_func'])['summary']}",
                    indent=max_verb_length + 4,
                )
            self.info("")
            self.info("Use 'lets help [VERB]' for more information about the verb")
            self.info("")
            self.info("AVAILABLE SETTINGS:", title=True)
            max_setting_length = max(
                len(namespace + name) + 1 for namespace, settings in self._registered_settings.items() for name in settings
            )
            for namespace, settings in self._registered_settings.items():
                for name, setting_info in settings.items():
                    # Skip protected settings
                    if name.startswith("_"):
                        continue
                    self.info(
                        f"  {namespace + '.' + name: >{max_setting_length}}: {setting_info['description']}",
                        indent=max_setting_length + 4,
                    )
            self.info("")
            self.info("Use 'lets help [SETTING]' for more information about the setting")
        else:
            for arg in args:
                verbs = self._resolve_verbs(arg)
                setting = self._resolve_setting(arg, True)
                if not verbs and not setting:
                    self.info(f"Unknown option: {arg}")
                    return -1
                if len(verbs) > 1:
                    self.warning(
                        "Ambiguous verb found. Use one of following verbs: "
                        + (", ".join([f"{c['namespace']}.{c['verb']}" for c in verbs]))
                    )
                    return -1
                if verbs:
                    cmd = verbs[0]
                    self.info(f"Usage: lets {cmd['namespace']}.{cmd['verb']} [OPTIONS]")
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
                        self.info(f"  lets set {arg} [key1:value1] [key2:value2] ...")
                        self.info(f"  lets add {arg} [key1:value1] [key2:value2] ...")
                        self.info(f"  lets remove {arg} [key1] [key2] ...")
                    elif setting["type"] == list:
                        self.info(f"  lets set {arg} [value1] [value2] ...")
                        self.info(f"  lets add {arg} [value1] [value2] ...")
                        self.info(f"  lets remove {arg} [value1] [value2] ...")
                    else:
                        self.info(
                            f"  lets set {arg} [{'|'.join(setting['options']) if setting['options'] else 'value'}]"
                        )
                    self.info(f"  lets get {arg}")
        return 0

    def _resolve_verbs(self, arg: str) -> List[VerbType]:
        namespace_verb = arg if "." in arg else "." + arg
        namespace, _verb = namespace_verb.split(".", 1)

        return [c for c in self._verbs if c["verb"] == _verb and namespace in ["", c["namespace"]]]

    def _process_arguments(self, args: List[str]) -> int:
        """Process the arguments and executes the correct verb."""
        if not args:
            self._help(self, "help", [])
            return -1
        # Search matching verbs
        verbs = self._resolve_verbs(args[0])
        if len(verbs) > 1:
            self.warning(
                "Ambiguous verb found. Use one of following verbs: "
                + (", ".join([f"{c['namespace']}.{c['verb']}" for c in verbs]))
            )
            return -1
        if not verbs:
            self.error(f"Unknown verb {args[0]}")
            return -1
        _verb = verbs[0]

        # Check for lets settings
        if _verb["namespace"] != "lets" and _verb["verb"] not in ["get", "set"]:
            if "verbose" in args or "lets.verbose" in args:
                self._registered_settings["lets"]["verbose"]["value"] = "on"
                while "verbose" in args:
                    del args[args.index("verbose")]

        # Check whether the user is asking for help
        if "help" in args[1:]:
            self._help(self, "help", [_verb["namespace"] + "." + _verb["verb"]])
            return 0

        try:
            result = _verb["process_func"](self, args[0], args[1:])
        except LetsExcept as e:
            self.error(str(e))
            return -1
        return result
