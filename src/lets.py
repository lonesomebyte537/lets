#!/usr/bin/env python3

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

"""Swiss army knife to simplify daily tasks."""
import importlib.util
import os
import pathlib
import shutil
import sys
import textwrap
from typing import Any, Callable, Dict, List, Optional, Set, TypedDict, Union

import yaml

VerbProcessFuncType = Callable[["Lets", str, List[str]], int]
VerbType = TypedDict("VerbType", {"context": str, "verb": str, "process_func": VerbProcessFuncType})
RegisteredVerbType = TypedDict("RegisteredVerbType", {"name": str, "func": VerbProcessFuncType})
SettingType = Dict[str, Any]
SettingContextType = Dict[str, SettingType]
SettingsType = Dict[str, SettingContextType]

# List of registered verbs. Each function decorated with @verb will be automatically registered
_registered_verbs: List[RegisteredVerbType] = []


def verb(verb_name: Optional[str] = None) -> Callable[[VerbProcessFuncType], VerbProcessFuncType]:
    """Decorate function as a verb handler.

    The name of the verb is inherited from the function name
    """

    def decorator(func: VerbProcessFuncType) -> VerbProcessFuncType:
        _registered_verbs.append({"name": verb_name or func.__name__, "func": func})
        return func

    return decorator


class Lets:
    """Class that offers methods to make simple calls to complex tasks."""

    def __init__(self) -> None:
        self._registered_settings: SettingsType = {}
        self._verbs: List[VerbType] = []
        self._load_plugins()
        _registered_verbs.append({"name": "help", "func": self.help})
        _registered_verbs.append({"name": "get", "func": self.get})
        _registered_verbs.append({"name": "set", "func": self.set})
        _registered_verbs.append({"name": "add", "func": self.add})
        _registered_verbs.append({"name": "remove", "func": self.remove})

        # Check whether verb already exists
        for _verb in _registered_verbs:
            context = _verb["func"].__module__
            name = _verb["name"]
            existing_verbs = [c for c in self._verbs if c["context"] == context and c["verb"] == name]
            if existing_verbs:
                raise ValueError(f"Verb {context}.{name} already exists")
            self._verbs.append({"context": context, "verb": name, "process_func": _verb["func"]})

        self.register_setting("lets", "plugin_folders", "List of folders to look for plugins", None, [])
        self.register_setting("lets", "verbose", "Sets the default verbose mode", ["on", "off"], "off")
        terminal_width = min((shutil.get_terminal_size()[0], 100))
        self._wrapper = textwrap.TextWrapper(width=terminal_width)
        self._load_settings()

    def _load_plugins(self) -> None:
        # Load folders from settings file. Other settings are loaded after all plugins are discovered
        file = pathlib.Path.home() / ".letsrc"
        folders = [pathlib.Path(os.path.realpath(__file__)).parent.resolve() / "plugins"]

        if file.exists():
            with open(file, "r", encoding="utf-8") as f:
                file_settings = yaml.safe_load(f)
                if "lets" in file_settings and "plugin_folders" in file_settings["lets"]:
                    folders.extend([pathlib.Path(f) for f in file_settings["lets"]["plugin_folders"]])

        for folder in folders:
            for module in os.listdir(folder):
                if (folder / module).is_file() and module.endswith(".py") and not module.startswith("_"):
                    spec = importlib.util.spec_from_file_location(module[:-3], str(folder / module))
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        mod.init(self)

    def _load_settings(self) -> None:
        # Check whether rc file exists
        file = pathlib.Path.home() / ".letsrc"
        if file.exists():
            # Yes, load the settings
            with open(file, "r", encoding="utf-8") as f:
                file_settings = yaml.safe_load(f)

            # Validate global settings and contexts first
            unknown_contexts = set(file_settings.keys()) - set(self._registered_settings.keys())
            if unknown_contexts:
                self.warning(f"Unknown contexts found in .letsrc: {' ,'.join(unknown_contexts)}")

            # Remove unknown contexts
            file_settings = {k:v for k,v in file_settings.items() if k not in unknown_contexts} 

            # Validate settings per context
            unknown_settings = {
                f"{c}.{s}" for c in file_settings for s in file_settings[c] if s not in self._registered_settings[c]
            }
            if unknown_settings:
                raise AttributeError(f"Unknown contexts found in .letsrc: {' ,'.join(unknown_settings)}")

            # Update the values
            for c in file_settings:
                for s in file_settings[c]:
                    self._registered_settings[c][s]["value"] = file_settings[c][s]

    def _save_settings(self) -> None:
        file = pathlib.Path.home() / ".letsrc"
        settings_dict = {
            c: {s: settings[s]["value"] for s in settings} for c, settings in self._registered_settings.items()
        }
        with open(file, "w", encoding="utf-8") as f:
            yaml.dump(settings_dict, f)

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
        context_setting = arg if "." in arg else "." + arg
        context, setting_name = context_setting.split(".", 1)

        if setting_name.startswith("_") and not allow_protected:
            self.error(f"Unknown setting: {arg}")
            return None

        settings = [
            (c, s)
            for c, settings in self._registered_settings.items()
            for s in settings
            if s == setting_name and context in ["", c]
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

    def get_setting(self, context: str, setting: str) -> Any:
        """Retrieve the setting value."""
        settings = self._registered_settings.get(context, {})
        the_setting = settings.get(setting, None)
        return the_setting["value"] if the_setting else None

    def set_setting(self, setting_name: str, value: Any) -> int:
        """Set the setting"""
        setting = self._resolve_setting(setting_name, allow_protected=True)
        if not setting:
            return -1
        if setting["value"] != value:
            setting["value"] = value
            self._save_settings()

    def info(self, text: str, title: bool = False, indent: int = 0) -> None:
        """Print a info string."""
        self._print("\033[97;1m" + text + "\033[0m" if title else text, indent=indent)

    def verbose(self, text: str) -> None:
        """Print a verbose string."""
        if self._registered_settings["lets"]["verbose"]["value"] == "on":
            self._print("\033[38;5;245m" + text + "\033[0m")

    def warning(self, text: str) -> None:
        """Print a warning string."""
        self._print("\033[93m" + text + "\033[0m")

    def error(self, text: str) -> None:
        """Print an error string."""
        self._print("\033[38;5;203m" + text + "\033[0m")

    def get(self, _: "Lets", __: str, args: List[str]) -> int:
        """Print the value of the given settings. If no settings are given, all settings are printed."""
        if len(args) < 1:
            args = [
                f"{context}.{setting}"
                for context, settings in self._registered_settings.items()
                for setting in settings
            ]
        results = {}
        for arg in args:
            # Check whether the argument matches a context
            if arg in self._registered_settings:
                settings = [(arg, s) for s in self._registered_settings[arg]]
            else:
                context_setting = arg if "." in arg else "." + arg
                context, setting = context_setting.split(".", 1)
                # Search matching settings
                settings = [
                    (c, s)
                    for c, settings in self._registered_settings.items()
                    for s in settings
                    if s == setting and context in ["", c]
                ]

            if not settings:
                self.error(f"Unknown setting {arg}")
                return -1

            for c, s in settings:
                # Skip protected settings
                if not s.startswith("_"):
                    results[f"{c}.{s}"] = self._registered_settings[c][s]["value"]
        max_length = max(len(r) for r in results)
        for s, v in results.items():
            value = ", ".join(v) if isinstance(v, list) else ", ".join([f"{key}:{val}" for key,val in v.items()]) if isinstance(v, dict) else v
            self.info(f"{s:>{max_length}}: {value}")
        return 0

    def set(self, _: "Lets", __: str, args: List[str]) -> int:
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

    def add(self, _: "Lets", __: str, args: List[str]) -> int:
        """Add values to a setting of type list or dict."""
        if len(args) < 2:
            self.warning("Usage: add [setting] [value1] [value2]")
            return -1

        setting = self._resolve_setting(args[0])
        if not setting:
            return -1

        if setting["type"] == list:
            setting["value"].extend(args[1:])
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

    def remove(self, _: "Lets", __: str, args: List[str]) -> int:
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

    # pylint: disable=too-many-arguments
    def register_setting(self, context: str, setting: str, description: str, options: List[str], default: Any) -> None:
        """Register the given setting for the given context."""
        if self._registered_settings.get(context, {}).get(setting, None) is not None:
            raise ValueError(f"Setting {context}.{setting} already exists")

        if context not in self._registered_settings:
            self._registered_settings[context] = {}
        self._registered_settings[context][setting] = {
            "description": description,
            "options": options,
            "value": default,
            "type": type(default),
        }

    @property
    def _available_settings(self) -> Set[str]:
        return {
            s["setting"] if context is None else f"{context}.{s['setting']}"
            for context, s in self._registered_settings.items()
        }

    # pylint: disable=too-many-statements, too-many-locals, too-many-branches
    def help(self, _: "Lets", __: str, args: List[str]) -> int:
        """Print this help."""

        def dissect_doc(func: VerbProcessFuncType) -> Dict[str, Any]:
            summary = ""
            description = ""
            options = []

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
            self.info(
                "  'Lets' simplifies the execution of common tasks. It takes a verb and options from the command \
line and runs the associated callback function to complete the task. A simple command could look like \
'lets build hello_world'. The options are chosen such that natural sentences can be constructed: 'lets \
build hello_world clean' to clean the output folder prior to building or 'lets set verbose on' to turn verbose mode \
permanently on. The order of options is arbitrary unless explicitly stated otherwise.",
                indent=2,
            )
            self.info("")
            self.info(
                "  Settings are used to store semi static options persistently such that these can be omitted from the \
command line. An example could be the build flavor which is typically set to 'debug'. Settings can typically be \
overridden at the command line. 'lets build hello_world release' will force hello world to be built for release even \
when the default is debug.",
                indent=2,
            )
            self.info("")
            self.info(
                "  A verb exists of two parts: [CONTEXT].[VERB_NAME]. The context is used to distinguish "
                "between identical verbs exposed by multiple contexts. "
                "If the verb name is unique across all contexts, the context can be omitted.",
                indent=2,
            )
            self.info("")
            self.info("AVAILABLE VERBS:", title=True)
            max_verb_length = max(len(c["context"] + c["verb"]) for c in self._verbs) + 1
            for cmd in self._verbs:
                self.info(
                    f"  {cmd['context']+'.'+cmd['verb']: >{max_verb_length}}: "
                    f"{dissect_doc(cmd['process_func'])['summary']}",
                    indent=max_verb_length + 4,
                )
            self.info("")
            self.info("Use 'lets help [VERB]' for more information about the verb")
            self.info("")
            self.info("AVAILABLE SETTINGS:", title=True)
            max_setting_length = max(
                len(context + name) + 1 for context, settings in self._registered_settings.items() for name in settings
            )
            for context, settings in self._registered_settings.items():
                for name, setting_info in settings.items():
                    # Skip protected settings
                    if name.startswith("_"):
                        continue
                    self.info(
                        f"  {context + '.' + name: >{max_setting_length}}: {setting_info['description']}",
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
                        + (", ".join([f"{c['context']}.{c['verb']}" for c in verbs]))
                    )
                    return -1
                if verbs:
                    cmd = verbs[0]
                    self.info(f"Usage: lets {cmd['context']}.{cmd['verb']} [OPTIONS]")
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
        context_verb = arg if "." in arg else "." + arg
        context, _verb = context_verb.split(".", 1)

        return [c for c in self._verbs if c["verb"] == _verb and context in ["", c["context"]]]

    def process_arguments(self, args: List[str]) -> int:
        """Process the arguments and executes the correct verb."""
        if not args:
            self.help(self, "help", [])
            return -1
        # Search matching verbs
        verbs = self._resolve_verbs(args[0])
        if len(verbs) > 1:
            self.warning(
                "Ambiguous verb found. Use one of following verbs: "
                + (", ".join([f"{c['context']}.{c['verb']}" for c in verbs]))
            )
            return -1
        if not verbs:
            self.error(f"Unknown verb {args[0]}")
            return -1
        _verb = verbs[0]

        # Check for lets settings
        if _verb["context"] != "lets" and _verb["verb"] not in ["get", "set"]:
            if "verbose" in args or "lets.verbose" in args:
                self._registered_settings["lets"]["verbose"]["value"] = "on"
                while "verbose" in args:
                    del args[args.index("verbose")]

        # Check whether the user is asking for help
        if "help" in args[1:]:
            self.help(self, "help", [_verb["context"] + "." + _verb["verb"]])
            return 0

        return _verb["process_func"](self, args[0], args[1:])


lets_instance = Lets()
sys.exit(lets_instance.process_arguments(sys.argv[1:]))
