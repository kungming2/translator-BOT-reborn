#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Interfaces with processes.ziwen_posts to help assess posts which might
be duplicates from the same user.
"""

import hashlib
import logging
import re
import time
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations

import numpy as np
import orjson

# For fuzzy matching (backup)
from rapidfuzz import fuzz

# For semantic similarity
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from config import SETTINGS, logger
from connection import REDDIT, is_mod, search_removal_reasons
from database import db
from reddit_sender import reddit_reply
from responses import RESPONSE
from usage_statistics import action_counter


class DuplicateDetector:
    """Enhanced duplicate detection system for Reddit posts."""

    def __init__(
        self,
        semantic_threshold=0.85,
        fuzzy_threshold=85,
        numerical_threshold=5,
        age_limit_hours=24,
        use_semantic=True,
    ):
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

        # Initialize semantic model if available and requested
        self.model = None
        if use_semantic:
            try:
                # Use a lightweight but effective model
                logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
                logging.getLogger("tqdm").setLevel(logging.WARNING)
                self.model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.debug(
                    "[ZW] Duplicate Detector: Semantic similarity model loaded successfully"
                )
            except Exception as e:
                logger.warning(
                    f"[ZW] Duplicate Detector: Failed to load semantic model: {e}"
                )
                self.model = None

    @staticmethod
    def normalize_text(text):
        """
        Normalize text for better comparison.

        Args:
            text: Input string

        Returns:
            Normalized string
        """
        # Convert to lowercase
        text = text.lower()

        # Remove excessive punctuation and whitespace
        text = re.sub(r"[!?]{2,}", "!", text)
        text = re.sub(r"\s+", " ", text)

        # Remove common Reddit formatting
        text = re.sub(r"\[.*?]\(.*?\)", "", text)  # Remove Markdown links
        text = re.sub(r"https?://\S+", "", text)  # Remove URLs

        return text.strip()

    @staticmethod
    def extract_numbers(text):
        """
        Extract numbers from text with better context awareness.

        Args:
            text: Input string

        Returns:
            List of integers found in the text
        """
        # Match numbers with various contexts: #1, episode 5, part 3, pt 2, etc.
        patterns = [
            r"#(\d+)",  # Explicit pattern for #1, #2, etc.
            r"(?:episode|ep|part|pt|chapter|ch|letter)\s*(\d+)",  # Contextual numbers
            r"\((?:pt|part)\s*(\d+)\)",  # Numbers in parentheses: (pt 1), (part 2)
            r"(?<=[\s\.\(\[\-])\d+(?=[\s\.\)\]\-]|$)",  # Standalone numbers
        ]

        numbers = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            numbers.extend([int(m) for m in matches])

        logger.debug(
            f"[ZW] Duplicate Detector: Extracted numbers from '{text}': {numbers}"
        )
        return numbers

    def is_numerical_sequence(self, titles):
        """
        Improved detection of numerical sequences in titles.

        Args:
            titles: List of title strings

        Returns:
            Boolean indicating if titles appear to be a sequence
        """
        if len(titles) < 2:
            return False

        # Extract numbers from each title
        number_sets = []
        for title in titles:
            nums = self.extract_numbers(title)
            if nums:
                number_sets.append(nums)

        # If less than 2 titles have numbers, can't determine sequence
        if len(number_sets) < 2:
            return False

        logger.debug(f"[ZW] Duplicate Detector: Numbers found in titles: {number_sets}")

        # Check if numbers are incrementing consistently
        # Compare the last number in each set (usually the episode/part number)
        last_numbers = [nums[-1] for nums in number_sets]

        # Check for consistent incrementation
        differences = [b - a for a, b in zip(last_numbers, last_numbers[1:])]

        if not differences:
            return False

        avg_diff = sum(differences) / len(differences)
        logger.debug(
            f"[ZW] Duplicate Detector: Average numerical difference: {avg_diff}"
        )

        # If numbers are incrementing consistently (difference of 1-3), it's likely a series
        if 0 < avg_diff <= 3:
            return True

        # If all differences are identical and non-zero, also likely a series
        if len(set(differences)) == 1 and differences[0] != 0:
            return True

        return False

    def calculate_semantic_similarity(self, titles):
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
            # Generate embeddings
            embeddings = self.model.encode(titles)

            # Calculate pairwise cosine similarities
            similarities = []
            for i, j in combinations(range(len(titles)), 2):
                sim = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
                similarities.append(sim)

            return np.mean(similarities)
        except Exception as e:
            logger.error(
                f"[ZW] Duplicate Detector: Error calculating semantic similarity: {e}"
            )
            return None

    @staticmethod
    def calculate_fuzzy_similarity(titles):
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
            # Use token_sort_ratio for better handling of word order
            sim = fuzz.token_sort_ratio(titles[i], titles[j])
            similarities.append(sim)

        return sum(similarities) / len(similarities)

    @staticmethod
    def calculate_string_similarity(titles):
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
            # SequenceMatcher from standard library
            ratio = SequenceMatcher(None, titles[i], titles[j]).ratio()
            similarities.append(ratio * 100)

        return sum(similarities) / len(similarities)

    def create_title_hash(self, title):
        """
        Create a hash of the title for exact duplicate detection.

        Args:
            title: Title string

        Returns:
            SHA256 hash of normalized title
        """
        normalized = self.normalize_text(title)
        # Remove all numbers and punctuation for hash
        cleaned = re.sub(r"[^a-z\s]", "", normalized)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return hashlib.sha256(cleaned.encode()).hexdigest()

    def detect_duplicates(
        self,
        list_posts,
    ):
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

        # FIRST: Collect all posts by author
        for post in list_posts:
            try:
                post_author = post.author.name.lower()
            except AttributeError:
                continue

            # Check post age
            time_delta = (current_time - post.created_utc) / 3600
            if time_delta > self.age_limit_hours:
                continue

            # Skip approved posts
            if post.approved:
                logger.debug(
                    f"[ZW] Duplicate Detector: Post `{post.id}` already approved by moderator"
                )
                continue

            # Skip moderator posts
            if is_mod(post_author):
                logger.debug(
                    f"[ZW] Duplicate Detector: Post `{post.id}` posted by moderator"
                )
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

        # THEN: Process posts by the same author (FIXED INDENTATION)
        for author, posts in author_posts.items():
            if len(posts) < 2:
                continue

            # Sort by creation time
            posts.sort(key=lambda x: x["created_utc"])
            titles = [p["title"] for p in posts]

            logger.debug(
                f"[ZW] Duplicate Detector: Analyzing {len(posts)} posts by u/{author}"
            )

            # Check if titles are part of a numbered sequence
            if self.is_numerical_sequence(titles):
                logger.info(
                    f"[ZW] Duplicate Detector: Posts by u/{author} appear to be a series. Skipping."
                )
                continue

            # Calculate similarity using the best available method
            similarity_score = None
            method_used = None

            # Try semantic similarity first (most accurate)
            if self.model:
                similarity_score = self.calculate_semantic_similarity(titles)
                if similarity_score is not None:
                    method_used = "semantic"
                    # Convert to 0-100 scale for consistent threshold comparison
                    similarity_score *= 100

            # Fallback to fuzzy matching
            if similarity_score is None:
                similarity_score = self.calculate_fuzzy_similarity(titles)
                if similarity_score is not None:
                    method_used = "fuzzy"

            # Final fallback to difflib
            if similarity_score is None:
                similarity_score = self.calculate_string_similarity(titles)
                method_used = "difflib"

            if similarity_score is None:
                continue

            logger.debug(
                f"[ZW] Duplicate Detector: Posts by u/{author} have {method_used} similarity: "
                f"{similarity_score:.2f}"
            )

            # Determine threshold based on method
            threshold = (
                self.semantic_threshold * 100
                if method_used == "semantic"
                else self.fuzzy_threshold
            )

            # Flag duplicates if above threshold
            if similarity_score >= threshold:
                # Keep the oldest post, remove the rest
                duplicate_ids = [p["id"] for p in posts[1:]]
                actionable_posts.extend(duplicate_ids)
                logger.info(
                    f"[ZW] Duplicate Detector: Flagged duplicates for removal: {duplicate_ids}"
                )

        # Remove any duplicates from actionable_posts and return
        actionable_posts = list(set(actionable_posts))

        return actionable_posts if actionable_posts else None


def duplicate_detector(list_posts, reddit_instance, testing_mode=False, **kwargs):
    """
    Wrapper function that detects and removes duplicate posts.

    Args:
        list_posts: List of Reddit PRAW submissions
        reddit_instance: PRAW Reddit instance for fetching posts
        testing_mode: If True, don't actually remove posts (default: False)
        **kwargs: Additional arguments for DuplicateDetector

    Returns:
        List of post IDs that were removed, or None
    """
    # Detect duplicates
    detector = DuplicateDetector(**kwargs)
    duplicate_ids = detector.detect_duplicates(list_posts)

    if not duplicate_ids:
        logger.debug("[ZW] Duplicate Detector: No duplicates detected.")
        return None

    logger.info(
        f"[ZW] Duplicate Detector: Found {len(duplicate_ids)} duplicate(s) to remove: {duplicate_ids}"
    )

    # Remove duplicates and notify authors
    successfully_removed = []

    for dupe_id in duplicate_ids:
        try:
            dupe_post = reddit_instance.submission(dupe_id)
            dupe_author = dupe_post.author.name

            # Find the original post (oldest post by the same author)
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

            # Remove the duplicate post
            if not testing_mode:
                # Try to use removal reasons if available
                removal_kwargs = {
                    "reason_id": search_removal_reasons("duplicate"),
                    "mod_note": f"Duplicate of {original_post.id if original_post else 'earlier post'}",
                }
                dupe_post.mod.remove(**removal_kwargs)

            # Reply to the author
            duplicate_comment = RESPONSE.COMMENT_DUPLICATE.format(
                author=dupe_author,
                original_link=original_post.permalink,
                dupe_link=dupe_post.permalink,
            )

            if not testing_mode:
                reddit_reply(dupe_post, duplicate_comment, True)

            successfully_removed.append(dupe_id)
            logger.info(
                f"[ZW] Duplicate Detector: Removed duplicate post {dupe_id} by u/{dupe_author}"
            )

        except Exception as e:
            logger.error(
                f"[ZW] Duplicate Detector: Error processing duplicate {dupe_id}: {e}"
            )
            continue

    # Log to action counter
    action_counter(len(successfully_removed), "Removed duplicates")

    return successfully_removed if successfully_removed else None


def search_image_hash(
    image_hash: str, max_distance: int = 5, days: int | None = None
) -> list[dict]:
    """
    Search the Ajo database for posts with matching or similar image hashes.

    Args:
        image_hash: The image hash to search for (hexadecimal string)
        max_distance: Maximum Hamming distance for similarity (default: 5)
                     0 = exact match only
                     5 = allow up to 5 bit differences (similar images)
        days: Number of days to look back (default: None = search all time)

    Returns:
        List of dictionaries containing matching post information:
        [{'post_id': str, 'created_utc': int, 'author': str,
          'title': str, 'hash': str, 'distance': int}, ...]
        Sorted by distance (closest matches first)
    """
    from database import db

    if not image_hash:
        logger.warning(
            "[ZW] Duplicate Detector: search_image_hash: Received empty hash"
        )
        return []

    try:
        # Import here to avoid issues if imagehash isn't available
        import imagehash

        target_hash = imagehash.hex_to_hash(image_hash)
    except Exception as e:
        logger.error(
            f"[ZW] Duplicate Detector: Failed to parse image hash '{image_hash}': {e}"
        )
        return []

    # Calculate cutoff time if days parameter is provided
    cutoff_utc = None
    if days is not None:
        cutoff_utc = int(time.time()) - (days * 86400)
        logger.debug(
            f"[ZW] Duplicate Detector: Searching image hashes from last {days} days (cutoff: {cutoff_utc})"
        )

    try:
        # Build query with optional time filter
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

                # Parse the ajo data
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

                # Calculate Hamming distance
                try:
                    stored_hash_obj = imagehash.hex_to_hash(stored_hash)
                    distance = target_hash - stored_hash_obj
                except Exception as e:
                    logger.debug(
                        f"[ZW] Duplicate Detector: Error comparing hash for post {post_id}: {e}"
                    )
                    continue

                # Only include if within distance threshold
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
                logger.debug(f"[ZW] Duplicate Detector: Error processing result: {e}")
                continue

        # Sort by distance (closest matches first)
        matches.sort(key=lambda x: x["distance"])

        time_range = f"last {days} days" if days is not None else "all time"
        logger.info(
            f"[ZW] Duplicate Detector: Found {len(matches)} image hash matches "
            f"in {time_range} (max distance: {max_distance})"
        )
        return matches

    except Exception as e:
        logger.error(f"[ZW] Duplicate Detector: Error searching image hashes: {e}")
        return []


def check_image_duplicate(
    post, ajo, days_lookback=30, max_distance=5, testing_mode=False
):
    """
    Check if a post's image is a duplicate of a previously posted image.

    This function should be called from ziwen_posts after an Ajo is created
    for an image post. It searches for similar images in the database and
    notifies the user if a match is found.

    Args:
        post: PRAW submission object (the current post being processed)
        ajo: Ajo object for the current post (must have image_hash set)
        days_lookback: How many days back to search (default: 30)
        max_distance: Maximum Hamming distance for similarity (default: 5)
                     0 = exact match only
                     5 = allow up to 5 bit differences (similar images)
        testing_mode: If True, don't actually post comments (default: False)

    Returns:
        dict or None: Information about the duplicate if found, else None
        {
            'found': bool,
            'match': dict,  # Best matching post info
            'commented': bool  # Whether a comment was posted
        }
    """
    # Skip if no image hash (not an image post)
    if not ajo.image_hash:
        logger.debug(
            f"[ZW] Image Dupe Check: Post `{post.id}` has no image hash, skipping"
        )
        return None

    logger.info(
        f"[ZW] Image Dupe Check: Checking image hash for post `{post.id}` "
        f"(hash: {ajo.image_hash})"
    )

    try:
        # Search for similar images in the database
        matches = search_image_hash(
            image_hash=ajo.image_hash, max_distance=max_distance, days=days_lookback
        )

        # Filter out the current post itself
        matches = [m for m in matches if m["post_id"] != post.id]

        if not matches:
            logger.info(
                f"[ZW] Image Dupe Check: No similar images found for post `{post.id}`"
            )
            return None

        # Get the best match (closest distance)
        best_match = matches[0]
        distance = best_match["distance"]

        logger.info(
            f"[ZW] Image Dupe Check: Found similar image for post `{post.id}`: "
            f"matches post `{best_match['post_id']}` with distance {distance}"
        )

        # Determine similarity level for user message
        if distance == 0:
            similarity_text = "identical to"
        elif distance <= 2:
            similarity_text = "nearly identical to"
        else:
            similarity_text = "very similar to"

        # Format the notification comment
        try:
            post_author = post.author.name
        except AttributeError:
            post_author = "[deleted]"

        # Build the comment with information about the similar post
        previous_post_link = f"https://www.reddit.com/comments/{best_match['post_id']}"

        # Calculate time difference
        time_diff_seconds = post.created_utc - best_match["created_utc"]
        time_diff_hours = time_diff_seconds / 3600
        time_diff_days = time_diff_seconds / 86400

        if time_diff_days >= 1:
            time_ago = f"{int(time_diff_days)} day(s) ago"
        else:
            time_ago = f"{int(time_diff_hours)} hour(s) ago"

        # Check if it's by the same author
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

        # Add disclaimer
        comment_text += "\n\n" + RESPONSE.BOT_DISCLAIMER

        # Post the comment
        commented = False
        if not testing_mode:
            try:
                reddit_reply(post, comment_text, True)
                commented = True
                logger.info(
                    f"[ZW] Image Dupe Check: Posted duplicate notification on `{post.id}`"
                )

                # Log to action counter
                action_counter(1, "Removed image duplicates")

            except Exception as e:
                logger.error(
                    f"[ZW] Image Dupe Check: Failed to post comment on `{post.id}`: {e}"
                )
        else:
            logger.info(
                f"[ZW] Image Dupe Check: [TESTING MODE] Would have posted comment:\n{comment_text}"
            )
            commented = True  # In testing mode, we "posted"

        return {
            "found": True,
            "match": best_match,
            "commented": commented,
            "distance": distance,
            "same_author": same_author,
        }

    except Exception as e:
        logger.error(
            f"[ZW] Image Dupe Check: Error checking image duplicate for `{post.id}`: {e}"
        )
        return None


def get_image_duplicate_stats(days=7):
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
                logger.debug(f"[ZW] Image Stats: Error processing result: {e}")
                continue

        # Find duplicate groups (same hash, multiple posts)
        duplicate_groups = [
            {
                "hash": hash_val,
                "count": len(posts),
                "posts": sorted(posts, key=lambda x: x["created_utc"]),
            }
            for hash_val, posts in hash_groups.items()
            if len(posts) > 1
        ]

        # Sort by count (most duplicates first)
        duplicate_groups.sort(key=lambda x: x["count"], reverse=True)

        stats = {
            "total_image_posts": total_posts,
            "unique_hashes": len(hash_groups),
            "duplicate_groups": duplicate_groups,
            "time_range_days": days,
        }

        logger.info(
            f"[ZW] Image Stats: Found {total_posts} image posts with "
            f"{len(hash_groups)} unique hashes over {days} days. "
            f"{len(duplicate_groups)} groups with exact duplicates."
        )

        return stats

    except Exception as e:
        logger.error(f"[ZW] Image Stats: Error getting statistics: {e}")
        return None


"""TESTING ROUTINE"""


def duplicate_detection_test():
    """
    Test the duplicate detector on r/translator posts.
    """
    print("=" * 80)
    print("DUPLICATE DETECTOR TEST - r/translator")
    print("=" * 80)
    print()

    # Fetch posts from r/translator
    designated_subreddit = SETTINGS["subreddit"]
    subreddit = REDDIT.subreddit(designated_subreddit)

    # Get the most recent posts (adjust limit as needed)
    print(f"Fetching posts from r/{designated_subreddit}...")
    posts = list(subreddit.new(limit=100))  # Get last 100 posts
    posts.reverse()  # Reverse order to process oldest posts first
    print(f"Fetched {len(posts)} posts\n")

    # Show some basic stats
    authors = {}
    for post in posts:
        try:
            author = post.author.name
            if author not in authors:
                authors[author] = []
            authors[author].append(post.title[:60])  # First 60 chars
        except AttributeError:
            continue

    print(f"Posts from {len(authors)} unique authors")
    multiple_posts = {k: v for k, v in authors.items() if len(v) > 1}
    print(f"Authors with multiple posts: {len(multiple_posts)}\n")

    if multiple_posts:
        print("Authors with multiple posts:")
        for author, titles in sorted(
            multiple_posts.items(), key=lambda x: len(x[1]), reverse=True
        ):
            print(f"  u/{author}: {len(titles)} posts")
            for i, title in enumerate(titles, 1):
                print(f"    {i}. {title}...")
        print()

    # Run the duplicate detector
    print("Running duplicate detector...")
    print("-" * 80)

    duplicate_ids = duplicate_detector(
        posts,
        REDDIT,
        testing_mode=True,
        semantic_threshold=0.85,
        fuzzy_threshold=85,
        age_limit_hours=48,  # Look at last 48 hours as a maximum
    )

    print("-" * 80)
    print()

    # Display results
    if duplicate_ids:
        print(f"🚨 FOUND {len(duplicate_ids)} DUPLICATE(S) TO REMOVE:")
        print("=" * 80)

        for i, post_id in enumerate(duplicate_ids, 1):
            post = REDDIT.submission(post_id)
            try:
                author = post.author.name
            except AttributeError:
                author = "[deleted]"

            print(f"\n{i}. Post ID: {post_id}")
            print(f"   Author: u/{author}")
            print(f"   Title: {post.title}")
            print(f"   URL: https://reddit.com{post.permalink}")
            print(f"   Created: {post.created_utc}")

            # Try to find what it's a duplicate of (the original kept post)
            # by looking for other posts by the same author
            author_posts = [
                p
                for p in posts
                if hasattr(p.author, "name")
                and p.author.name == author
                and p.id != post_id
            ]
            if author_posts:
                print("   Likely duplicate of:")
                for orig in author_posts[:3]:  # Show up to 3 originals
                    print(f"     - {orig.title[:60]}... ({orig.id})")

        print("\n" + "=" * 80)
        print(f"SUMMARY: Would remove {len(duplicate_ids)} post(s)")
        print("=" * 80)
    else:
        print("✅ No duplicates detected!")
        print("All posts appear to be unique.")

    print()


if __name__ == "__main__":
    start_time = time.time()
    duplicate_detection_test()
    end_time = time.time()
    elapsed = end_time - start_time
    print(f"\nTotal execution time: {elapsed:.2f} seconds")
