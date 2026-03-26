#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
from __future__ import annotations

"""
Interfaces with processes.ziwen_posts to help assess posts which might
be duplicates from the same user.
...

Logger tag: [MN:DUPE]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import hashlib
import logging
import re
import time
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations
from typing import TYPE_CHECKING

import numpy as np
import orjson
from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from config import logger as _base_logger
from database import db
from reddit.connection import is_mod, remove_content
from reddit.reddit_sender import reddit_reply
from responses import RESPONSE

from .usage_statistics import action_counter

if TYPE_CHECKING:
    from praw import Reddit
    from praw.models import Submission

    from models.ajo import Ajo

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "MN:DUPE"})


# ─── Duplicate detector class ─────────────────────────────────────────────────


class DuplicateDetector:
    """Enhanced duplicate detection system for Reddit posts."""

    def __init__(
        self,
        semantic_threshold: float = 0.85,
        fuzzy_threshold: int = 85,
        numerical_threshold: int = 5,
        age_limit_hours: int = 24,
        use_semantic: bool = True,
    ) -> None:
        """
        Initialize the duplicate detector.

        Args:
            semantic_threshold: Cosine similarity threshold (0-1) for semantic matching
            fuzzy_threshold: Fuzzy matching threshold (0-100)
            numerical_threshold: Threshold for numerical sequence detection
            age_limit_hours: Maximum age of posts to consider
            use_semantic: Whether to use semantic similarity (requires sentence-transformers)
        """
        self.semantic_threshold = semantic_threshold
        self.fuzzy_threshold = fuzzy_threshold
        self.numerical_threshold = numerical_threshold
        self.age_limit_hours = age_limit_hours

        self.model = None
        if use_semantic:
            try:
                logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
                logging.getLogger("tqdm").setLevel(logging.WARNING)
                self.model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.debug("Semantic similarity model loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load semantic model: {e}")
                self.model = None

    # ── Text normalisation & analysis ─────────────────────────────────────────

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalize text for better comparison.

        Args:
            text: Input string

        Returns:
            Normalized string
        """
        text = text.lower()
        text = re.sub(r"[!?]{2,}", "!", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\[.*?]\(.*?\)", "", text)  # Remove Markdown links
        text = re.sub(r"https?://\S+", "", text)  # Remove URLs
        return text.strip()

    @staticmethod
    def extract_numbers(text: str) -> list[int]:
        """
        Extract numbers from text with context awareness.

        Args:
            text: Input string

        Returns:
            List of integers found in the text
        """
        patterns = [
            r"#(\d+)",
            r"(?:episode|ep|part|pt|chapter|ch|letter)\s*(\d+)",
            r"\((?:pt|part)\s*(\d+)\)",
            r"(?<=[\s\.\(\[\-])\d+(?=[\s\.\)\]\-]|$)",
        ]

        numbers = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            numbers.extend([int(m) for m in matches])

        logger.debug(f"Extracted numbers from '{text}': {numbers}")
        return numbers

    def is_numerical_sequence(self, titles: list[str]) -> bool:
        """
        Detect numerical sequences in titles (e.g., episode/part numbers).

        Args:
            titles: List of title strings

        Returns:
            Boolean indicating if titles appear to be a sequence
        """
        if len(titles) < 2:
            return False

        number_sets = []
        for title in titles:
            nums = self.extract_numbers(title)
            if nums:
                number_sets.append(nums)

        if len(number_sets) < 2:
            return False

        logger.debug(f"Numbers found in titles: {number_sets}")

        last_numbers = [nums[-1] for nums in number_sets]
        differences = [
            b - a for a, b in zip(last_numbers, last_numbers[1:], strict=False)
        ]

        if not differences:
            return False

        avg_diff = sum(differences) / len(differences)
        logger.debug(f"Average numerical difference: {avg_diff}")

        if 0 < avg_diff <= 3:
            return True
        return len(set(differences)) == 1 and differences[0] != 0

    def create_title_hash(self, title: str) -> str:
        """
        Create a hash of the title for exact duplicate detection.

        Args:
            title: Title string

        Returns:
            SHA256 hash of normalized title
        """
        normalized = self.normalize_text(title)
        cleaned = re.sub(r"[^a-z\s]", "", normalized)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return hashlib.sha256(cleaned.encode()).hexdigest()

    # ── Similarity methods ────────────────────────────────────────────────────

    def calculate_semantic_similarity(self, titles: list[str]) -> float | None:
        """
        Calculate semantic similarity using sentence transformers.

        Args:
            titles: List of title strings

        Returns:
            Average pairwise cosine similarity (0-1)
        """
        if not self.model or len(titles) < 2:
            return None

        try:
            embeddings = self.model.encode(titles)
            similarities = []
            for i, j in combinations(range(len(titles)), 2):
                sim = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
                similarities.append(sim)
            return float(np.mean(similarities))
        except Exception as e:
            logger.error(f"Error calculating semantic similarity: {e}")
            return None

    @staticmethod
    def calculate_fuzzy_similarity(titles: list[str]) -> float | None:
        """
        Calculate fuzzy similarity (fallback method).

        Args:
            titles: List of title strings

        Returns:
            Average fuzzy similarity score (0-100)
        """
        if len(titles) < 2:
            return None

        similarities = []
        for i, j in combinations(range(len(titles)), 2):
            sim = fuzz.token_sort_ratio(titles[i], titles[j])
            similarities.append(sim)

        return sum(similarities) / len(similarities)

    @staticmethod
    def calculate_string_similarity(titles: list[str]) -> float | None:
        """
        Calculate string similarity using built-in difflib (no dependencies).

        Args:
            titles: List of title strings

        Returns:
            Average similarity ratio (0-100)
        """
        if len(titles) < 2:
            return None

        similarities = []
        for i, j in combinations(range(len(titles)), 2):
            ratio = SequenceMatcher(None, titles[i], titles[j]).ratio()
            similarities.append(ratio * 100)

        return sum(similarities) / len(similarities)

    # ── Detection ─────────────────────────────────────────────────────────────

    def detect_duplicates(
        self,
        list_posts: list[Submission],
    ) -> list[str] | None:
        """
        Main duplicate detection function with enhanced algorithms.

        Args:
            list_posts: List of Reddit PRAW submission objects

        Returns:
            List of post IDs to remove, or None
        """
        author_posts = defaultdict(list)
        actionable_posts = []
        current_time = int(time.time())

        for post in list_posts:
            try:
                post_author = post.author.name.lower()
            except AttributeError:
                continue

            time_delta = (current_time - post.created_utc) / 3600
            if time_delta > self.age_limit_hours:
                continue

            if post.approved:
                logger.debug(f"Post `{post.id}` already approved by moderator")
                continue

            if is_mod(post_author):
                logger.debug(f"Post `{post.id}` posted by moderator")
                continue

            normalized_title = self.normalize_text(post.title)
            author_posts[post_author].append(
                {
                    "id": post.id,
                    "title": normalized_title,
                    "created_utc": post.created_utc,
                    "original_title": post.title,
                }
            )

        for author, posts in author_posts.items():
            if len(posts) < 2:
                continue

            posts.sort(key=lambda x: x["created_utc"])
            titles = [p["title"] for p in posts]

            logger.debug(f"Analyzing {len(posts)} posts by u/{author}")

            if self.is_numerical_sequence(titles):
                logger.info(f"Posts by u/{author} appear to be a series. Skipping.")
                continue

            similarity_score = None
            method_used = None

            if self.model:
                similarity_score = self.calculate_semantic_similarity(titles)
                if similarity_score is not None:
                    method_used = "semantic"
                    similarity_score *= 100

            if similarity_score is None:
                similarity_score = self.calculate_fuzzy_similarity(titles)
                if similarity_score is not None:
                    method_used = "fuzzy"

            if similarity_score is None:
                similarity_score = self.calculate_string_similarity(titles)
                method_used = "difflib"

            if similarity_score is None:
                continue

            logger.debug(
                f"Posts by u/{author} have {method_used} similarity: "
                f"{similarity_score:.2f}"
            )

            threshold = (
                self.semantic_threshold * 100
                if method_used == "semantic"
                else self.fuzzy_threshold
            )

            if similarity_score >= threshold:
                duplicate_ids = [p["id"] for p in posts[1:]]
                actionable_posts.extend(duplicate_ids)
                logger.info(f"Flagged duplicates for removal: {duplicate_ids}")

        actionable_posts = list(set(actionable_posts))

        return actionable_posts if actionable_posts else None


# ─── Duplicate detector wrapper ───────────────────────────────────────────────


def duplicate_detector(
    list_posts: list[Submission],
    reddit_instance: Reddit,
    testing_mode: bool = False,
    semantic_threshold: float = 0.85,
    fuzzy_threshold: int = 85,
    numerical_threshold: int = 5,
    age_limit_hours: int = 24,
    use_semantic: bool = True,
) -> list[str] | None:
    """
    Wrapper function that detects and removes duplicate posts.

    Args:
        list_posts: List of Reddit PRAW submissions
        reddit_instance: PRAW Reddit instance for fetching posts
        testing_mode: If True, don't actually remove posts (default: False)
        semantic_threshold: Cosine similarity threshold (0-1) for semantic matching
        fuzzy_threshold: Fuzzy matching threshold (0-100)
        numerical_threshold: Threshold for numerical sequence detection
        age_limit_hours: Maximum age of posts to consider
        use_semantic: Whether to use semantic similarity

    Returns:
        List of post IDs that were removed, or None
    """
    detector = DuplicateDetector(
        semantic_threshold=semantic_threshold,
        fuzzy_threshold=fuzzy_threshold,
        numerical_threshold=numerical_threshold,
        age_limit_hours=age_limit_hours,
        use_semantic=use_semantic,
    )
    duplicate_ids = detector.detect_duplicates(list_posts)

    if not duplicate_ids:
        logger.debug("No duplicates detected.")
        return None

    logger.info(f"Found {len(duplicate_ids)} duplicate(s) to remove: {duplicate_ids}")

    successfully_removed = []

    for dupe_id in duplicate_ids:
        try:
            dupe_post = reddit_instance.submission(dupe_id)
            dupe_author = dupe_post.author.name

            original_post = None
            for post in list_posts:
                try:
                    if (
                        hasattr(post.author, "name")
                        and post.author.name == dupe_author
                        and post.id != dupe_id
                        and post.created_utc < dupe_post.created_utc
                    ):
                        original_post = post
                        break
                except AttributeError:
                    continue

            if not testing_mode:
                remove_content(
                    dupe_post,
                    reason="duplicate",
                    mod_note=f"Duplicate of {original_post.id if original_post else 'earlier post'}",
                )

            duplicate_comment: str = ""
            if original_post is not None and dupe_post is not None:
                duplicate_comment = RESPONSE.COMMENT_DUPLICATE.format(
                    author=dupe_author,
                    original_link=original_post.permalink,
                    dupe_link=dupe_post.permalink,
                )

            if not testing_mode:
                reddit_reply(dupe_post, duplicate_comment, True)

            successfully_removed.append(dupe_id)
            logger.info(f"Removed duplicate post `{dupe_id}` by u/{dupe_author}")

        except Exception as e:
            logger.error(f"Error processing duplicate `{dupe_id}`: {e}")
            continue

    action_counter(len(successfully_removed), "Removed duplicates")

    return successfully_removed if successfully_removed else None


# ─── Image hash search ────────────────────────────────────────────────────────


def search_image_hash(
    image_hash: str, max_distance: int = 5, days: int | None = None
) -> list[dict]:
    """
    Search the Ajo database for posts with matching or similar image hashes.

    Args:
        image_hash: The image hash to search for (hexadecimal string)
        max_distance: Maximum Hamming distance for similarity (default: 5).
                      0 = exact match only; 5 = allow up to 5 bit differences.
        days: Number of days to look back (default: None = search all time)

    Returns:
        List of dictionaries containing matching post information:
        [{'post_id': str, 'created_utc': int, 'author': str,
          'title': str, 'hash': str, 'distance': int}, ...]
        Sorted by distance (closest matches first)
    """
    from database import db

    if not image_hash:
        logger.warning("search_image_hash: Received empty hash")
        return []

    try:
        import imagehash

        target_hash = imagehash.hex_to_hash(image_hash)
    except Exception as e:
        logger.error(f"Failed to parse image hash '{image_hash}': {e}")
        return []

    cutoff_utc = None
    if days is not None:
        cutoff_utc = int(time.time()) - (days * 86400)
        logger.debug(
            f"Searching image hashes from last {days} days (cutoff: {cutoff_utc})"
        )

    try:
        if cutoff_utc is not None:
            query = """
                    SELECT id, created_utc, ajo
                    FROM ajo_database
                    WHERE ajo LIKE '%image_hash%'
                      AND created_utc >= ? \
                    """
            results = db.fetchall_ajo(query, (cutoff_utc,))
        else:
            query = "SELECT id, created_utc, ajo FROM ajo_database WHERE ajo LIKE '%image_hash%'"
            results = db.fetchall_ajo(query)

        matches = []

        for result in results:
            try:
                post_id = result["id"]
                created_utc = result["created_utc"]
                data_json = result["ajo"]

                if isinstance(data_json, str):
                    try:
                        data = orjson.loads(data_json)
                    except orjson.JSONDecodeError:
                        from ast import literal_eval

                        data = literal_eval(data_json)
                else:
                    data = data_json

                stored_hash = data.get("image_hash")
                if not stored_hash:
                    continue

                try:
                    stored_hash_obj = imagehash.hex_to_hash(stored_hash)
                    distance = target_hash - stored_hash_obj
                except Exception as e:
                    logger.debug(f"Error comparing hash for post {post_id}: {e}")
                    continue

                if distance <= max_distance:
                    matches.append(
                        {
                            "post_id": post_id,
                            "created_utc": created_utc,
                            "author": data.get("author", "unknown"),
                            "title": data.get("title", ""),
                            "hash": stored_hash,
                            "distance": distance,
                        }
                    )

            except Exception as e:
                logger.debug(f"Error processing result: {e}")
                continue

        matches.sort(key=lambda x: x["distance"])

        time_range = f"last {days} days" if days is not None else "all time"
        logger.info(
            f"Found {len(matches)} image hash matches "
            f"in {time_range} (max distance: {max_distance})"
        )
        return matches

    except Exception as e:
        logger.error(f"Error searching image hashes: {e}")
        return []


# ─── Image duplicate check ────────────────────────────────────────────────────


def check_image_duplicate(
    post: Submission,
    ajo: Ajo,
    days_lookback: int = 30,
    max_distance: int = 5,
    testing_mode: bool = False,
) -> dict | None:
    """
    Check if a post's image is a duplicate of a previously posted image.

    Should be called from ziwen_posts after an Ajo is created for an image
    post. Searches for similar images in the database and notifies the user
    if a match is found.

    Args:
        post: PRAW submission object (the current post being processed)
        ajo: Ajo object for the current post (must have image_hash set)
        days_lookback: How many days back to search (default: 30)
        max_distance: Maximum Hamming distance for similarity (default: 5).
                      0 = exact match only; 5 = allow up to 5 bit differences.
        testing_mode: If True, don't actually post comments (default: False)

    Returns:
        dict or None: Information about the duplicate if found, else None
        {
            'found': bool,
            'match': dict,  # Best matching post info
            'commented': bool  # Whether a comment was posted
        }
    """
    if not ajo.image_hash:
        logger.debug(f"Post `{post.id}` has no image hash, skipping")
        return None

    logger.info(f"Checking image hash for post `{post.id}` (hash: {ajo.image_hash})")

    try:
        matches = search_image_hash(
            image_hash=ajo.image_hash, max_distance=max_distance, days=days_lookback
        )

        matches = [m for m in matches if m["post_id"] != post.id]

        if not matches:
            logger.info(f"No similar images found for post `{post.id}`")
            return None

        best_match = matches[0]
        distance = best_match["distance"]

        logger.info(
            f"Found similar image for post `{post.id}`: "
            f"matches post `{best_match['post_id']}` with distance {distance}"
        )

        if distance == 0:
            similarity_text = "identical to"
        elif distance <= 2:
            similarity_text = "nearly identical to"
        else:
            similarity_text = "very similar to"

        try:
            post_author = post.author.name
        except AttributeError:
            post_author = "[deleted]"

        previous_post_link = f"https://www.reddit.com/comments/{best_match['post_id']}"

        time_diff_seconds = post.created_utc - best_match["created_utc"]
        time_diff_hours = time_diff_seconds / 3600
        time_diff_days = time_diff_seconds / 86400

        if time_diff_days >= 1:
            time_ago = f"{int(time_diff_days)} day(s) ago"
        else:
            time_ago = f"{int(time_diff_hours)} hour(s) ago"

        same_author = best_match["author"].lower() == post_author.lower()

        if same_author:
            comment_text = RESPONSE.COMMENT_IMAGE_DUPLICATE_SAME_AUTHOR.format(
                author=post_author,
                similarity=similarity_text,
                previous_link=previous_post_link,
                time_ago=time_ago,
            )
        else:
            comment_text = RESPONSE.COMMENT_IMAGE_DUPLICATE_DIFFERENT_AUTHOR.format(
                author=post_author,
                similarity=similarity_text,
                previous_link=previous_post_link,
                previous_author=best_match["author"],
                time_ago=time_ago,
            )

        comment_text += "\n\n" + RESPONSE.BOT_DISCLAIMER

        commented = False
        if not testing_mode:
            try:
                reddit_reply(post, comment_text, True)
                commented = True
                logger.info(f"Posted duplicate notification on `{post.id}`")
                action_counter(1, "Removed image duplicates")
            except Exception as e:
                logger.error(f"Failed to post comment on `{post.id}`: {e}")
        else:
            logger.info(f"[TESTING MODE] Would have posted comment:\n{comment_text}")
            commented = True

        return {
            "found": True,
            "match": best_match,
            "commented": commented,
            "distance": distance,
            "same_author": same_author,
        }

    except Exception as e:
        logger.error(f"Error checking image duplicate for `{post.id}`: {e}")
        return None


# ─── Image duplicate statistics ───────────────────────────────────────────────


def get_image_duplicate_stats(days: int = 7) -> dict | None:
    """
    Get statistics about image duplicates in the database.
    Useful for monitoring and tuning the duplicate detection parameters.

    Args:
        days: Number of days to analyze (default: 7)

    Returns:
        dict: Statistics about image duplicates
        {
            'total_image_posts': int,
            'unique_hashes': int,
            'duplicate_groups': list[dict],  # Groups of posts with identical hashes
            'time_range_days': int
        }
    """
    cutoff_utc = int(time.time()) - (days * 86400)

    try:
        query = """
                SELECT id, created_utc, ajo
                FROM ajo_database
                WHERE ajo LIKE '%image_hash%'
                  AND created_utc >= ? \
                """
        results = db.fetchall_ajo(query, (cutoff_utc,))

        hash_groups = defaultdict(list)
        total_posts = 0

        for result in results:
            try:
                data = orjson.loads(result["ajo"])
                image_hash = data.get("image_hash")

                if image_hash:
                    total_posts += 1
                    hash_groups[image_hash].append(
                        {
                            "post_id": result["id"],
                            "created_utc": result["created_utc"],
                            "author": data.get("author", "unknown"),
                            "title": data.get("title", ""),
                        }
                    )
            except Exception as e:
                logger.debug(f"Error processing result: {e}")
                continue

        duplicate_groups = [
            {
                "hash": hash_val,
                "count": len(posts),
                "posts": sorted(posts, key=lambda x: x["created_utc"]),
            }
            for hash_val, posts in hash_groups.items()
            if len(posts) > 1
        ]

        duplicate_groups.sort(key=lambda x: x["count"], reverse=True)

        stats = {
            "total_image_posts": total_posts,
            "unique_hashes": len(hash_groups),
            "duplicate_groups": duplicate_groups,
            "time_range_days": days,
        }

        logger.info(
            f"Found {total_posts} image posts with "
            f"{len(hash_groups)} unique hashes over {days} days. "
            f"{len(duplicate_groups)} groups with exact duplicates."
        )

        return stats

    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        return None
