#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Defines the Titolo class, the core data model representing a parsed
r/translator post title.

A Titolo is produced by title.title_handling.process_title and carries all
results of the parsing pipeline: source and target Lingvo objects, flair
metadata, direction, notification languages, and the various forms of the
title string. Consumers should treat a Titolo as read-only after
process_title returns.

This class is intentionally free of parsing logic and has no imports from
the title package, making it safe to import anywhere without pulling in the
full pipeline.

Logger tag: [M:TITOLO]
"""


class Titolo:
    """
    Data container for a parsed r/translator post title.

    All fields are populated by title.title_handling.process_title.
    """

    def __init__(self):
        self.source = []  # List of source Lingvo objects
        self.target = []  # List of target Lingvo objects
        self.final_code = None  # CSS flair code
        self.final_text = None  # CSS flair display text
        self.title_original = None  # Original title as-is
        self.title_actual = None  # Original title minus language tag
        self.title_processed = None  # Preprocessed title
        self.notify_languages = []  # Languages to notify subscribers for
        self.language_country = None  # Optional country specification
        self.direction = (
            None  # 'english_from' | 'english_to' | 'english_both' | 'english_none'
        )
        self.ai_assessed = False  # True if the AI fallback was used

    def __repr__(self):
        return f"<Titolo: ({self.source} > {self.target}) | {self.title_original}>"

    def __str__(self):
        return (
            f"Titolo(\n"
            f"  source={self.source},\n"
            f"  target={self.target},\n"
            f"  final_code='{self.final_code}',\n"
            f"  final_text='{self.final_text}',\n"
            f"  title_original='{self.title_original}',\n"
            f"  title_actual='{self.title_actual}',\n"
            f"  title_processed='{self.title_processed}',\n"
            f"  notify_languages={self.notify_languages},\n"
            f"  language_country='{self.language_country}',\n"
            f"  direction='{self.direction}',\n"
            f"  ai_assessed={self.ai_assessed}\n)"
        )

    def add_final_code(self, code):
        """Set the CSS flair code."""
        self.final_code = code

    def add_final_text(self, text):
        """Set the CSS flair display text."""
        self.final_text = text
