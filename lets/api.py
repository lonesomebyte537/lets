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

from .core import LetsCore, LetsExcept, Password, VerbProcessFuncType, _get_namespace, _registered_verbs
from typing import Any, Callable, Dict, List, Optional, Tuple
import os
import pty
import re
import select
import subprocess
import sys
import termios
import tty


def verb(verb_name: Optional[str] = None) -> Callable[[VerbProcessFuncType], VerbProcessFuncType]:
    """Decorate function as a verb handler.

    The name of the verb is inherited from the function name
    """
    # Get the namespace of the caller to allow plugins to specify the namespace of their verbs.
    namespace = _get_namespace()

    def decorator(func: VerbProcessFuncType) -> VerbProcessFuncType:
        _registered_verbs.append({"name": verb_name or func.__name__, "func": func, "namespace": namespace})
        return func

    return decorator


class ExecutionEnvironment:
    """ Class to represent execution environment """
    def _prepare_command(self, command: str) -> str:
        """ Prepare the command to be executed in the execution environment

        This function prepares the command to be executed in the execution environment.
        The command is modified to be executed in the execution environment.

        Args:
            command (str): The command to be executed in the execution environment.
        Returns:
            str: The prepared command to be executed in the execution environment.
        """
        return command


class DevContainer(ExecutionEnvironment):
    """ Class to represent devcontainer execution environment

    To use this, make sure devcontainer CLI is installed.

    Args:
        path (str): The path to the folder containing the .devcontainer folder.
        mount (tuple): A tuple representing the mount points.
            The first element is the source path on the host machine, and the
            second element is the target path inside the devcontainer.
    """
    def __init__(self, path: str, mount: Tuple[str, str]):
        self.path = path
        self.mount = mount

    def _prepare_command(self, command: str) -> str:
        """ Prepare the command to be executed inside the devcontainer

        This function prepares the command to be executed inside the devcontainer by
        mounting the specified source path to the target path and then executing
        the command in the target path.
        It also checks whether Lets was invoked from inside the devcontainer and
        if so, it executes the command directly without using devcontainer CLI.

        Args:
            command (str): The command to be executed inside the devcontainer.
        Returns:
            str: The prepared command to be executed inside the devcontainer.
        """
        if os.path.exists("/.dockerenv"):
            # Already running inside the devcontainer, so execute the command directly.
            return command
        # Change working directory inside the container to the same relative path as on the host machine to allow relative paths to work correctly.
        host_cwd = os.getcwd()
        relative_cwd = os.path.relpath(host_cwd, self.mount[0])
        command = f"sh -c \"cd {os.path.join(self.mount[1], relative_cwd)} && {command}\""
        return f"devcontainer exec --workspace-folder {self.path} -- {command}"


class Lets(LetsCore):
    ####################################################
    ######     Functions to initialize plugins    ######
    ####################################################
    # pylint: disable=too-many-arguments
    def register_setting(self, setting: str, description: str, options: List[str], default: Any,
            setting_type: Optional[type] = None) -> None:
        """Register the given setting for the given namespace."""
        namespace = _get_namespace()
        if self._registered_settings.get(namespace, {}).get(setting, None) is not None:
            raise ValueError(f"Setting {namespace}.{setting} already exists")

        if namespace not in self._registered_settings:
            self._registered_settings[namespace] = {}
        self._registered_settings[namespace][setting] = {
            "description": description,
            "options": options,
            "value": default,
            "type": setting_type or type(default),
        }

    ####################################################
    ######       Functions to inform users        ######
    ####################################################
    def info(self, text: str, title: bool = False, indent: int = 0) -> None:
        """Print a info string."""
        self._print("\033[97;1m" + text + "\033[0m" if title else text, indent=indent)

    def verbose(self, text: str) -> None:
        """Print a verbose string."""
        if self._registered_settings["lets"]["verbose"]["value"] == "on" or self._one_time_verbose:
            self._print("\033[38;5;245m" + text + "\033[0m")

    def warning(self, text: str) -> None:
        """Print a warning string."""
        self._print("\033[93m" + text + "\033[0m")

    def error(self, text: str) -> None:
        """Print an error string."""
        self._print("\033[38;5;203m" + text + "\033[0m")

    def evaluate(self, condition: bool, message: str, fatal: bool = True) -> None:
        """Evaluate the condition and print the message as error if the evaluation fails."""
        if not condition:
            if fatal:
                raise LetsExcept(message)
            else:
                self.error(message)

    ####################################################
    ###### Functions to manage persistent settings######
    ####################################################
    def get_setting(self, setting: str) -> Any:
        """Retrieve the setting value."""
        namespace = _get_namespace()
        settings = self._registered_settings.get(namespace, {})
        the_setting = settings.get(setting, None)
        return the_setting["value"] if the_setting else None

    def set_setting(self, setting_name: str, value: Any) -> int:
        """Set the setting"""
        namespace = _get_namespace()
        setting = self._resolve_setting(f"{namespace}.{setting_name}", allow_protected=True)
        if not setting:
            return -1
        if setting["value"] != value:
            setting["value"] = value
            self._save_settings()

    def remember(self, setting: str, value: Any, error: Optional[str] = None) -> Any:
        """Remember the given value for the given setting.
           If value is not a value, the remembered value will be returned.
           Otherwise the value itself is stored and returned."""
        namespace = _get_namespace()
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

    ####################################################
    ######    Functions to manipulate argument    ######
    ####################################################
    def extract(self, items_to_extract: List[str], items: List[str]) -> Dict[str, str]:
        """Extract the given items from the list of items and return them as a dictionary."""
        extracted_items = []
        lowercase_items = [a.lower() for a in items]
        for item in items_to_extract:
            if item.lower() in lowercase_items:
                item_index = lowercase_items.index(item.lower())
                extracted_items.append(item)
                del items[item_index : item_index + 1]
                del lowercase_items[item_index : item_index + 1]
        return extracted_items

    def fuzzy_find(self, text: str | List[str], options: List[str], unique=False, starts=False, case_sensitive=False, require_match=False, no_match_error=None) -> Optional[List[str]]:
        """ Searches for matching string(s) in the options.

        Find all strings in options that start with or contain the given text
        When a list is provided, the results for all texts are combined and returned.

        Args:
            text: The text to look for
            options: The list of strings to choose from
            unique: Exactly one match is expected
            starts: Only options that start with text should be considered a match
            no_match_error: The text to print when the text is not found. When a string is provided, the no_match_error is printed and
            sys.exit() is issued. Otherwise, [] is returned
            case_sensitive: Case sensitive search

        Returns:
            The list of matches
        """
        if not isinstance(text, list):
            text = [text]
        results = []
        for t in text:
            no_match_error = no_match_error or "No match found"
            regex = re.compile(("^" if starts else "") + re.escape(t), 0 if case_sensitive else re.IGNORECASE)
            subresults = [s for s in options if regex.search(s)]
            if require_match and (not subresults or (unique and len(subresults) != 1)):
                raise LetsExcept(f"{no_match_error}: '{t}'")
            results.extend(subresults)
        return results

    ####################################################
    ######    Functions to execute commands       ######
    ####################################################
    def execute(self, command: str, show_output: bool=True, env: Optional[ExecutionEnvironment] = None) -> tuple[int, str]:
        """ Execute the given command

        Execute the given command and preserve the ANSI codes in the output

        Args:
          command: The command to execute
          show_output: When true, the output of the command is printed to the terminal

        Returns:
          process return code
          terminal output
        """
        master_fd, slave_fd = pty.openpty()

        if env is not None:
            command = env._prepare_command(command)

        self.verbose(f"Executing command: {command}")

        stdin_fd = sys.stdin.fileno()
        stdin_is_tty = sys.stdin.isatty()
        original_tty_state = None
        if stdin_is_tty:
                original_tty_state = termios.tcgetattr(stdin_fd)
                tty.setraw(stdin_fd)

        process = subprocess.Popen(
            command,
            shell=True,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            text=False
        )

        os.close(slave_fd)

        captured = bytearray()

        forward_stdin = True
        master_open = True

        try:
            while master_open:
                read_fds = [master_fd]
                if forward_stdin:
                    read_fds.append(stdin_fd)

                ready, _, _ = select.select(read_fds, [], [], 0.1)

                if master_fd in ready:
                    try:
                        data = os.read(master_fd, 1024)
                    except OSError:
                        break

                    if not data:
                        master_open = False
                    else:
                        if show_output:
                            # Write raw to terminal (colors preserved)
                            sys.stdout.buffer.write(data)
                            sys.stdout.buffer.flush()

                        # Also capture
                        captured.extend(data)

                if forward_stdin and stdin_fd in ready:
                    try:
                        data = os.read(stdin_fd, 1024)
                    except OSError:
                        forward_stdin = False
                        data = b""

                    if not data:
                        forward_stdin = False
                    else:
                        os.write(master_fd, data)

                if process.poll() is not None and not master_open:
                    break
        finally:
            if stdin_is_tty and original_tty_state is not None:
                termios.tcsetattr(stdin_fd, termios.TCSADRAIN, original_tty_state)
            os.close(master_fd)

        process.wait()
        return process.returncode, captured.decode(errors="replace")

