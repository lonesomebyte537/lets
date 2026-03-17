# Installation

To run demo, make sure Lets is installed.
Then navigate to this example folder in a shell

Below commands are expected to be executed from this folder.

# Example sequence

```bash
$ # To know what verbs and settings are available:

$ lets help
...
AVAILABLE VERBS:
    demo.build: Build the application(s) with the given name.
    demo.flash: Flash the application with the given name.
  demo.monitor: Monitor the output of the board with the given
                name.
     demo.show: Show different kind of information.
...

AVAILABLE SETTINGS:
     demo.boards: Mapping between board names and the serial port
                  they are connected to. The name of the board can
                  be chosen arbitrarily and can be used in other
                  verbs to refer to the board.

$ # so the demo plugin offers 4 verbs and one setting. Let get more info on the show verb

$ lets help show
Usage: lets demo.show [OPTIONS]

SUMMARY
  Show different kind of information.

DESCRIPTION
  Use this verb to show different knd of information

OPTIONS
  - apps: Shows the different apps that can be built and flashed.
  - boards: Shows the registered boards and their corresponding
            serial ports.

EXAMPLES
  - lets show apps: Shows the different apps that can be built and
                    flashed.

$ # Okay, let's show all apps with option 'apps'

$ lets show apps  # this searches all subfolders under ./apps
Apps:
- hello_cruel_world
- hello_beautiful_world

$ # Two apps are part of the demo project. Let's build these

$ lets build hello # build both hello_world apps. Giving 'hello' will match both apps
Building hello_cruel_world
hello_cruel_world built successfully
Building hello_beautiful_world
hello_beautiful_world built successfully

$ lets build cruel beau # Multiple apps can be listed at the command line
Building hello_cruel_world
hello_cruel_world built successfully
Building hello_beautiful_world
hello_beautiful_world built successfully

$ # Now rebuild only hello_cruel_world
$ lets build cruel clean # Lets rebuild clean. 'cruel' resolvies to only hello_cruel_world 
Cleaning build directory for hello_cruel_world...
Building hello_cruel_world
hello_cruel_world built successfully

$ # With the app built, let's (virtually) flash it
$ lets flash
No boards registered. Please register a board first.

$ # Right, no boards yet, let's add two boards
$ lets add boards board1:/dev/ttyACM0 board2:/dev/ttyACM1
$ lets flash board1
Flashing hello_cruel_world on board board1
hello_cruel_world flashed successfully on board board1

$ # We made some modifications to the source code. Lets rebuild
$ lets build   # No need to pass the name of the app; it's remembered
$ lets flash   # No need to provide name and board; both are remembered

$ # Now monitor the terminal output
$ lets monitor # Board is remembered and the associated port can be retrieved
Showing monitor output for board board1 on port /dev/ttyACM0
```
