#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Integration-style smoke test for the duplicate detector.
Fetches live posts from r/translator and runs the detector in testing_mode
so no posts are actually removed.

Run with:
    python -m pytest testing/unit/test_dupe_detector.py -s
or directly:
    python testing/unit/test_dupe_detector.py
"""

from config import SETTINGS
from monitoring.dupe_detector import duplicate_detector
from reddit.connection import REDDIT


def test_duplicate_detection() -> None:
    """
    Test the duplicate detector on r/translator posts.
    Fetches the 100 most recent posts and runs the detector in testing_mode.
    Asserts that the detector returns either None or a list of post ID strings.
    """
    # Fetch posts from r/translator
    designated_subreddit = SETTINGS["subreddit"]
    subreddit = REDDIT.subreddit(designated_subreddit)

    print("=" * 80)
    print("DUPLICATE DETECTOR TEST - r/translator")
    print("=" * 80)
    print()

    print(f"Fetching posts from r/{designated_subreddit}...")
    posts = list(subreddit.new(limit=100))  # Get last 100 posts
    posts.reverse()  # Reverse order to process oldest posts first
    print(f"Fetched {len(posts)} posts\n")

    # Show some basic stats
    authors: dict[str, list[str]] = {}
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

    # Run the duplicate detector in testing_mode (no posts removed)
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

    # Assert return type is valid
    assert duplicate_ids is None or isinstance(duplicate_ids, list), (
        f"Expected list[str] or None, got {type(duplicate_ids)}"
    )
    if duplicate_ids is not None:
        assert all(isinstance(pid, str) for pid in duplicate_ids), (
            "All duplicate IDs should be strings"
        )

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
    test_duplicate_detection()
