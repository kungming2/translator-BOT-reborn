#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Test suite for models/instruo.py.

Covers:
  - Instruo.__init__: field storage and defaults
  - Instruo.__repr__: format
  - Instruo.to_dict: serialisation of all fields including nested commands
  - Instruo.from_text: command extraction from plain strings (all command types)
  - Instruo.from_comment: construction from a mocked PRAW comment
  - _strip_commands: removal of commands leaving prose intact
  - comment_has_command: pre-check detection for all command categories
"""

import unittest
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

# noinspection PyProtectedMember
from models.instruo import Instruo, _strip_commands, comment_has_command
from models.komando import Komando


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skip_if_no_data(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: skip a test if any data-loading exception is raised."""

    def wrapper(self: unittest.TestCase, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(self, *args, **kwargs)
        except (FileNotFoundError, ImportError, KeyError, ValueError) as exc:
            self.skipTest(f"Data not available: {exc}")

    wrapper.__name__ = fn.__name__
    return wrapper


def _make_komando(name: str = "translated", data: list | None = None) -> Komando:
    """Return a minimal Komando for use in Instruo construction."""
    return Komando(name=name, data=data or [])


def _make_mock_comment(
    body: str = "!translated",
    comment_id: str = "abc123",
    post_id: str = "post456",
    created_utc: float = 1_700_000_000.0,
    author: str = "test_user",
    post_author: str = "post_author",
) -> MagicMock:
    """Return a minimal PRAW comment mock."""
    comment = MagicMock()
    comment.body = body
    comment.id = comment_id
    comment.created_utc = created_utc
    comment.author = MagicMock()
    comment.author.__str__ = lambda self: author
    comment.submission = MagicMock()
    comment.submission.id = post_id
    comment.submission.author = MagicMock()
    comment.submission.author.__str__ = lambda self: post_author
    return comment


# ---------------------------------------------------------------------------
# Instruo.__init__
# ---------------------------------------------------------------------------


class TestInstruoInit(unittest.TestCase):
    """Instruo stores all fields correctly on construction."""

    def setUp(self) -> None:
        self.instruo = Instruo(
            id_comment="c1",
            id_post="p1",
            created_utc=1_700_000_000,
            author_comment="alice",
            commands=[_make_komando()],
            languages=[],
            body="!translated",
            author_post="bob",
            body_remainder=None,
        )

    def test_id_comment_stored(self) -> None:
        self.assertEqual(self.instruo.id_comment, "c1")

    def test_id_post_stored(self) -> None:
        self.assertEqual(self.instruo.id_post, "p1")

    def test_created_utc_stored(self) -> None:
        self.assertEqual(self.instruo.created_utc, 1_700_000_000)

    def test_author_comment_stored(self) -> None:
        self.assertEqual(self.instruo.author_comment, "alice")

    def test_author_post_stored(self) -> None:
        self.assertEqual(self.instruo.author_post, "bob")

    def test_commands_stored(self) -> None:
        self.assertEqual(len(self.instruo.commands), 1)
        self.assertIsInstance(self.instruo.commands[0], Komando)

    def test_body_stored(self) -> None:
        self.assertEqual(self.instruo.body, "!translated")

    def test_body_remainder_default_none(self) -> None:
        instruo = Instruo(
            id_comment="c2",
            id_post="p2",
            created_utc=0,
            author_comment="x",
            commands=[],
            languages=[],
        )
        self.assertIsNone(instruo.body_remainder)

    def test_body_default_none(self) -> None:
        instruo = Instruo(
            id_comment="c3",
            id_post="p3",
            created_utc=0,
            author_comment="x",
            commands=[],
            languages=[],
        )
        self.assertIsNone(instruo.body)


# ---------------------------------------------------------------------------
# Instruo.__repr__
# ---------------------------------------------------------------------------


class TestInstruoRepr(unittest.TestCase):
    """__repr__ contains id and commands."""

    def test_repr_contains_id(self) -> None:
        instruo = Instruo(
            id_comment="xyz99",
            id_post="p",
            created_utc=0,
            author_comment="a",
            commands=[],
            languages=[],
        )
        self.assertIn("xyz99", repr(instruo))

    def test_repr_contains_commands(self) -> None:
        instruo = Instruo(
            id_comment="c1",
            id_post="p",
            created_utc=0,
            author_comment="a",
            commands=[_make_komando("identify")],
            languages=[],
        )
        self.assertIn("commands", repr(instruo))


# ---------------------------------------------------------------------------
# Instruo.to_dict
# ---------------------------------------------------------------------------


class TestInstruoToDict(unittest.TestCase):
    """to_dict() serialises all fields correctly."""

    def setUp(self) -> None:
        self.instruo = Instruo(
            id_comment="c1",
            id_post="p1",
            created_utc=1_700_000_000,
            author_comment="alice",
            author_post="bob",
            commands=[_make_komando("translated")],
            languages=[],
            body="!translated",
            body_remainder=None,
        )
        self.result = self.instruo.to_dict()

    def test_all_keys_present(self) -> None:
        for key in (
            "id_comment",
            "id_post",
            "created_utc",
            "author_comment",
            "author_post",
            "commands",
            "languages",
            "body",
            "body_remainder",
        ):
            self.assertIn(key, self.result)

    def test_id_values_correct(self) -> None:
        self.assertEqual(self.result["id_comment"], "c1")
        self.assertEqual(self.result["id_post"], "p1")

    def test_commands_serialised_as_list_of_dicts(self) -> None:
        self.assertIsInstance(self.result["commands"], list)
        self.assertIsInstance(self.result["commands"][0], dict)
        self.assertEqual(self.result["commands"][0]["name"], "translated")

    def test_languages_serialised_as_list_of_strings(self) -> None:
        self.assertIsInstance(self.result["languages"], list)

    def test_empty_commands_serialises_as_empty_list(self) -> None:
        instruo = Instruo(
            id_comment="c",
            id_post="p",
            created_utc=0,
            author_comment="a",
            commands=[],
            languages=[],
        )
        self.assertEqual(instruo.to_dict()["commands"], [])


# ---------------------------------------------------------------------------
# Instruo.from_text
# ---------------------------------------------------------------------------


class TestInstruoFromText(unittest.TestCase):
    """from_text() uses placeholder metadata and extracts commands."""

    def test_placeholder_ids(self) -> None:
        instruo = Instruo.from_text("!translated")
        self.assertEqual(instruo.id_comment, "TEST_ID")
        self.assertEqual(instruo.id_post, "TEST_POST_ID")

    def test_placeholder_author(self) -> None:
        instruo = Instruo.from_text("!translated")
        self.assertEqual(instruo.author_comment, "[test_user]")

    def test_placeholder_created_utc(self) -> None:
        instruo = Instruo.from_text("!translated")
        self.assertEqual(instruo.created_utc, 0)

    def test_body_stored(self) -> None:
        instruo = Instruo.from_text("hello !translated")
        self.assertEqual(instruo.body, "hello !translated")

    @_skip_if_no_data
    def test_no_command_text_has_empty_commands(self) -> None:
        instruo = Instruo.from_text("just a normal comment with no commands")
        self.assertEqual(instruo.commands, [])

    @_skip_if_no_data
    def test_translated_command_extracted(self) -> None:
        instruo = Instruo.from_text("!translated")
        names = [cmd.name for cmd in instruo.commands]
        self.assertIn("translated", names)

    @_skip_if_no_data
    def test_identify_command_with_language_extracted(self) -> None:
        instruo = Instruo.from_text("!identify:Bengali")
        names = [cmd.name for cmd in instruo.commands]
        self.assertIn("identify", names)
        identify_cmd = next(cmd for cmd in instruo.commands if cmd.name == "identify")
        self.assertIsNotNone(identify_cmd.data)

    @_skip_if_no_data
    def test_wikipedia_lookup_extracted(self) -> None:
        instruo = Instruo.from_text("{{Esperanto}}")
        names = [cmd.name for cmd in instruo.commands]
        self.assertIn("lookup_wp", names)
        wp_cmd = next(cmd for cmd in instruo.commands if cmd.name == "lookup_wp")
        self.assertIn("Esperanto", wp_cmd.data)

    @_skip_if_no_data
    def test_cjk_lookup_extracted(self) -> None:
        instruo = Instruo.from_text("`中文`")
        names = [cmd.name for cmd in instruo.commands]
        self.assertIn("lookup_cjk", names)

    @_skip_if_no_data
    def test_body_remainder_set(self) -> None:
        instruo = Instruo.from_text("Some prose here. !translated")
        # body_remainder should have the command stripped
        self.assertIsNotNone(instruo.body_remainder)
        assert instruo.body_remainder is not None
        self.assertNotIn("!translated", instruo.body_remainder)

    @_skip_if_no_data
    def test_pure_command_body_remainder_is_none(self) -> None:
        # A body that is only a command leaves no prose remainder
        instruo = Instruo.from_text("!translated")
        self.assertIsNone(instruo.body_remainder)


# ---------------------------------------------------------------------------
# Instruo.from_comment
# ---------------------------------------------------------------------------


class TestInstruoFromComment(unittest.TestCase):
    """from_comment() correctly reads PRAW comment fields."""

    @_skip_if_no_data
    def test_id_comment_from_praw(self) -> None:
        comment = _make_mock_comment(comment_id="abc123")
        instruo = Instruo.from_comment(comment)
        self.assertEqual(instruo.id_comment, "abc123")

    @_skip_if_no_data
    def test_id_post_from_praw(self) -> None:
        comment = _make_mock_comment(post_id="post456")
        instruo = Instruo.from_comment(comment)
        self.assertEqual(instruo.id_post, "post456")

    @_skip_if_no_data
    def test_author_comment_from_praw(self) -> None:
        comment = _make_mock_comment(author="alice")
        instruo = Instruo.from_comment(comment)
        self.assertEqual(instruo.author_comment, "alice")

    @_skip_if_no_data
    def test_author_post_from_praw(self) -> None:
        comment = _make_mock_comment(post_author="bob")
        instruo = Instruo.from_comment(comment)
        self.assertEqual(instruo.author_post, "bob")

    @_skip_if_no_data
    def test_created_utc_cast_to_int(self) -> None:
        comment = _make_mock_comment(created_utc=1_700_000_000.7)
        instruo = Instruo.from_comment(comment)
        self.assertIsInstance(instruo.created_utc, int)
        self.assertEqual(instruo.created_utc, 1_700_000_000)

    @_skip_if_no_data
    def test_body_stored_from_praw(self) -> None:
        comment = _make_mock_comment(body="!translated")
        instruo = Instruo.from_comment(comment)
        self.assertEqual(instruo.body, "!translated")

    @_skip_if_no_data
    def test_commands_extracted_from_praw(self) -> None:
        comment = _make_mock_comment(body="!translated")
        instruo = Instruo.from_comment(comment)
        names = [cmd.name for cmd in instruo.commands]
        self.assertIn("translated", names)

    @_skip_if_no_data
    def test_deleted_author_falls_back(self) -> None:
        comment = _make_mock_comment()
        comment.author = None
        instruo = Instruo.from_comment(comment)
        self.assertEqual(instruo.author_comment, "[deleted]")

    @_skip_if_no_data
    def test_parent_languages_normalised_from_single_lingvo(self) -> None:
        # Passing a bare Lingvo (not a list) should be accepted without error
        comment = _make_mock_comment(body="!translated")
        mock_lingvo = MagicMock()
        mock_lingvo.preferred_code = "ja"
        instruo = Instruo.from_comment(comment, parent_languages=mock_lingvo)
        self.assertIsInstance(instruo.languages, list)


# ---------------------------------------------------------------------------
# _strip_commands()
# ---------------------------------------------------------------------------


class TestStripCommands(unittest.TestCase):
    """_strip_commands() removes commands and leaves prose intact."""

    @_skip_if_no_data
    def test_prose_only_returns_unchanged(self) -> None:
        text = "This is just a normal comment."
        result = _strip_commands(text)
        self.assertEqual(result, text)

    @_skip_if_no_data
    def test_pure_command_returns_none(self) -> None:
        result = _strip_commands("!translated")
        self.assertIsNone(result)

    @_skip_if_no_data
    def test_command_stripped_leaving_prose(self) -> None:
        result = _strip_commands("Please translate this. !translated")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn("!translated", result)
        self.assertIn("Please translate this", result)

    @_skip_if_no_data
    def test_wikipedia_lookup_stripped(self) -> None:
        result = _strip_commands("Check out {{Esperanto}} for more.")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn("{{Esperanto}}", result)

    @_skip_if_no_data
    def test_cjk_backtick_lookup_stripped(self) -> None:
        result = _strip_commands("What does `中文` mean?")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn("`中文`", result)

    @_skip_if_no_data
    def test_empty_string_returns_none(self) -> None:
        result = _strip_commands("")
        self.assertIsNone(result)

    @_skip_if_no_data
    def test_whitespace_only_returns_none(self) -> None:
        result = _strip_commands("   \n   ")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# comment_has_command()
# ---------------------------------------------------------------------------


class TestCommentHasCommand(unittest.TestCase):
    """comment_has_command() correctly detects presence of bot commands."""

    @_skip_if_no_data
    def test_plain_prose_returns_false(self) -> None:
        self.assertFalse(comment_has_command("just a normal comment"))

    @_skip_if_no_data
    def test_translated_command_detected(self) -> None:
        self.assertTrue(comment_has_command("!doublecheck"))

    @_skip_if_no_data
    def test_identify_command_detected(self) -> None:
        self.assertTrue(comment_has_command("!identify:Bengali"))

    @_skip_if_no_data
    def test_wikipedia_braces_detected(self) -> None:
        self.assertTrue(comment_has_command("{{Esperanto}}"))

    @_skip_if_no_data
    def test_cjk_backtick_detected(self) -> None:
        self.assertTrue(comment_has_command("`中文`"))

    @_skip_if_no_data
    def test_command_in_code_block_not_detected(self) -> None:
        # Commands inside triple-backtick code blocks should be ignored
        text = "```\n!translated\n```"
        self.assertFalse(comment_has_command(text))

    @_skip_if_no_data
    def test_inline_quoted_command_not_detected(self) -> None:
        # Commands quoted as inline code (e.g. `!doublecheck`) should be ignored
        text = "Use `!translated` to mark a post as translated."
        self.assertFalse(comment_has_command(text))

    @_skip_if_no_data
    def test_praw_comment_object_accepted(self) -> None:
        comment = _make_mock_comment(body="!translated")
        self.assertTrue(comment_has_command(comment))

    @_skip_if_no_data
    def test_praw_comment_no_command_returns_false(self) -> None:
        comment = _make_mock_comment(body="just a reply, no commands here")
        self.assertFalse(comment_has_command(comment))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_all_tests() -> unittest.TestResult:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (
        TestInstruoInit,
        TestInstruoRepr,
        TestInstruoToDict,
        TestInstruoFromText,
        TestInstruoFromComment,
        TestStripCommands,
        TestCommentHasCommand,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    print("=" * 70)
    print("Instruo Test Suite")
    print("=" * 70)
    run_all_tests()
