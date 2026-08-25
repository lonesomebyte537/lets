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

""" This plugin demonstrates how to create a plugin for Lets. It defines a few
verbs to build, flash and monitor applications on different boards. It also
shows how to use the fuzzy finding and remembering features of Lets to make the
user experience more natural and intuitive. 
"""

from lets import LetsExcept, args, verb
from pathlib import Path
from typing import List, Tuple

# A unique namespace for the verbs and settings defined in this file.
LETS_NAMESPACE = "demo"

def _get_apps() -> List[str]:
    """ Helper method to get the app names from the ./apps directory. """
    return [p.name for p in (Path(__file__).parent / "apps").iterdir() if p.is_dir()]

def _match_apps(lets: "Lets", args: List[str]) -> Tuple[List[str], List[str]]:
    """ Helper method to match the app names from the arguments.
        Note that this function expects all arguments to be applications hence
        this must be called when all other arguments are consumed (e.g. like 'clean'). """
    # The user can choose from the apps under the ./apps directory.
    apps = _get_apps()
    # Fuzzy find matching apps
    matched_apps = lets.fuzzy_find(args, apps, require_match=True, no_match_error="Unknown app")
    return matched_apps, args

def _match_boards(lets: "Lets", args: List[str]) -> Tuple[List[str], List[str]]:
    """ Helper method to match the board names from the arguments. """
    # The user can choose from the registered boards.
    boards = lets.get_setting("boards")
    lets.evaluate(boards, "No boards registered. Please register a board first.")
    # Extract the boards from the arguments
    matched_boards = lets.extract(list(boards.keys()), args)
    return matched_boards, args

def init(lets):
    # Register a setting for the boards.
    lets.register_setting(
        "boards",
        "Mapping between board names and the serial port they are connected to. "
        "The name of the board can be chosen arbitrarily and can be used in "
        "other verbs to refer to the board.",
        None, {}
    ) 

@verb()
@args(r"debug|release", exact=True, remember=["flavor"])
@args("clean")
@args(_match_apps, remember=["apps"])
def build(lets: "Lets", _verb: str, flavor: str, clean: List[str], apps: list[str], args: List[str]) -> int:
    """ Build the application(s) with the given name.

        The user can specify one or more app names as arguments. If no app name
        is given, it will build the last used apps.

        Options:
        - [apps]: One or more (fuzzy) names of apps to build. Apps are remembered.
        - [debug|release]: Build for debug or release
        - clean: If specified, it will clean the build directory before building.

        Examples:
        - lets build hello_cruel_world clean release: Cleans and builds hello_cruel_world in release mode
        - lets build hello debug: Build hello_cruel_world and hello_beautiful_world in debug
        - lets build: Build the last used apps 
    """
    for app in apps:
        if clean:
            lets.info(f"Cleaning build directory for {app}...", title=True)
        lets.info(f"Building {app} in {flavor}", title=True)
        lets.execute(f"echo {app} built successfully")
    return 0

@verb()
@args("erase")
@args(_match_boards, _match_apps, remember=["boards", "apps"])
def flash(lets: "Lets", _verb: str, erase: str, boards: list[str], apps: list[str], args: List[str]) -> int:
    """ Flash the application with the given name.

        The user can specify an application name and a board name as arguments.
        If no application or board name is given, it will use the last used
        application and board.

        Options:
        - [apps]: One or more (fuzzy) names of apps to build. Apps are remembered.
        - [board]: The name of the board to flash the app on. Boards are remembered.
        - erase: If specified, it will erase the board before flashing.

        Examples:
        - lets flash hello_cruel_world board1 erase: Erases and flashes the app on board1
        - lets flash board2: Flashes the last used app on board2
    """
    if not apps:
        raise LetsExcept("No apps provided")
    if not boards:
        raise LetsExcept("No boards provided")
    for board in boards:
        if erase:
            lets.info(f"Erasing board {board}...", title=True)
            lets.execute(f"echo Erased board {board}")
        for app in apps:
            lets.info(f"Flashing {app} on board {board}", title=True)
            lets.execute(f"echo {app} flashed successfully on board {board}")
    return 0

@verb()
@args(_match_boards, remember=["boards"], exact=True)
def monitor(lets: "Lets", _verb: str, board: str, args: List[str]) -> int:
    """ Monitor the output of the board with the given name.

        The user can specify a board name as argument. If no board name is given,
        it will use the last used board. All output from the board will be shown in the terminal.
        The user can exit by pressing Ctrl+C.

        Options:
        - [board]: The name of the board to flash the app on. Boards are remembered.

        Examples:
        - lets monitor board1: Shows the monitor output for board1
    """
    lets.evaluate(not args, "Unexpected arguments: " + ", ".join(args))
    port = lets.get_setting("boards").get(board, "unknown")
    lets.info(f"Showing monitor output for board {board} on port {port}", title=True)
    return 0

@verb()
def show_apps(lets: "Lets", _verb: str, args: List[str]) -> int:
    """ Shows the different apps that can be built and flashed. """
    lets.info("Apps:", title=True)
    for app in _get_apps():
        lets.info(f"- {app}")
    return 0

@verb()
def show_boards(lets: "Lets", _verb: str, args: List[str]) -> int:
    """ Shows the registered boards and their corresponding serial ports. """
    boards = lets.get_setting("boards")
    lets.info("Boards:", title=True)
    for board, port in boards.items():
        lets.info(f"- {board}: {port}")
    return 0