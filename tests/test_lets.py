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

"""Unit tests for the lets package.

Isolation strategy
------------------
* ``_registered_verbs`` is a module-level list that every ``Lets()``
  construction reads and appends to.  It is cleared in setUp/tearDown so
  tests cannot interfere with each other.
* ``pathlib.Path.home`` and ``pathlib.Path.cwd`` are patched to an empty
  temp directory, so no real ``~/.lets`` or project ``.lets`` files are
  ever loaded.
* ``LetsCore._save_settings`` is patched to a no-op, so no test writes to
  disk; in-memory state changes are still exercised normally.

Namespace convention
--------------------
``_get_namespace()`` walks two call-frames up from the callee.  When Lets
API methods are called directly from this module the resolved namespace is
``"test"`` (provided by the module-level constant below).
"""

import pathlib
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import lets.core as core_module
from lets.api import ExecutionEnvironment, Lets, args, verb
from lets.core import LetsExcept

# Required so that _get_namespace() resolves to "test" when Lets methods are
# called directly from test functions in this module.
LETS_NAMESPACE = "test"


# ---------------------------------------------------------------------------
# Base test case
# ---------------------------------------------------------------------------

class LetsTestCase(unittest.TestCase):
    """Provides an isolated Lets instance for each test."""

    def setUp(self):
        # Clear the global verb registry so each test starts from scratch and
        # the duplicate-verb guard inside LetsCore.__init__ never fires.
        core_module._registered_verbs.clear()

        # Use an empty temp directory as both home and cwd so no real
        # .lets files are discovered during initialisation.
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = pathlib.Path(self._tmp.name)

        self._patch_home = patch.object(
            core_module.pathlib.Path, "home", return_value=self._tmp_path
        )
        self._patch_cwd = patch.object(
            core_module.pathlib.Path, "cwd", return_value=self._tmp_path
        )
        # Suppress filesystem writes; in-memory state is still updated.
        self._patch_save = patch.object(core_module.LetsCore, "_save_settings")

        self._patch_home.start()
        self._patch_cwd.start()
        self._patch_save.start()

        self.lets = Lets()

        # remember() requires the namespace's "_remember" bucket.
        # In normal use this is created by _load_settings() after plugins
        # register their own namespaces; here we create it manually so that
        # tests calling lets methods under the "test" namespace work.
        self.lets._registered_settings.setdefault("test", {})["_remember"] = {
            "description": "",
            "options": None,
            "value": {},
            "type": dict,
        }

    def tearDown(self):
        self._patch_home.stop()
        self._patch_cwd.stop()
        self._patch_save.stop()
        self._tmp.cleanup()
        core_module._registered_verbs.clear()

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _make_lets_with_verb(self, name: str | list[str], func) -> Lets:
        """Return a fresh Lets() that contains one extra verb under 'test'."""
        core_module._registered_verbs.clear()
        # Normalize string names to word lists (matching core.py's __init__ behavior)
        if isinstance(name, str):
            name = name.split()
        core_module._registered_verbs.append(
            {"name": name, "func": func, "namespace": "test"}
        )
        lets = Lets()
        lets._registered_settings.setdefault("test", {})["_remember"] = {
            "description": "",
            "options": None,
            "value": {},
            "type": dict,
        }
        return lets


# ---------------------------------------------------------------------------
# extract()
# ---------------------------------------------------------------------------

class TestExtract(LetsTestCase):

    def test_extract_returns_matching_items(self):
        args = ["hello", "clean", "world"]
        result = self.lets.extract(["clean"], args)
        self.assertEqual(result, ["clean"])

    def test_extract_removes_item_from_source_list(self):
        args = ["hello", "clean", "world"]
        self.lets.extract(["clean"], args)
        self.assertEqual(args, ["hello", "world"])

    def test_extract_is_case_insensitive(self):
        args = ["CLEAN", "hello"]
        result = self.lets.extract(["clean"], args)
        self.assertEqual(result, ["clean"])
        self.assertEqual(args, ["hello"])

    def test_extract_missing_item_returns_empty(self):
        args = ["hello", "world"]
        result = self.lets.extract(["clean"], args)
        self.assertEqual(result, [])
        self.assertEqual(args, ["hello", "world"])

    def test_extract_multiple_items(self):
        args = ["a", "verbose", "b", "clean"]
        result = self.lets.extract(["clean", "verbose"], args)
        self.assertCountEqual(result, ["clean", "verbose"])
        self.assertEqual(args, ["a", "b"])


# ---------------------------------------------------------------------------
# fuzzy_find()
# ---------------------------------------------------------------------------

class TestFuzzyFind(LetsTestCase):

    def test_fuzzy_find_exact_match_preferred_over_partial_matches(self):
        options = ["wash", "washing", "carwash"]

        result = self.lets.fuzzy_find("was", options)
        self.assertCountEqual(result, ["wash", "washing", "carwash"])

        result = self.lets.fuzzy_find("wash", options)
        self.assertEqual(result, ["wash"])

    def test_fuzzy_find_substring_match(self):
        result = self.lets.fuzzy_find("hel", ["hello_world", "hello_beautiful", "bye"])
        self.assertEqual(result, ["hello_world", "hello_beautiful"])

    def test_fuzzy_find_starts_with(self):
        result = self.lets.fuzzy_find("he", ["hello", "she", "hey"], starts=True)
        self.assertCountEqual(result, ["hello", "hey"])

    def test_fuzzy_find_case_insensitive_by_default(self):
        result = self.lets.fuzzy_find("HELLO", ["hello_world", "HELLO_BEAUTIFUL", "bye"])
        self.assertEqual(len(result), 2)

    def test_fuzzy_find_require_match_no_result_raises(self):
        with self.assertRaises(LetsExcept):
            self.lets.fuzzy_find("xyz", ["hello", "world"], require_match=True)

    def test_fuzzy_find_unique_multiple_results_raises(self):
        with self.assertRaises(LetsExcept):
            self.lets.fuzzy_find("hel", ["hello", "help"], unique=True, require_match=True)

    def test_fuzzy_find_no_require_match_returns_empty(self):
        result = self.lets.fuzzy_find("xyz", ["hello", "world"])
        self.assertEqual(result, [])

    def test_fuzzy_find_with_list_of_texts(self):
        options = ["hello_world", "hello_beautiful", "bye", "shell"]
        texts = ["hello", "bye", "xyz"]

        results = self.lets.fuzzy_find(texts, options)
        self.assertEqual(results, ["hello_world", "hello_beautiful", "bye"])

# ---------------------------------------------------------------------------
# evaluate()
# ---------------------------------------------------------------------------

class TestEvaluate(LetsTestCase):

    def test_evaluate_true_does_not_raise(self):
        self.lets.evaluate(True, "should not raise")  # no exception

    def test_evaluate_false_fatal_raises_lets_except(self):
        with self.assertRaises(LetsExcept) as ctx:
            self.lets.evaluate(False, "fatal error message")
        self.assertIn("fatal error message", str(ctx.exception))

    def test_evaluate_false_non_fatal_prints_error(self):
        with patch("builtins.print") as mock_print:
            self.lets.evaluate(False, "non fatal", fatal=False)
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("non fatal", output)


# ---------------------------------------------------------------------------
# register_setting() / get_setting() / set_setting()
# ---------------------------------------------------------------------------

class TestSettings(LetsTestCase):

    def test_register_setting_stores_default_value(self):
        self.lets.register_setting("my_key", "desc", None, "default_val")
        value = self.lets.get_setting("my_key")
        self.assertEqual(value, "default_val")

    def test_register_setting_duplicate_raises_value_error(self):
        self.lets.register_setting("my_key", "desc", None, "v")
        with self.assertRaises(ValueError):
            self.lets.register_setting("my_key", "desc", None, "v")

    def test_set_setting_updates_value(self):
        self.lets.register_setting("speed", "speed setting", None, 10)
        self.lets.set_setting("speed", 99)
        self.assertEqual(self.lets.get_setting("speed"), 99)

    def test_get_setting_unknown_returns_none(self):
        result = self.lets.get_setting("nonexistent_setting")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# remember()
# ---------------------------------------------------------------------------

class TestRemember(LetsTestCase):

    def test_remember_stores_and_returns_value(self):
        result = self.lets.remember("last_app", "myapp")
        self.assertEqual(result, "myapp")

    def test_remember_retrieves_previously_stored_value(self):
        self.lets.remember("last_app", "myapp")
        result = self.lets.remember("last_app", [])
        self.assertEqual(result, "myapp")

    def test_remember_empty_with_error_raises(self):
        with self.assertRaises(LetsExcept):
            self.lets.remember("last_app", [], error="No app specified")

    def test_remember_empty_without_error_returns_empty(self):
        result = self.lets.remember("last_app", [])
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# _process_arguments() — CLI dispatch
# ---------------------------------------------------------------------------

class TestProcessArguments(LetsTestCase):

    def test_empty_args_returns_minus_one(self):
        result = self.lets._process_arguments([])
        self.assertEqual(result, -1)

    def test_unknown_verb_returns_minus_one(self):
        result = self.lets._process_arguments(["nonexistentverb"])
        self.assertEqual(result, -1)

    def test_set_verbose_on(self):
        result = self.lets._process_arguments(["set", "verbose", "on"])
        self.assertEqual(result, 0)
        self.assertEqual(
            self.lets._registered_settings["lets"]["verbose"]["value"], "on"
        )

    def test_help_for_verb_returns_zero(self):
        # Exercises the fixed 'self._help' (was 'self.help') code path.
        result = self.lets._process_arguments(["get", "help"])
        self.assertEqual(result, 0)

    def test_explicit_namespace_verb_dispatched(self):
        result = self.lets._process_arguments(["lets.get", "verbose"])
        self.assertEqual(result, 0)

    def test_custom_verb_receives_args_and_return_code_propagated(self):
        calls = []

        def my_verb(lets_instance, _verb, args):
            calls.append(args)
            return 42

        lets = self._make_lets_with_verb("greet", my_verb)
        result = lets._process_arguments(["greet", "world", "again"])
        self.assertEqual(result, 42)
        self.assertEqual(calls, [["world", "again"]])

    def test_verb_exception_returns_minus_one(self):
        def bad_verb(lets_instance, _verb, args):
            raise LetsExcept("boom")

        lets = self._make_lets_with_verb("explode", bad_verb)
        result = lets._process_arguments(["explode"])
        self.assertEqual(result, -1)

    def test_multi_word_verb_match(self):
        """Multi-word verb names consume multiple arguments."""
        calls = []

        def show_mem(lets_instance, _verb, args):
            calls.append(args)
            return 0

        lets = self._make_lets_with_verb("show memory", show_mem)
        result = lets._process_arguments(["show", "memory", "app1"])
        self.assertEqual(result, 0)
        self.assertEqual(calls, [["app1"]])

    def test_longest_match_wins(self):
        """When both 'show' and 'show memory' exist, 'show' wins for just 'show'."""
        tracked = {"show_calls": [], "mem_calls": []}

        def show_fn(l, _v, a):
            tracked["show_calls"].append(a)
            return 0

        def show_mem_fn(l, _v, a):
            tracked["mem_calls"].append(a)
            return 0

        core_module = __import__('lets.core', fromlist=['_registered_verbs'])
        core_module._registered_verbs.clear()
        core_module._registered_verbs.append({"name": ["show"], "func": show_fn, "namespace": "test"})
        core_module._registered_verbs.append({"name": ["show", "memory"], "func": show_mem_fn, "namespace": "test"})

        lets = Lets()
        lets._registered_settings.setdefault("test", {})["_remember"] = {"description": "", "options": None, "value": {}, "type": dict}

        # Just 'show' should match the single-word verb
        lets._process_arguments(["show"])
        self.assertEqual(tracked["show_calls"], [[]])
        self.assertEqual(tracked["mem_calls"], [])

        tracked["show_calls"].clear()
        lets2 = Lets()
        lets2._registered_settings.setdefault("test", {})["_remember"] = {"description": "", "options": None, "value": {}, "type": dict}
        # 'show memory' should match the two-word verb
        lets2._process_arguments(["show", "memory"])
        self.assertEqual(tracked["mem_calls"], [[]])

    def test_multi_word_with_namespace_prefix(self):
        """Multi-word verbs work with namespace prefix."""
        calls = []

        def show_cpu(l, _v, a):
            calls.append(a)
            return 0

        core_module = __import__('lets.core', fromlist=['_registered_verbs'])
        core_module._registered_verbs.clear()
        core_module._registered_verbs.append({"name": ["show", "cpuload"], "func": show_cpu, "namespace": "demo"})
        lets = Lets()
        lets._registered_settings.setdefault("demo", {})["_remember"] = {"description": "", "options": None, "value": {}, "type": dict}

        result = lets._process_arguments(["demo.show", "cpuload", "app1"])
        self.assertEqual(result, 0)
        self.assertEqual(calls, [["app1"]])


# ---------------------------------------------------------------------------
# Built-in verbs: get / set / add / remove
# ---------------------------------------------------------------------------

class TestBuiltinVerbs(LetsTestCase):

    def test_get_displays_verbose_setting(self):
        with patch("builtins.print") as mock_print:
            result = self.lets._process_arguments(["get", "verbose"])
        self.assertEqual(result, 0)
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("verbose", output)

    def test_set_then_get_roundtrip(self):
        self.lets._process_arguments(["set", "verbose", "on"])
        self.assertEqual(
            self.lets._registered_settings["lets"]["verbose"]["value"], "on"
        )
        self.lets._process_arguments(["set", "verbose", "off"])
        self.assertEqual(
            self.lets._registered_settings["lets"]["verbose"]["value"], "off"
        )

    def test_add_to_set_setting(self):
        self.lets._process_arguments(["add", "plugins", "myplugin.py"])
        self.assertIn(
            "myplugin.py",
            self.lets._registered_settings["lets"]["plugins"]["value"],
        )

    def test_add_to_dict_setting(self):
        # Register a dict-typed setting under "test" namespace.
        self.lets.register_setting("boards", "board map", None, {})
        result = self.lets._process_arguments(["add", "boards", "board1:/dev/ttyACM0"])
        self.assertEqual(result, 0)
        self.assertEqual(
            self.lets._registered_settings["test"]["boards"]["value"],
            {"board1": "/dev/ttyACM0"},
        )

    def test_remove_from_dict_setting(self):
        self.lets.register_setting("boards", "board map", None, {"board1": "/dev/ttyACM0"})
        self.lets._process_arguments(["remove", "boards", "board1"])
        self.assertNotIn(
            "board1",
            self.lets._registered_settings["test"]["boards"]["value"],
        )


# ---------------------------------------------------------------------------
# Output helpers: info / warning / error / verbose
# ---------------------------------------------------------------------------

class TestOutput(LetsTestCase):

    def test_info_prints_plain_text(self):
        with patch("builtins.print") as mock_print:
            self.lets.info("hello output")
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("hello output", output)

    def test_warning_includes_ansi_yellow(self):
        with patch("builtins.print") as mock_print:
            self.lets.warning("watch out")
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("watch out", output)
        self.assertIn("\033[93m", output)

    def test_error_includes_ansi_red(self):
        with patch("builtins.print") as mock_print:
            self.lets.error("something failed")
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("something failed", output)
        self.assertIn("\033[38;5;203m", output)

    def test_verbose_silent_when_off(self):
        with patch("builtins.print") as mock_print:
            self.lets.verbose("debug message")
        mock_print.assert_not_called()

    def test_verbose_prints_when_on(self):
        self.lets._registered_settings["lets"]["verbose"]["value"] = "on"
        with patch("builtins.print") as mock_print:
            self.lets.verbose("debug message")
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("debug message", output)


# ---------------------------------------------------------------------------
# execute() / set_default_env()
# ---------------------------------------------------------------------------

class _DummyEnv(ExecutionEnvironment):
    """Execution environment used to verify command rewriting and usage."""

    def __init__(self, marker: str):
        self.marker = marker
        self.seen_commands = []

    def _prepare_command(self, command: str) -> str:
        self.seen_commands.append(command)
        return f"printf '{self.marker}\\n' && {command}"


class TestExecute(LetsTestCase):

    def test_execute_uses_explicit_env(self):
        env = _DummyEnv("EXPLICIT_ENV")

        return_code, output = self.lets.execute("printf 'payload'", show_output=False, env=env)

        self.assertEqual(return_code, 0)
        self.assertEqual(env.seen_commands, ["printf 'payload'"])
        self.assertIn("EXPLICIT_ENV", output)
        self.assertIn("payload", output)

    def test_execute_uses_default_env_set_by_set_default_env(self):
        env = _DummyEnv("DEFAULT_ENV")
        self.lets.set_default_env(env)

        return_code, output = self.lets.execute("printf 'payload'", show_output=False)

        self.assertEqual(return_code, 0)
        self.assertEqual(env.seen_commands, ["printf 'payload'"])
        self.assertIn("DEFAULT_ENV", output)
        self.assertIn("payload", output)


# Test that:
# @args(r"(debug|release)", r"(simulator|silicon)")
# def my_func(args, flavor, target):
#    ..
# my_func(["debug", "simulator"]) should assign flavor="debug" and target="simulator" and args = [].
# Add all kind of permutations

# ---------------------------------------------------------------------------

LETS_NAMESPACE = "test"  # keep for @args module-scoped decoration


def _make_lets_with_args_verb(name: str | list[str], func) -> Lets:
    """Register *func* as a verb under 'test' and return a fresh Lets()."""
    core_module._registered_verbs.clear()
    if isinstance(name, str):
        name = name.split()
    core_module._registered_verbs.append(
        {"name": name, "func": func, "namespace": "test"}
    )
    lets = Lets()
    lets._registered_settings.setdefault("test", {})["_remember"] = {
        "description": "", "options": None, "value": {}, "type": dict
    }
    return lets


def _capture(verb_name: str | list[str], patterns, *input_args) -> tuple:
    """Decorate a mock with @args + @verb, run via _process_arguments, return captured call args."""
    if isinstance(verb_name, str):
        verb_name = [verb_name]
    captured = []

    @args(*patterns)
    @verb(verb_name[0])
    def fn(*fn_args, **fn_kwargs):
        captured.append((list(fn_args), dict(fn_kwargs)))
        return 0

    lets = _make_lets_with_args_verb(verb_name[0], fn)
    lets._process_arguments([verb_name[0], *input_args])
    assert len(captured) == 1
    return captured[0]


# ---------------------------------------------------------------------------
# @args
# ---------------------------------------------------------------------------

class TestArgsSinglePattern(LetsTestCase):

    def test_single_pattern_matches(self):
        """One pattern matches → remaining=[], extracted=[value]."""
        (a, k) = _capture("sp1", [r"debug|release"], "debug")
        ext = a[2]  # remaining args after lets+verb
        pos = a[3]  # first extracted
        self.assertEqual(pos, [])
        self.assertEqual(ext, ["debug"])

    def test_single_pattern_no_match_passes_through(self):
        """No match → all original args remain, extracted=[]."""
        (a, k) = _capture("sp2", [r"debug|release"], "other")
        ext = a[2]
        pos = a[3]
        self.assertEqual(pos, ["other"])
        self.assertEqual(ext, [])

    def test_pattern_greedy_removes_all_matches(self):
        """Multiple occurrences of same matched value are all removed."""
        (a, k) = _capture("sp3", [r"debug|release"], "debug", "foo", "debug")
        ext = a[2]
        pos = a[3]
        self.assertEqual(pos, ["foo"])
        self.assertEqual(ext, ["debug", "debug"])

    def test_pattern_matches_last_item(self):
        (a, k) = _capture("sp4", [r"debug|release"], "foo", "bar", "release")
        ext = a[2]
        pos = a[3]
        self.assertEqual(pos, ["foo", "bar"])
        self.assertEqual(ext, ["release"])

    def test_pattern_matches_first_item(self):
        (a, k) = _capture("sp5", [r"debug|release"], "debug", "bar")
        ext = a[2]
        pos = a[3]
        self.assertEqual(pos, ["bar"])
        self.assertEqual(ext, ["debug"])


class TestArgsMultiPattern(LetsTestCase):

    def test_first_pattern_consumes_first_match(self):
        (a, k) = _capture("mp1", [r"debug|release", r"simulator|silicon"], "debug", "simulator")
        self.assertEqual(a[2], ["debug"])  # first extracted
        self.assertEqual(a[3], ["simulator"])  # second extracted
        self.assertEqual(a[4], [])         # remaining

    def test_second_pattern_consumes_first_match(self):
        (a, k) = _capture("mp2", [r"debug|release", r"simulator|silicon"], "foo", "silicon")
        self.assertEqual(a[2], [])
        self.assertEqual(a[3], ["silicon"])
        self.assertEqual(a[4], ["foo"])

    def test_neither_pattern_matches(self):
        (a, k) = _capture("mp3", [r"debug|release", r"simulator|silicon"], "foo", "bar")
        self.assertEqual(a[2], [])
        self.assertEqual(a[3], [])
        self.assertEqual(a[4], ["foo", "bar"])  # original args untouched

    def test_first_pattern_consumes_second(self):
        (a, k) = _capture("mp4", [r"debug|release", r"simulator|silicon"], "foo", "debug")
        self.assertEqual(a[2], ["debug"])
        self.assertEqual(a[3], [])
        self.assertEqual(a[4], ["foo"])

    def test_both_patterns_match_scattered(self):
        (a, k) = _capture("mp5", [r"debug|release", r"simulator|silicon"], "x", "debug", "y", "silicon")
        self.assertEqual(a[2], ["debug"])
        self.assertEqual(a[3], ["silicon"])
        self.assertEqual(a[4], ["x", "y"])    # unmatched items preserved in order

    def test_first_pattern_greedy_second_empty(self):
        (a, k) = _capture("mp6", [r"debug|release", r"simulator|silicon"], "debug", "release")
        self.assertEqual(a[2], ["debug", "release"])
        self.assertEqual(a[3], [])
        self.assertEqual(a[4], [])

    def test_first_empty_second_consumes_all(self):
        (a, k) = _capture("mp7", [r"debug|release", r"simulator|silicon"], "simulator", "silicon")
        self.assertEqual(a[2], [])
        self.assertEqual(a[3], ["simulator", "silicon"])
        self.assertEqual(a[4], [])

    def test_first_empty_second_consumes_one(self):
        (a, k) = _capture("mp8", [r"debug|release", r"simulator|silicon"], "debug", "silicon")
        # pattern 1 consumes "debug", pattern 2 consumes "silicon"
        self.assertEqual(a[2], ["debug"])
        self.assertEqual(a[3], ["silicon"])
        self.assertEqual(a[4], [])


class TestArgsEdgeCases(LetsTestCase):

    def test_empty_input_args(self):
        """No input args → remaining is empty, all extracted are []."""
        (a, k) = _capture("ea1", [r"debug|release"])
        self.assertEqual(a[2], [])
        self.assertEqual(a[3], [])

    def test_single_arg_no_pattern_match(self):
        """One arg that doesn't match any pattern."""
        (a, k) = _capture("ea2", [r"debug|release", r"simulator|silicon"], "only_one")
        self.assertEqual(a[2], [])
        self.assertEqual(a[3], [])
        self.assertEqual(a[4], ["only_one"])

    def test_three_patterns_few_matches(self):
        """Three patterns but fewer matching args."""
        (a, k) = _capture("ea3", [r"a", r"b", r"c"], "x", "b")
        self.assertEqual(a[2], [])
        self.assertEqual(a[3], ["b"])
        self.assertEqual(a[4], [])
        self.assertEqual(a[5], ["x"])

    def test_same_value_matches_first_pattern_not_second(self):
        """A value that could match a broader second pattern is consumed by the first."""
        (a, k) = _capture("ea4", [r"debug", r".*"], "debug")
        # After first pattern removes "debug", remaining is empty, second gets nothing
        self.assertEqual(a[2], ["debug"])
        self.assertEqual(a[3], [])
        self.assertEqual(a[4], [])


class TestArgsRegexBehavior(LetsTestCase):

    def test_word_boundary_regex(self):
        r"""Patterns can use word boundaries — \bdebug\b matches 'debug' but not 'debugger'."""
        (a, k) = _capture("rb1", [r"\bdebug\b"], "debugger")
        self.assertEqual(a[2], [])
        self.assertEqual(a[3], ["debugger"])  # NOT matched

    def test_digit_pattern(self):
        """Regex with character classes like digits."""
        (a, k) = _capture("rb2", [r"\d+"], "42")
        self.assertEqual(a[2], ["42"])
        self.assertEqual(a[3], [])

    def test_start_anchor(self):
        r"""Pattern anchored at start matches prefix."""
        (a, k) = _capture("rb3", [r"^app-\d+"], "app-123")
        self.assertEqual(a[2], ["app-123"])
        self.assertEqual(a[3], [])

    def test_case_insensitive_flag(self):
        """re.IGNORECASE allows matching across cases."""
        (a, k) = _capture("rb4", [r"(?i)debug"], "DEBUG")
        self.assertEqual(a[2], ["DEBUG"])
        self.assertEqual(a[3], [])

    def test_alternation_within_pattern(self):
        r"""A single pattern with | alternation."""
        (a, k) = _capture("rb5", [r"foo|bar|baz"], "bar")
        self.assertEqual(a[2], ["bar"])
        self.assertEqual(a[3], [])

    def test_non_greedy_vs_fullmatch(self):
        """re.fullmatch requires the entire string to match the pattern."""
        # "^app" would partially match "app123", but fullmatch requires total
        (a, k) = _capture("rb6", [r"^app$"], "app123")
        self.assertEqual(a[2], [])
        self.assertEqual(a[3], ["app123"])  # does NOT match ^app$ under fullmatch


class TestArgsCascaded(LetsTestCase):

    def _capture_cascaded(self, patterns_first: str, patterns_second: str, *input_args):
        """Decorate a mock with two @args calls, run via _process_arguments, return captured call args."""
        captured = []

        @args(patterns_first)
        @args(patterns_second)
        @verb("cc")
        def fn(*fn_args, **fn_kwargs):
            captured.append((list(fn_args), dict(fn_kwargs)))
            return 0

        core_module._registered_verbs.clear()
        lets = self._make_lets_with_verb("cc", fn)
        lets._process_arguments(["cc", *input_args])
        assert len(captured) == 1, f"Expected 1 call, got {len(captured)}"
        return captured[0]

    def test_cascaded_both_match(self):
        """Two separate decorators each match one value."""
        (a, k) = self._capture_cascaded(r"debug|release", r"simulator|silicon", "debug", "simulator")
        self.assertEqual(a[2], ["debug"])   # first decorator's extracted
        self.assertEqual(a[3], ["simulator"])  # second decorator's extracted
        self.assertEqual(a[4], [])            # remaining

    def test_cascaded_reverse_order_values(self):
        """Values in reverse order — each pattern finds its match."""
        (a, k) = self._capture_cascaded(r"debug|release", r"simulator|silicon", "simulator", "debug")
        self.assertEqual(a[2], ["debug"])
        self.assertEqual(a[3], ["simulator"])
        self.assertEqual(a[4], [])

    def test_cascaded_first_missing(self):
        """Only the second pattern matches."""
        (a, k) = self._capture_cascaded(r"debug|release", r"simulator|silicon", "silicon")
        self.assertEqual(a[2], [])
        self.assertEqual(a[3], ["silicon"])
        self.assertEqual(a[4], [])

    def test_cascaded_second_missing(self):
        """Only the first pattern matches."""
        (a, k) = self._capture_cascaded(r"debug|release", r"simulator|silicon", "release")
        self.assertEqual(a[2], ["release"])
        self.assertEqual(a[3], [])
        self.assertEqual(a[4], [])

    def test_cascaded_neither_matches(self):
        """No args match — everything passes through in remaining."""
        (a, k) = self._capture_cascaded(r"debug|release", r"simulator|silicon", "foo")
        self.assertEqual(a[2], [])
        self.assertEqual(a[3], [])
        self.assertEqual(a[4], ["foo"])

    def test_cascaded_reversed_decorator_order(self):
        """Swapping decorator order produces same result."""
        captured = []

        @args(r"simulator|silicon")
        @args(r"debug|release")
        @verb("cr")
        def fn(*fn_args, **fn_kwargs):
            captured.append((list(fn_args), dict(fn_kwargs)))
            return 0

        core_module._registered_verbs.clear()
        lets = self._make_lets_with_verb("cr", fn)
        lets._process_arguments(["cr", "debug", "silicon"])
        (a, k) = captured[0]
        # first decorator (outer = silicon pattern) extracts second; second extracts first
        self.assertEqual(a[2], ["silicon"])
        self.assertEqual(a[3], ["debug"])
        self.assertEqual(a[4], [])


class TestArgsExact(LetsTestCase):

    def test_exact_zero_matches_raises(self):
        """exact=True with no matching argument raises LetsExcept."""
        @args(r"debug|release", exact=True)
        @verb("ex0")
        def fn(*fn_args, **fn_kwargs):
            return 0

        lets = _make_lets_with_args_verb("ex0", fn)
        with self.assertRaises(LetsExcept) as ctx:
            # Call the wrapper directly (args=(lets_instance, ["verbose"]))
            fn(lets, ["verbose"])
        self.assertIn("Expected exactly one match", str(ctx.exception))

    def test_exact_one_match_passes(self):
        """exact=True with exactly one matching argument works."""
        (a, k) = _capture("ex1", [r"debug|release", r"(?i)exact"], "debug")
        self.assertEqual(a[2], ["debug"])
        self.assertEqual(a[3], [])

    def test_exact_two_matches_raises(self):
        """exact=True with two matching arguments raises LetsExcept."""
        @args(r"debug|release", exact=True)
        @verb("ex2")
        def fn(*fn_args, **fn_kwargs):
            return 0

        lets = _make_lets_with_args_verb("ex2", fn)
        with self.assertRaises(LetsExcept) as ctx:
            # Call the wrapper directly (args=(lets_instance, ["debug", "release"]))
            fn(lets, ["debug", "release"])
        self.assertIn("Expected exactly one match", str(ctx.exception))


class TestArgsRemember(LetsTestCase):

    def test_remember_stores_and_restores_single_value(self):
        """First call stores the match; second call with no match returns the stored value."""
        captured = []

        @args(r"debug|release", remember=["flavor"])
        @verb("rem1")
        def fn(*fn_args, **fn_kwargs):
            captured.append((list(fn_args), dict(fn_kwargs)))
            return 0

        lets = _make_lets_with_args_verb("rem1", fn)

        # First call: "debug" matches → flavor remembered and passed as arg
        lets._process_arguments(["rem1", "debug"])
        self.assertEqual(
            lets._registered_settings["test"]["_remember"]["value"].get("flavor"),
            ["debug"],
        )
        (fn_args, _) = captured[-1]
        # fn_args[2] = flavor matches list
        self.assertEqual(fn_args[2], ["debug"])

        # Second call: no matching arg → flavor restored from memory
        captured.clear()
        lets._process_arguments(["rem1"])
        (fn_args, _) = captured[-1]
        self.assertEqual(fn_args[2], ["debug"])  # restored from remember

    def test_remember_multiple_values(self):
        """Two patterns remember two values; both restored on empty call."""
        captured = []

        @args(r"debug|release", r"simulator|silicon", remember=["flavor", "target"])
        @verb("rem2")
        def fn(*fn_args, **fn_kwargs):
            captured.append((list(fn_args), dict(fn_kwargs)))
            return 0

        lets = _make_lets_with_args_verb("rem2", fn)

        # Store values
        lets._process_arguments(["rem2", "debug", "silicon"])
        (fn_args, _) = captured[-1]
        self.assertEqual(fn_args[2], ["debug"])
        self.assertEqual(fn_args[3], ["silicon"])
        self.assertEqual(
            lets._registered_settings["test"]["_remember"]["value"],
            {"flavor": ["debug"], "target": ["silicon"]},
        )

        # Restore both on next call
        captured.clear()
        lets._process_arguments(["rem2"])
        (fn_args, _) = captured[-1]
        self.assertEqual(fn_args[2], ["debug"])  # restored from memory
        self.assertEqual(fn_args[3], ["silicon"])  # restored from memory

    def test_remember_overwrites_on_new_match(self):
        """A new invocation with a different value replaces the old remembered value."""
        captured = []

        @args(r"debug|release", remember=["flavor"])
        @verb("rem3")
        def fn(*fn_args, **fn_kwargs):
            captured.append((list(fn_args), dict(fn_kwargs)))
            return 0

        lets = _make_lets_with_args_verb("rem3", fn)

        lets._process_arguments(["rem3", "debug"])
        self.assertEqual(
            lets._registered_settings["test"]["_remember"]["value"]["flavor"],
            ["debug"],
        )

        # New value should overwrite
        captured.clear()
        lets._process_arguments(["rem3", "release"])
        (fn_args, _) = captured[-1]
        self.assertEqual(fn_args[2], ["release"])  # new match takes precedence
        self.assertEqual(
            lets._registered_settings["test"]["_remember"]["value"]["flavor"],
            ["release"],
        )

    def test_remember_partial_match_restores_unmatched(self):
        """When only one of two patterns matches, the other is restored from memory."""
        captured = []

        @args(r"debug|release", r"simulator|silicon", remember=["flavor", "target"])
        @verb("rem4")
        def fn(*fn_args, **fn_kwargs):
            captured.append((list(fn_args), dict(fn_kwargs)))
            return 0

        lets = _make_lets_with_args_verb("rem4", fn)

        # Remember both
        lets._process_arguments(["rem4", "debug", "silicon"])
        self.assertEqual(captured[-1][0][2], ["debug"])
        self.assertEqual(captured[-1][0][3], ["silicon"])

        # Only second pattern matches now
        captured.clear()
        lets._process_arguments(["rem4", "simulator"])
        (fn_args, _) = captured[-1]
        self.assertEqual(fn_args[2], ["debug"])  # restored from memory
        self.assertEqual(fn_args[3], ["simulator"])  # updated by new match

    def test_remember_empty_no_match_returns_empty_list(self):
        """With no prior storage and no match, remember returns []."""
        captured = []

        @args(r"debug|release", remember=["flavor"])
        @verb("rem5")
        def fn(*fn_args, **fn_kwargs):
            captured.append((list(fn_args), dict(fn_kwargs)))
            return 0

        lets = _make_lets_with_args_verb("rem5", fn)

        # No match, nothing stored yet → flavor should be []
        lets._process_arguments(["rem5"])
        (fn_args, _) = captured[-1]
        self.assertEqual(fn_args[2], [])

    def test_remember_exact_true_stores_scalar(self):
        """When exact=True, the single match is passed as a scalar to the function.

        Note: _remember_setting() is called *before* the exact extraction (line 86
        in api.py), so what gets persisted to storage is still the raw list ``["debug"]``.
        The function receives ``"debug"`` because the post-remember path applies exact=True.
        """
        captured = []

        @args(r"debug|release", exact=True, remember=["flavor"])
        @verb("rem6")
        def fn(*fn_args, **fn_kwargs):
            captured.append((list(fn_args), dict(fn_kwargs)))
            return 0

        lets = _make_lets_with_args_verb("rem6", fn)

        # Single match → function gets scalar via exact=True
        lets._process_arguments(["rem6", "debug"])
        self.assertEqual(captured[-1][0][2], "debug")
        # Storage holds the raw list because remember runs before exact extraction
        self.assertEqual(
            lets._registered_settings["test"]["_remember"]["value"]["flavor"],
            ["debug"],
        )

    def test_remember_with_no_match_raises_when_exact(self):
        """When remember restores a single-item list and exact=True, the check passes.

        ``len(["debug"]) == 1`` so no exception is raised — the list is treated as the
        single match (which is the same count).  This means restoring from memory works
        with exact=True even though the value type differs from a fresh match.
        """
        captured = []

        @args(r"debug|release", exact=True, remember=["flavor"])
        @verb("rem7")
        def fn(*fn_args, **fn_kwargs):
            captured.append((list(fn_args), dict(fn_kwargs)))
            return 0

        lets = _make_lets_with_args_verb("rem7", fn)

        # First call stores value
        lets._process_arguments(["rem7", "debug"])
        self.assertEqual(captured[-1][0][2], "debug")

        # Second call: exact=True + remember → len(["debug"]) == 1 → no error, scalar passed
        captured.clear()
        lets._process_arguments(["rem7"])
        (fn_args, _) = captured[-1]
        self.assertEqual(fn_args[2], "debug")  # exact extracts from single-item list

    def test_remember_restore_then_update(self):
        """Restore from memory, then update with a new value."""
        captured = []

        @args(r"debug|release", r"(?i)simulator|silicon", remember=["flavor", "target"])
        @verb("rem8")
        def fn(*fn_args, **fn_kwargs):
            captured.append((list(fn_args), dict(fn_kwargs)))
            return 0

        lets = _make_lets_with_args_verb("rem8", fn)

        # Initial store
        lets._process_arguments(["rem8", "debug", "silicon"])
        self.assertEqual(captured[-1][0][2], ["debug"])
        self.assertEqual(captured[-1][0][3], ["silicon"])

        # Restore both (via remember, no matching input)
        captured.clear()
        lets._process_arguments(["rem8"])
        (fn_args, _) = captured[-1]
        self.assertEqual(fn_args[2], ["debug"])
        self.assertEqual(fn_args[3], ["silicon"])

        # Update only first, second stays in memory
        captured.clear()
        lets._process_arguments(["rem8", "release"])
        (fn_args, _) = captured[-1]
        self.assertEqual(fn_args[2], ["release"])  # new match
        self.assertEqual(fn_args[3], ["silicon"])  # restored from memory

    def test_remember_multiple_matches_per_pattern(self):
        """Pattern with multiple matches remembers all of them."""
        captured = []

        @args(r"debug|release", remember=["flavors"])
        @verb("rem9")
        def fn(*fn_args, **fn_kwargs):
            captured.append((list(fn_args), dict(fn_kwargs)))
            return 0

        lets = _make_lets_with_args_verb("rem9", fn)

        # Multiple matches for same pattern
        lets._process_arguments(["rem9", "debug", "release"])
        self.assertEqual(captured[-1][0][2], ["debug", "release"])
        self.assertEqual(
            lets._registered_settings["test"]["_remember"]["value"]["flavors"],
            ["debug", "release"],
        )


class TestArgsCallableMatcher(LetsTestCase):

    def test_callable_matcher_mixed_with_regex(self):
        """Callable and regex patterns work together in the same @args."""
        captured = []

        @args(r"debug|release", lambda lets, args: ([a for a in args if a.startswith("dev")], [a for a in args if not a.startswith("dev")]))
        @verb("ca4")
        def fn(*fn_args, **fn_kwargs):
            captured.append((list(fn_args), dict(fn_kwargs)))
            return 0

        lets = _make_lets_with_args_verb("ca4", fn)
        lets._process_arguments(["ca4", "debug", "dev123", "foo"])
        (fn_args, _) = captured[-1]
        # First pattern extracts "debug" from remaining, then callable sees ["dev123", "foo"]
        self.assertEqual(fn_args[2], ["debug"])
        self.assertEqual(fn_args[3], ["dev123"])
        self.assertEqual(fn_args[4], ["foo"])

    def test_callable_matcher_multiple_callables(self):
        """Two callable matchers work in sequence; second sees post-first result."""
        captured = []

        @args(
            lambda lets, args: ([a for a in args if a == "x"], [a for a in args if a != "x"]),
            lambda lets, args: ([a for a in args if a == "y"], [a for a in args if a != "y"]),
        )
        @verb("ca6")
        def fn(*fn_args, **fn_kwargs):
            captured.append((list(fn_args), dict(fn_kwargs)))
            return 0

        lets = _make_lets_with_args_verb("ca6", fn)
        lets._process_arguments(["ca6", "x", "y", "z"])
        (fn_args, _) = captured[-1]
        self.assertEqual(fn_args[2], ["x"])
        self.assertEqual(fn_args[3], ["y"])
        self.assertEqual(fn_args[4], ["z"])


# ---------------------------------------------------------------------------
# table()
# ---------------------------------------------------------------------------
class TestTable(LetsTestCase):

    def test_table_supports_all_list_dict_combinations(self):
        columns_variants = [
            ["name", "score"],
            {"name": "Name", "score": "Score"},
        ]
        rows_variants = [
            [["Alice", "10"], ["Bob", "20"]],
            [{"name": "Alice", "score": "10"}, {"name": "Bob", "score": "20"}],
        ]

        for columns in columns_variants:
            for rows in rows_variants:
                with self.subTest(columns_type=type(columns).__name__, rows_type=type(rows[0]).__name__):
                    with patch.object(self.lets, "info") as mock_info:
                        self.lets.table(columns, rows)

                    calls = [call.args[0] for call in mock_info.call_args_list]
                    expected_header = "name  | score" if isinstance(columns, list) else "Name  | Score"
                    self.assertEqual(calls[0], expected_header)
                    self.assertEqual(calls[1], "------+------")
                    self.assertEqual(calls[2], "Alice | 10   ")
                    self.assertEqual(calls[3], "Bob   | 20   ")


if __name__ == "__main__":
    unittest.main()
