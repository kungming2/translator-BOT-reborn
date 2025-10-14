#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Interfaces with processes.ziwen_posts to help assess posts which might
be duplicates from the same user.
"""
import hashlib
import re
import time
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations

# For semantic similarity
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
# For fuzzy matching (backup)
from rapidfuzz import fuzz

from config import logger
from connection import is_mod, REDDIT, search_removal_reasons
from reddit_sender import message_reply
from responses import RESPONSE
from statistics import action_counter


class DuplicateDetector:
    """Enhanced duplicate detection system for Reddit posts."""

    def __init__(self,
                 semantic_threshold=0.85,
                 fuzzy_threshold=85,
                 numerical_threshold=5,
                 age_limit_hours=24,
                 use_semantic=True):
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
                self.model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("[DD] Semantic similarity model loaded successfully")
            except Exception as e:
                logger.warning(f"[DD] Failed to load semantic model: {e}")
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
        text = re.sub(r'[!?]{2,}', '!', text)
        text = re.sub(r'\s+', ' ', text)

        # Remove common Reddit formatting
        text = re.sub(r'\[.*?]\(.*?\)', '', text)  # Remove Markdown links
        text = re.sub(r'https?://\S+', '', text)  # Remove URLs

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
            r'(?:episode|ep|part|pt|chapter|ch|#|letter)\s*(\d+)',  # Contextual numbers
            r'\((?:pt|part)\s*(\d+)\)',  # Numbers in parentheses: (pt 1), (part 2)
            r'(?<=[\s\.\(\[\-])\d+(?=[\s\.\)\]\-]|$)',  # Standalone numbers
        ]

        numbers = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            numbers.extend([int(m) for m in matches])

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

        logger.info(f"[DD] Numbers found in titles: {number_sets}")

        # Check if numbers are incrementing consistently
        # Compare the last number in each set (usually the episode/part number)
        last_numbers = [nums[-1] for nums in number_sets]

        # Check for consistent incrementation
        differences = [b - a for a, b in zip(last_numbers, last_numbers[1:])]

        if not differences:
            return False

        avg_diff = sum(differences) / len(differences)
        logger.info(f"[DD] Average numerical difference: {avg_diff}")

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
            logger.error(f"[DD] Error calculating semantic similarity: {e}")
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
        cleaned = re.sub(r'[^a-z\s]', '', normalized)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return hashlib.sha256(cleaned.encode()).hexdigest()

    def detect_duplicates(self, list_posts, ):
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

        # Group posts by author
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
                logger.info(f"[DD] Post `{post.id}` already approved by moderator")
                continue

            # Skip moderator posts
            if is_mod(post_author):
                logger.info(f"[DD] Post `{post.id}` posted by moderator")
                continue

            normalized_title = self.normalize_text(post.title)
            author_posts[post_author].append({
                'id': post.id,
                'title': normalized_title,
                'created_utc': post.created_utc,
                'original_title': post.title
            })

            # Process posts by the same author
            for author, posts in author_posts.items():
                if len(posts) < 2:
                    continue

                # Sort by creation time
                posts.sort(key=lambda x: x['created_utc'])
                titles = [p['title'] for p in posts]

                logger.info(f"[DD] Analyzing {len(posts)} posts by u/{author}")

                # Check if titles are part of a numbered sequence
                if self.is_numerical_sequence(titles):
                    logger.info(f"[DD] Posts by u/{author} appear to be a series. Skipping.")
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

                logger.info(
                    f"[DD] Posts by u/{author} have {method_used} similarity: "
                    f"{similarity_score:.2f}"
                )

                # Determine threshold based on method
                threshold = self.semantic_threshold * 100 if method_used == "semantic" else self.fuzzy_threshold

                # Flag duplicates if above threshold
                if similarity_score >= threshold:
                    # Keep the oldest post, remove the rest
                    duplicate_ids = [p['id'] for p in posts[1:]]
                    actionable_posts.extend(duplicate_ids)
                    logger.info(f"[DD] Flagged duplicates for removal: {duplicate_ids}")

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
        logger.info("[DD] No duplicates detected.")
        return None

    logger.info(f"[DD] Found {len(duplicate_ids)} duplicate(s) to remove: {duplicate_ids}")

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
                    if (hasattr(post.author, 'name') and
                            post.author.name == dupe_author and
                            post.id != dupe_id and
                            post.created_utc < dupe_post.created_utc):
                        original_post = post
                        break
                except AttributeError:
                    continue

            # Remove the duplicate post
            if not testing_mode:
                # Try to use removal reasons if available
                removal_kwargs = {'reason_id': search_removal_reasons("duplicate"),
                                  'mod_note': f"Duplicate of {original_post.id if original_post else 'earlier post'}"}
                dupe_post.mod.remove(**removal_kwargs)

            # Reply to the author
            duplicate_comment = RESPONSE.COMMENT_DUPLICATE.format(
                author=dupe_author,
                original_link=original_post.permalink,
                dupe_link=dupe_post.permalink,
            )
            bot_reply = message_reply(dupe_post, duplicate_comment)
            if not testing_mode:
                bot_reply.mod.distinguish()

            successfully_removed.append(dupe_id)
            logger.info(f"[DD] Removed duplicate post {dupe_id} by u/{dupe_author}")

        except Exception as e:
            logger.error(f"[DD] Error processing duplicate {dupe_id}: {e}")
            continue

    # Log to action counter
    action_counter(len(successfully_removed), "Removed duplicates")

    return successfully_removed if successfully_removed else None


def test_duplicate_detection():
    """
    Test the duplicate detector on r/translator posts.
    """
    print("=" * 80)
    print("DUPLICATE DETECTOR TEST - r/translator")
    print("=" * 80)
    print()

    # Fetch posts from r/translator
    subreddit = REDDIT.subreddit('translator')

    # Get the most recent posts (adjust limit as needed)
    print("Fetching posts from r/translator...")
    posts = list(subreddit.new(limit=100))  # Get last 100 posts
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
        for author, titles in sorted(multiple_posts.items(), key=lambda x: len(x[1]), reverse=True):
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
        image_hash_detector=None,  # No image hash detection for this test
        semantic_threshold=0.85,
        fuzzy_threshold=85,
        age_limit_hours=48  # Look at last 48 hours
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
            author_posts = [p for p in posts if hasattr(p.author, 'name') and
                            p.author.name == author and p.id != post_id]
            if author_posts:
                print(f"   Likely duplicate of:")
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
    test_duplicate_detection()
