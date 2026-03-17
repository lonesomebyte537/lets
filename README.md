# DESCRIPTION

Lets is a command‑line interpreter designed to make task execution more natural and intuitive.
Instead of memorizing complex commands, users interact with Lets by typing simple, verb‑based instructions written in plain language.
In addition, Lets offers a framework that makes it straightforward for developers to create plugins and extend functionality.

An extensive working example is available under `./example/demo.py`. Check it out! 

## For the user

### Simple natural commands
Lets streamlines everyday operations by associating verbs with actions.
A verb combined with optional arguments triggers a specific function.
The available verbs and options are intentionally chosen so users can form commands that read like sentences.
Unless otherwise mentioned, the order of options doesn't matter.

Some example:

```
lets build hello_cruel_world
lets build hello_cruel_world clean
lets set verbose on
lets flash myboard
```

### Namespaces
Each verb has the form [NAMESPACE].[VERB_NAME].
Namespaces help avoid name conflicts between plugins.
If a verb is unique across all loaded plugins, the namespace can be omitted for convenience.

### Dynamic loading
Lets automatically walks up the directory tree to discover plugins.
Project‑local plugins load only when working inside that project’s folder.
Users can also create global plugins by placing them in `~/.letsrc`, making them available everywhere.

### Fuzzy
Plugin authors can enable fuzzy argument matching. Useful when users don’t remember exact names.

```
lets build cruel   # Builds hello_cruel_world
lets build world   # Builds hello_cruel_world and hello_beautiful_world
lets build hel     # Builds hello_cruel_world and hello_beautiful_world
```

For building, the fuzzy name could match multiple apps.
For some actions the name must be unique (e.g. you can't flash multiple apps).
The plugin developer is in control of this

### Persistent arguments
Lets can store certain arguments so users don’t have to repeat them across related commands.
For example, once you build an app, you can flash or monitor it without specifying its name again, unless you explicitly supply a new one.

```
lets build hello_cruel_world   # 'hello_cruel_world' will be remembered
lets flash myboard1            # The remembered app is used, 'myboard1' is remembered
lets monitor                   # The remembered board 'myboard1' is used to open terminal
lets monitor myboard2          # Don't use the remembered board but 'myboard2'
```

### Settings
Machine or user dependent settings can be easily configured by the user. Plugins can easily retrieve the value of the settings

```
lets add boards myboard1:/dev/ttyACM0 myboard2:/dev/ttyACM3
lets set autoclean on
lets get boards
```

### Verbose
Although Lets hides complex command syntax, users may want visibility into the underlying operations.
Verbose mode displays the executed commands and additional details.

```
lets build hello_world verbose   # Use verbose as argument to enable one-time verbose mode
lets set verbose on              # Turn verbose mode on permanently
lets set verbose off             # Turn verbose mode off again
```

### Rich output
All output is colored and decorated so info, warning, errors and verbose output
is visually distinct.

### Help
Lets provides detailed help for every verb, including available options, examples, and the current value of settings.

<code>
lets help build

Usage: lets demo.build [OPTIONS]

<b>SUMMARY</b><br>
  Build the application(s) with the given name.

<b>DESCRIPTION</b><br>
  The user can specify one or more app names as arguments. If no app name is given,
  it will build the last used apps.

<b>OPTIONS</b><br>
  <ul><li>clean: If specified, it will clean the build directory before building.</li></ul>

<b>EXAMPLES</b>
<ul>
  <li> lets build hello_cruel_world clean: Cleans and builds hello_cruel_world</li>
  <li>lets build hello: Build hello_cruel_world and hello_beautiful_world</li>
  <li>lets build: Build the last used apps</li>
  </ul>
</code>

## For the developer

### Verb
Use the verb decorator to register a verb and link it to a Python function.
Any arguments after the verb are forwarded to that function.

```python
@verb("build")
def build(lets: "Lets", _verb: str, args: List[str]) -> int:
    pass
```

### Settings
Plugins can declare their own settings, each with a description and a type.
Users can modify these settings; plugins can read and override them at runtime.

```python
def init(lets):
    # Register a setting for the boards.
    lets.register_setting(
        "boards",
        "Mapping between board names and the serial port they are connected to."
        "The name of the board can be chosen arbitrarily and can be used in"
        "other verbs to refer to the board.",
        None, {}
    ) 

@verb("flash")
def flash(lets: "Lets", _verb: str, args: List[str]) -> int:
    lets.get_setting("boards")
```

### Help
Provide help to the user in the docstring of the function. Lets will parse the docstring and format the help before presented to the user.

```python
@verb("build")
def build(lets: "Lets", _verb: str, args: List[str]) -> int:
    """ Build the application(s) with the given name.

        The user can specify one or more app names as arguments. If no app name
        is given, it will build the last used apps.

        Options:
        - clean: If specified, it will clean the build directory before building.

        Examples:
        - lets build hello_cruel_world clean: Cleans and builds hello_cruel_world
        - lets build hello: Build hello_cruel_world and hello_beautiful_world
        - lets build: Build the last used apps 
    """
```

### Fuzzy search
Plugins can use fuzzy matching to find items in a list, supporting constraints such as case‑sensitivity, at least one match or requiring a unique match.

```python
@verb("build")
def build(lets: "Lets", _verb: str, args: List[str]) -> int:
    lets.fuzzy_find(args[0], available_apps, require_match=True)
```

### Argument extraction
Lets can identify and extract specific options from the argument list and remove them once processed.

```python
@verb("build")
def build(lets: "Lets", _verb: str, args: List[str]) -> int:
    clean_build = lets.extract(['clean'], args)
```

### Result checking
Use `lets.evaluate` to check the result is as expected. Show an error or
in case of a fatal error, stop execution immediately.

### Persistent arguments
Plugins can store arguments so users don’t need to repeat them between commands.

```python
@verb("build")
def build(lets: "Lets", _verb: str, args: List[str]) -> int:
    # Check whether any app is provided at the command line
    apps = lets.extract(['hello_cruel_world', 'hello_beautiful_world'], args)
    # If apps were found, 'remember' will store these. Otherwise 'remember' will
    # return the remembered apps from previous command
    apps = lets.remember('last_used_apps', apps)
```

### Shell command invocation
lets.execute provides a clean way to run shell commands while preserving output formatting, including ANSI colors. The output and returncode are available to the plugin for further processing.

```python
@verb("build")
def build(lets: "Lets", _verb: str, args: List[str]) -> int:
    lets.execute("gcc --version")
```
