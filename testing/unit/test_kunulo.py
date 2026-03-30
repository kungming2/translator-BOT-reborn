#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Unit tests for the Kunulo model class.

Run with:
    pytest test_kunulo.py -v
"""

from unittest.mock import MagicMock, patch

import pytest

from models.kunulo import Kunulo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_praw_submission(
    *,
    post_id: str = "1rorpb8",
    title: str = "[Community] Translation Challenge — 2026-03-09",
    created_utc: float = 1773034258.0,
    author_name: str = "translatorbot",
    permalink: str = "/r/translator/comments/1rorpb8/community_translation_challenge/",
) -> MagicMock:
    """Return a minimal mock PRAW Submission."""
    sub = MagicMock()
    sub.id = post_id
    sub.title = title
    sub.created_utc = created_utc
    sub.author.name = author_name
    sub.permalink = permalink
    sub.comments.list.return_value = []
    return sub


def make_praw_comment(
    *,
    comment_id: str = "abc123",
    author_name: str = "translatorbot",
    body: str = "",
) -> MagicMock:
    """Return a minimal mock PRAW Comment."""
    comment = MagicMock()
    comment.id = comment_id
    comment.author.name = author_name
    comment.body = body
    return comment


# ===========================================================================
# Kunulo tests
# ===========================================================================


class TestKunuloInit:
    def test_empty_init(self):
        k = Kunulo()
        assert k._data == {}
        assert k._op_thanks is False
        assert k._submission is None

    def test_init_with_data(self):
        data = {"comment_unknown": [("njpal88", None)]}
        k = Kunulo(data=data, op_thanks=True)
        assert k._data == data
        assert k._op_thanks is True


class TestKunuloRepr:
    def test_repr_contains_op_thanks(self):
        assert "OP Thanks: True" in repr(Kunulo(op_thanks=True))


class TestKunuloNormalizeEntry:
    def test_tuple_entry_unchanged(self):
        assert Kunulo._normalize_entry(("abc", ["x"])) == ("abc", ["x"])

    def test_string_entry_gets_none_data(self):
        assert Kunulo._normalize_entry("abc") == ("abc", None)


class TestKunuloExtractCjk:
    # Bodies are structured like real ANCHOR_CJK comments the bot posts,
    # where each looked-up character gets a markdown header entry.

    def test_single_character(self):
        body = (
            "[](#comment_cjk)\n\n"
            "# [夜](https://www.reddit.com/r/translator/search?q=%E5%A4%9C&restrict_sr=on)\n\n"
            "Some lookup content here.\n\n"
            "---\nZiwen: a bot for r/translator"
        )
        assert Kunulo._extract_cjk_characters(body) == ["夜"]

    def test_traditional_simplified_pair(self):
        # Bot posts traditional / simplified when both forms exist
        body = (
            "[](#comment_cjk)\n\n"
            "# [國 / 国](https://www.reddit.com/r/translator/search?q=%E5%9C%8B&restrict_sr=on)\n\n"
            "Some lookup content here."
        )
        assert Kunulo._extract_cjk_characters(body) == ["國"]

    def test_multiple_characters(self):
        # Realistic multi-character CJK lookup from models.md example
        body = (
            "[](#comment_cjk)\n\n"
            "# [实](https://www.reddit.com/r/translator/search?q=%E6%94%B9&restrict_sr=on)\n\n"
            "Meaning: change, reform\n\n"
            "# [现](https://www.reddit.com/r/translator/search?q=%E5%96%84&restrict_sr=on)\n\n"
            "Meaning: good, virtuous\n\n"
            "# [心](https://www.reddit.com/r/translator/search?q=%E5%BF%83&restrict_sr=on)\n\n"
            "Meaning: heart, mind\n\n"
            "---\nZiwen: a bot for r/translator"
        )
        assert Kunulo._extract_cjk_characters(body) == ["实", "现", "心"]

    def test_no_headers_returns_empty(self):
        # e.g. a comment_unknown body has no CJK headers
        body = (
            "**It looks like you have submitted a translation request tagged as 'Unknown'.** \n\n"
            "* Other community members may help you re-categorize your post.\n\n"
            "*Note: Your post has NOT been removed.*\n"
            "[](#comment_unknown)"
        )
        assert Kunulo._extract_cjk_characters(body) == []


class TestKunuloExtractWikipediaTerms:
    # Bodies are structured like real ANCHOR_WIKIPEDIA comments the bot posts,
    # where each looked-up term is a bold markdown link.

    def test_single_term(self):
        body = (
            "[](#comment_wikipedia)\n\n"
            "**[Romanization](https://en.wikipedia.org/wiki/Romanization)**\n\n"
            "Some article summary here.\n\n"
            "---\nZiwen: a bot for r/translator"
        )
        assert Kunulo._extract_wikipedia_terms(body) == ["Romanization"]

    def test_multiple_terms(self):
        body = (
            "[](#comment_wikipedia)\n\n"
            "**[Hanzi](https://en.wikipedia.org/wiki/Chinese_characters)**\n\n"
            "Summary of Hanzi article.\n\n"
            "**[Pinyin](https://en.wikipedia.org/wiki/Pinyin)**\n\n"
            "Summary of Pinyin article.\n\n"
            "---\nZiwen: a bot for r/translator"
        )
        assert Kunulo._extract_wikipedia_terms(body) == ["Hanzi", "Pinyin"]

    def test_no_terms_returns_empty(self):
        # e.g. a comment_long body has no bold Wikipedia links
        body = (
            "**Your translation request appears to be very long.** "
            "It may take a while for a translator to respond.\n\n"
            "*Note: Your post has NOT been removed.*\n"
            "[](#comment_long)"
        )
        assert Kunulo._extract_wikipedia_terms(body) == []


class TestKunuloAddEntry:
    def test_adds_tuple_entry(self):
        k = Kunulo()
        k._add_entry("comment_unknown", "abc123", None)
        assert k._data["comment_unknown"] == [("abc123", None)]

    def test_multiple_entries_same_tag(self):
        k = Kunulo()
        k._add_entry("comment_unknown", "abc123", None)
        k._add_entry("comment_unknown", "def456", None)
        assert len(k._data["comment_unknown"]) == 2


class TestKunuloGetTag:
    def test_returns_first_comment_id(self):
        k = Kunulo(data={"comment_unknown": [("njpal88", None), ("xyz999", None)]})
        assert k.get_tag("comment_unknown") == "njpal88"

    def test_returns_none_for_missing_tag(self):
        assert Kunulo().get_tag("comment_unknown") is None

    def test_handles_legacy_string_entry(self):
        k = Kunulo(data={"comment_unknown": ["njpal88"]})
        assert k.get_tag("comment_unknown") == "njpal88"


class TestKunuloGetTagWithData:
    def test_returns_tuple(self):
        chars = ["实", "现"]
        k = Kunulo(data={"comment_cjk": [("nk398my", chars)]})
        comment_id, data = k.get_tag_with_data("comment_cjk")
        assert comment_id == "nk398my"
        assert data == chars

    def test_missing_tag_returns_none_tuple(self):
        assert Kunulo().get_tag_with_data("comment_cjk") == (None, None)

    def test_out_of_range_index_returns_none_tuple(self):
        k = Kunulo(data={"comment_cjk": [("abc", None)]})
        assert k.get_tag_with_data("comment_cjk", index=5) == (None, None)


class TestKunuloGetAllEntries:
    def test_normalizes_legacy_entries(self):
        k = Kunulo(data={"comment_unknown": ["abc123", "def456"]})
        assert k.get_all_entries("comment_unknown") == [
            ("abc123", None),
            ("def456", None),
        ]

    def test_empty_for_missing_tag(self):
        assert Kunulo().get_all_entries("missing") == []


class TestKunuloGetCommentIds:
    def test_returns_ids_only(self):
        k = Kunulo(data={"comment_unknown": [("abc", None), ("def", ["x"])]})
        assert k.get_comment_ids("comment_unknown") == ["abc", "def"]

    def test_empty_list_for_missing_tag(self):
        assert Kunulo().get_comment_ids("missing") == []


class TestKunuloCheckExistingCjkLookups:
    def test_exact_match_found(self):
        k = Kunulo(data={"comment_cjk": [("abc123", ["实", "现", "心"])]})
        result = k.check_existing_cjk_lookups(["实", "现", "心"], exact_match=True)
        assert result is not None
        assert result["comment_id"] == "abc123"

    def test_exact_match_fails_on_different_chars(self):
        k = Kunulo(data={"comment_cjk": [("abc123", ["实", "现"])]})
        assert k.check_existing_cjk_lookups(["实", "心"], exact_match=True) is None

    def test_subset_match(self):
        k = Kunulo(data={"comment_cjk": [("abc123", ["实", "现", "心", "道"])]})
        result = k.check_existing_cjk_lookups(["实", "心"], exact_match=False)
        assert result is not None
        assert result["comment_id"] == "abc123"

    def test_empty_request_returns_none(self):
        k = Kunulo(data={"comment_cjk": [("abc123", ["实"])]})
        assert k.check_existing_cjk_lookups([]) is None

    def test_no_cjk_entries_returns_none(self):
        assert Kunulo().check_existing_cjk_lookups(["实"]) is None


class TestKunuloGetCommentPermalink:
    def test_generates_correct_url(self):
        k = Kunulo()
        k._submission = MagicMock()
        k._submission.permalink = "/r/translator/comments/1o7pjsn/some_post/"
        assert k.get_comment_permalink("njpal88") == (
            "https://www.reddit.com/r/translator/comments/1o7pjsn/some_post/njpal88"
        )

    def test_raises_without_submission(self):
        with pytest.raises(RuntimeError, match="No submission associated"):
            Kunulo().get_comment_permalink("abc123")


class TestKunuloToDict:
    def test_structure(self):
        k = Kunulo(data={"comment_unknown": [("njpal88", None)]}, op_thanks=True)
        result = k.to_dict()
        assert result["op_thanks"] is True
        entry = result["data"]["comment_unknown"][0]
        assert entry["comment_id"] == "njpal88"
        assert entry["associated_data"] is None

    def test_empty_kunulo(self):
        assert Kunulo().to_dict() == {"data": {}, "op_thanks": False}


class TestKunuloDelete:
    def test_raises_without_submission(self):
        k = Kunulo(data={"comment_unknown": [("abc", None)]})
        with pytest.raises(RuntimeError, match="No submission associated"):
            k.delete("comment_unknown")

    def test_returns_zero_for_missing_tag(self):
        k = Kunulo()
        k._submission = MagicMock()
        assert k.delete("nonexistent_tag") == 0

    def test_deletes_comments_and_removes_tag(self):
        k = Kunulo(data={"comment_unknown": [("abc123", None)]})
        k._submission = MagicMock()
        mock_comment = MagicMock()
        with patch("models.kunulo.REDDIT") as mock_reddit:
            mock_reddit.comment.return_value = mock_comment
            count = k.delete("comment_unknown")
        assert count == 1
        assert "comment_unknown" not in k._data
        mock_comment.delete.assert_called_once()

    def test_partial_failure_still_counts_successes(self):
        k = Kunulo(data={"comment_unknown": [("good_id", None), ("bad_id", None)]})
        k._submission = MagicMock()

        def side_effect(**kwargs):
            m = MagicMock()
            if kwargs.get("id") == "bad_id":
                m.delete.side_effect = Exception("API error")
            return m

        with patch("models.kunulo.REDDIT") as mock_reddit:
            mock_reddit.comment.side_effect = side_effect
            assert k.delete("comment_unknown") == 1


class TestKunuloAttrAccess:
    def test_dynamic_tag_access(self):
        k = Kunulo(data={"comment_unknown": [("abc", None)]})
        assert k.comment_unknown == [("abc", None)]

    def test_op_thanks_property(self):
        assert Kunulo(op_thanks=True).op_thanks is True

    def test_missing_attr_raises(self):
        with pytest.raises(AttributeError):
            _ = Kunulo().does_not_exist


class TestKunuloFromSubmission:
    def test_empty_submission_produces_empty_kunulo(self):
        sub = make_praw_submission()
        with (
            patch("models.kunulo.USERNAME", "translatorbot"),
            patch(
                "models.kunulo.SETTINGS",
                {
                    "thanks_keywords": ["thank", "thanks"],
                    "thanks_negation_keywords": ["no thanks"],
                },
            ),
        ):
            k = Kunulo.from_submission(sub)
        assert k._data == {}
        assert k._op_thanks is False

    def test_bot_comment_with_anchor_is_registered(self):
        sub = make_praw_submission(author_name="op_user")
        bot_comment = make_praw_comment(
            comment_id="njpal88",
            author_name="translatorbot",
            body="Some reply [](#comment_unknown)",
        )
        sub.comments.list.return_value = [bot_comment]
        with (
            patch("models.kunulo.USERNAME", "translatorbot"),
            patch(
                "models.kunulo.SETTINGS",
                {
                    "thanks_keywords": ["thank", "thanks"],
                    "thanks_negation_keywords": ["no thanks"],
                },
            ),
        ):
            k = Kunulo.from_submission(sub)
        assert "comment_unknown" in k._data
        assert k.get_tag("comment_unknown") == "njpal88"

    def test_op_thanks_detected(self):
        sub = make_praw_submission(author_name="op_user")
        sub.comments.list.return_value = [
            make_praw_comment(
                comment_id="xyz999", author_name="op_user", body="Thanks everyone!"
            )
        ]
        with (
            patch("models.kunulo.USERNAME", "translatorbot"),
            patch(
                "models.kunulo.SETTINGS",
                {
                    "thanks_keywords": ["thank", "thanks"],
                    "thanks_negation_keywords": [],
                },
            ),
        ):
            k = Kunulo.from_submission(sub)
        assert k._op_thanks is True

    def test_op_thanks_negated(self):
        sub = make_praw_submission(author_name="op_user")
        sub.comments.list.return_value = [
            make_praw_comment(
                comment_id="xyz999", author_name="op_user", body="No thanks, I'm fine."
            )
        ]
        with (
            patch("models.kunulo.USERNAME", "translatorbot"),
            patch(
                "models.kunulo.SETTINGS",
                {
                    "thanks_keywords": ["thanks"],
                    "thanks_negation_keywords": ["no thanks"],
                },
            ),
        ):
            k = Kunulo.from_submission(sub)
        assert k._op_thanks is False

    def test_cjk_comment_extracts_characters(self):
        sub = make_praw_submission(author_name="op_user")
        sub.comments.list.return_value = [
            make_praw_comment(
                comment_id="nk398my",
                author_name="translatorbot",
                body="[](#comment_cjk)\n\n# [实](url)\n\n# [现](url)\n",
            )
        ]
        with (
            patch("models.kunulo.USERNAME", "translatorbot"),
            patch(
                "models.kunulo.SETTINGS",
                {
                    "thanks_keywords": ["thanks"],
                    "thanks_negation_keywords": [],
                },
            ),
        ):
            k = Kunulo.from_submission(sub)
        _, data = k.get_tag_with_data("comment_cjk")
        chars = data["terms"]
        assert "实" in chars
        assert "现" in chars

    def test_submission_stored_on_instance(self):
        sub = make_praw_submission()
        with (
            patch("models.kunulo.USERNAME", "translatorbot"),
            patch(
                "models.kunulo.SETTINGS",
                {
                    "thanks_keywords": [],
                    "thanks_negation_keywords": [],
                },
            ),
        ):
            k = Kunulo.from_submission(sub)
        assert k._submission is sub

    def test_other_anchor_tags_are_registered(self):
        # Verify that single-data tags from responses.yaml (comment_long,
        # comment_claim, comment_duplicate, etc.) are stored with None data,
        # since they carry no extracted associated data.
        for tag in (
            "comment_long",
            "comment_claim",
            "comment_duplicate",
            "comment_unknown",
            "comment_defined_multiple",
            "comment_bad_title",
            "comment_english_only",
        ):
            sub = make_praw_submission(author_name="op_user")
            sub.comments.list.return_value = [
                make_praw_comment(
                    comment_id="abc001",
                    author_name="translatorbot",
                    body=f"Some bot comment text.\n\n[](#{tag})",
                )
            ]
            with (
                patch("models.kunulo.USERNAME", "translatorbot"),
                patch(
                    "models.kunulo.SETTINGS",
                    {
                        "thanks_keywords": [],
                        "thanks_negation_keywords": [],
                    },
                ),
            ):
                k = Kunulo.from_submission(sub)
            assert tag in k._data, f"Expected tag '{tag}' to be registered"
            assert k.get_tag(tag) == "abc001"
            assert k.get_tag_with_data(tag) == ("abc001", None)
