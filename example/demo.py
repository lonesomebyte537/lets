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

from lets import LetsExcept, verb
from pathlib import Path
from typing import List

# A unique namespace for the verbs and settings defined in this file.
LETS_NAMESPACE = "demo"

def _get_apps() -> List[str]:
    """ Helper method to get the app names from the ./apps directory. """
    return [p.name for p in (Path(__file__).parent / "apps").iterdir() if p.is_dir()]

def _match_apps(lets: "Lets", args: List[str], unique: bool = False) -> List[str]:
    """ Helper method to match the app names from the arguments. If no app name
        is given, it will return the last used apps.  """
    # The user can choose from the apps under the ./apps directory.
    apps = _get_apps()
    # Fuzzy find matching apps
    matched_apps = lets.fuzzy_find(args, apps, require_match=True, no_match_error="Unknown app")
    # Remember the apps or retrieve the remembered apps if no apps given
    matched_apps = lets.remember("last_used_apps", matched_apps, error="No app specified")
    lets.evaluate(not unique or len(matched_apps) == 1, "Multiple apps matched. Please specify one app: " + ", ".join(matched_apps))
    return matched_apps

def _match_boards(lets: "Lets", args: List[str], unique: bool = False) -> List[str]:
    """ Helper method to match the board names from the arguments. If no board
        name is given, it will return the last used boards.  """
    # The user can choose from the registered boards.
    boards = lets.get_setting("boards")
    lets.evaluate(boards, "No boards registered. Please register a board first.")
    # Extract the boards from the arguments
    matched_boards = lets.extract(list(boards.keys()), args)
    # Remember the boards or retrieve the remembered boards if no boards given
    return lets.remember("last_used_boards", matched_boards, error="No board specified")

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
def build(lets: "Lets", _verb: str, args: List[str]) -> int:
    """ Build the application(s) with the given name.

        The user can specify one or more app names as arguments. If no app name
        is given, it will build the last used apps.

        Options:
        - [apps]: One or more (fuzzy) names of apps to build. Apps are remembered.
        - clean: If specified, it will clean the build directory before building.

        Examples:
        - lets build hello_cruel_world clean: Cleans and builds hello_cruel_world
        - lets build hello: Build hello_cruel_world and hello_beautiful_world
        - lets build: Build the last used apps 
    """
    clean = lets.extract(['clean'], args)
    apps = _match_apps(lets, args)
    for app in apps:
        if clean:
            lets.info(f"Cleaning build directory for {app}...", title=True)
        lets.info(f"Building {app}", title=True)
        lets.execute(f"echo {app} built successfully")
    return 0

@verb()
def flash(lets: "Lets", _verb: str, args: List[str]) -> int:
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
    erase = lets.extract(['erase'], args)
    boards = _match_boards(lets, args, unique=True)
    apps = _match_apps(lets, args, unique=True)
    if erase:
        lets.info(f"Erasing board {boards[0]}...", title=True)
        lets.execute(f"echo Erased board {boards[0]}")
    lets.info(f"Flashing {apps[0]} on board {boards[0]}", title=True)
    lets.execute(f"echo {apps[0]} flashed successfully on board {boards[0]}")
    return 0

@verb()
def monitor(lets: "Lets", _verb: str, args: List[str]) -> int:
    """ Monitor the output of the board with the given name.

        The user can specify a board name as argument. If no board name is given,
        it will use the last used board. All output from the board will be shown in the terminal.
        The user can exit by pressing Ctrl+C.

        Options:
        - [board]: The name of the board to flash the app on. Boards are remembered.

        Examples:
        - lets monitor board1: Shows the monitor output for board1
    """
    boards = _match_boards(lets, args, unique=True)
    lets.evaluate(not args, "Unexpected arguments: " + ", ".join(args))
    port = lets.get_setting("boards").get(boards[0], "unknown")
    lets.info(f"Showing monitor output for board {boards[0]} on port {port}", title=True)
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