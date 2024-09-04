# DESCRIPTION
'Lets' simplifies the execution of common tasks. It takes a verb and options from the command line and
runs the associated callback function to complete the task. A simple command could look like `lets build
hello_world`. The options are chosen such that natural sentences can be constructed: `lets build hello_world clean`
to clean the output folder prior to building or `lets set verbose on` to turn verbose mode permanently on. The order
of options is arbitrary unless explicitly stated otherwise.

Settings are used to store semi static options
persistently such that these can be omitted from the command line. An example could be the build flavor which is
typically set to `debug`. Settings can typically be overridden at the command line. `lets build hello_world release`
will force hello world to be built for release even when the default is debug.

A verb exists of two parts: `[CONTEXT].[VERB_NAME]`. The context is used to distinguish between identical verbs exposed
by multiple contexts. If the verb name is unique across all contexts, the context can be omitted.
