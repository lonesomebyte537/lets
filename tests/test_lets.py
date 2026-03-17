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
  temp directory, so no real ``~/.letsrc`` or project ``.letsrc`` files are
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
from unittest.mock import patch

import lets.core as core_module
from lets.api import Lets
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
        # .letsrc files are discovered during initialisation.
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

    def _make_lets_with_verb(self, name: str, func) -> Lets:
        """Return a fresh Lets() that contains one extra verb under 'test'."""
        core_module._registered_verbs.clear()
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


if __name__ == "__main__":
    unittest.main()
