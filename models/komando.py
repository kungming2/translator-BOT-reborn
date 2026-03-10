#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Defines the Komando command structure and class,
along with related functions. This represents a command called within a
comment, along with the data associated with that comment call.
...

Logger tag: [M:KOMANDO]
"""

import logging
import re
from collections import defaultdict

from config import SETTINGS
from config import logger as _base_logger
from languages import converter
from utility import extract_text_within_curly_braces

logger = logging.LoggerAdapter(_base_logger, {"tag": "M:KOMANDO"})


class Komando:
    def __init__(
        self, name, data=None, specific_mode=False, disable_tokenization=False
    ):
        self.name = name  # e.g., "identify", "translated"
        # For data, ["es"], ["la", "grc"] as Lingvos or None
        # lookup_cjk gets tuples: ('lang', 'term', explicit_bool)
        self.data = data
        self.specific_mode = specific_mode
        self.disable_tokenization = disable_tokenization

    def __repr__(self):
        return (
            f"Komando(name={self.name!r}, data={self.data!r}, "
            f"specific_mode={self.specific_mode!r}, "
            f"disable_tokenization={self.disable_tokenization!r})"
        )

    def to_dict(self):
        return {
            "name": self.name,
            "data": self.data,
            "specific_mode": self.specific_mode,
            "disable_tokenization": self.disable_tokenization,
        }

    def remap_language(self, target_lang_code):
        """
        Remap all language codes in self.data to a target language code.
        Only works for 'lookup_cjk' komandos.

        :param target_lang_code: Target language code (e.g., 'ja', 'ko')
        :return: New Komando object with remapped language codes
        :raises ValueError: If self.name is not 'lookup_cjk'
        """
        if self.name != "lookup_cjk":
            raise ValueError(
                f"remap_language only works with 'lookup_cjk' komandos, got '{self.name}'"
            )

        if not self.data:
            return Komando(
                name=self.name,
                data=self.data,
                specific_mode=self.specific_mode,
                disable_tokenization=self.disable_tokenization,
            )

        logger.info(f"Remapping {len(self.data)} entries to '{target_lang_code}'.")

        # Handle both old format (lang, term) and new format (lang, term, explicit)
        remapped_data = []
        for entry in self.data:
            if len(entry) == 3:
                # New format: (lang, term, explicit)
                _, term, explicit = entry
                remapped_data.append((target_lang_code, term, explicit))
            elif len(entry) == 2:
                # Old format: (lang, term)
                _, term = entry
                remapped_data.append((target_lang_code, term))
            else:
                remapped_data.append(entry)

        return Komando(
            name=self.name,
            data=remapped_data,
            specific_mode=self.specific_mode,
            disable_tokenization=self.disable_tokenization,
        )


def _check_specific_mode(arg_str):
    """
    Check if argument ends with ! and has 2-4 chars before it.
    Returns (cleaned_arg, specific_mode_flag).
    """
    # Strip common trailing punctuation first (except !)
    arg_str = arg_str.rstrip(".,;:?()[]{}")

    if arg_str.endswith("!"):
        content = arg_str[:-1]  # Remove trailing !
        if 2 <= len(content) <= 4:
            return content, True
        else:
            # Fail gracefully: return None to indicate invalid
            return None, False
    return arg_str, False


def _deduplicate_args(args):
    """
    Deduplicate arguments while preserving order.

    Handles four types of arguments:
    1. Lingvo objects - dedupe by language code
    2. 3-tuples (for lookup_cjk) - dedupe by (lang, term, explicit) tuples
    3. 2-tuples (for lookup_cjk legacy) - dedupe by (lang, term) tuples
    4. Strings - dedupe by value

    :param args: List of arguments to deduplicate
    :return: Deduplicated list maintaining original order
    """
    if not args:
        return args

    seen = set()
    result = []

    for arg in args:
        # Handle Lingvo objects
        if hasattr(arg, "language_name"):
            key = arg.language_name
            if key not in seen:
                seen.add(key)
                result.append(arg)
        # Handle tuples (lookup_cjk format: (lang, term) or (lang, term, explicit))
        elif isinstance(arg, tuple):
            if arg not in seen:  # Tuples are hashable - can use directly
                seen.add(arg)
                result.append(arg)
        # Handle strings
        else:
            if arg not in seen:
                seen.add(arg)
                result.append(arg)

    return result


def extract_commands_from_text(text, parent_languages=None):
    """
    Extract Komando commands from text.

    Parses text for command patterns including:
    - Commands with required arguments: !command:"arg" or !command:arg1,arg2
    - Commands with optional arguments: !command or !command:"arg" or !command:arg
    - Commands with no arguments: !command
    - CJK lookups using backticks: `term`, `term`:lang
    - Wikipedia lookups using double braces: {{term}}

    Supports specific_mode via trailing exclamation: !command:la! activates specific_mode
    for strict code lookups (2-4 character codes only).

    For lookup_cjk commands, supports disable_tokenization via trailing exclamation:
    `term`! or `term`:lang! disables tokenization for that lookup.

    Arguments are converted to Lingvo objects via the converter() function unless
    the command is in the skip-conversion list.

    :param text: The input text to parse for commands.
    :param parent_languages: Optional list of Lingvo objects representing the language(s)
        of the post this comment belongs to. The first Lingvo's preferred_code is used as
        a fallback language for CJK backtick lookups when no language can be inferred from
        the comment text itself (e.g. kanji-only terms with no kana). Ignored if the code
        is ambiguous (e.g. 'multiple', 'generic', 'unknown') or not a 2-3 character ISO code.
    :return: A list of Komando objects with extracted commands and their arguments.
    """
    commands_dict = defaultdict(list)
    specific_mode_dict = defaultdict(bool)
    disable_tokenization_dict = defaultdict(bool)
    original_text = text.strip()

    # Normalize curly quotes in both cases
    text = original_text.replace(""", '"').replace(""", '"')
    text = text.replace("'", "'").replace("'", "'")

    # Remove backslash escapes before backticks (from Reddit's rich text formatter)
    text = text.replace("\\`", "`")

    text_lower = text.lower()  # For case-insensitive command detection

    # Replace !id with synonym !identify.
    text = text.replace("!id:", "!identify:")

    logger.debug(f"Parsing {len(text)} chars of text.")

    def process_args(arg_string, is_quoted):
        """Process arguments and extract specific_mode flags."""
        if is_quoted:
            return [arg_string], [False]

        args_temp = re.split(r"[,+]", arg_string)
        processed_args = []
        mode_flags = []

        for arg in args_temp:
            cleaned, is_specific_mode = _check_specific_mode(arg)
            if cleaned is None:
                # Invalid specific mode: skip this arg
                continue
            processed_args.append(cleaned)
            mode_flags.append(is_specific_mode)

        return processed_args, mode_flags

    # Commands with required arguments
    for cmd in SETTINGS["commands_with_args"]:
        cmd_lower = cmd.lower()
        pattern = r"(?i)" + re.escape(cmd) + r"(?:\"([^\"]+)\"|[ ]?([^\s]+))"
        matches = re.findall(pattern, text)

        for match in matches:
            canonical = (
                SETTINGS["command_aliases"]
                .get(cmd_lower, cmd_lower)
                .rstrip(":")
                .lstrip("!")
            )
            raw_args, specific_modes = process_args(
                match[0] or match[1], bool(match[0])
            )

            should_convert = cmd_lower not in SETTINGS["commands_skip_conversion"]
            args = [
                # Pass internal post type keywords (e.g. 'meta', 'community') through
                # as raw strings so !set can reclassify an Ajo as a Diskuto without
                # converter() treating them as invalid language lookups.
                arg
                if (
                    not should_convert or arg.lower() in SETTINGS["internal_post_types"]
                )
                else converter(arg, specific_mode=specific_modes[i])
                for i, arg in enumerate(raw_args)
            ]
            commands_dict[canonical].extend(args)

            # Track if any argument had specific_mode enabled
            if any(specific_modes):
                specific_mode_dict[canonical] = True

    # Commands with optional arguments
    for cmd in SETTINGS["commands_optional_args"]:
        cmd_lower = cmd.lower()
        base = cmd_lower.lstrip("!")
        pattern = r"(?i)" + re.escape(cmd) + r"(?:\"([^\"]+)\"|:[ ]?([^\s]+))?"
        matches = re.findall(pattern, text)

        for match in matches:
            raw = match[0] or match[1]
            if raw:
                raw_args, specific_modes = process_args(raw, bool(match[0]))

                should_convert = cmd_lower not in SETTINGS.get(
                    "commands_skip_conversion", []
                )
                args = [
                    converter(arg, specific_mode=specific_modes[i])
                    if should_convert
                    else arg
                    for i, arg in enumerate(raw_args)
                ]
                commands_dict[base].extend(args)

                # Track if any argument had specific_mode enabled
                if any(specific_modes):
                    specific_mode_dict[base] = True
            else:
                commands_dict.setdefault(base, [])

    # Commands with no arguments
    for cmd in SETTINGS["commands_no_args"]:
        cmd_lower = cmd.lower()
        if cmd_lower in text_lower:
            canonical = cmd_lower.lstrip("!")
            commands_dict.setdefault(canonical, [])

    # Special: CJK lookup using lookup_matcher
    # Supports: `term`, `term`:lang, `term`!, `term`:lang! formats
    from lookup.match_helpers import lookup_matcher

    if text.count("`") >= 1:
        # Check for disable_tokenization flag (trailing !)
        has_disable_tokenization = False

        # Pattern to match backtick lookups with optional language and trailing !
        # Matches: `term`!, `term`:lang!
        backtick_pattern = r"`([^`]+)`(?::(\w+))?(!)?"
        backtick_matches = re.findall(backtick_pattern, original_text)

        for term, lang, exclamation in backtick_matches:
            if exclamation:
                has_disable_tokenization = True
                break

        if has_disable_tokenization:
            disable_tokenization_dict["lookup_cjk"] = True

        # This is to allow for better matching on specific posts.
        language_code = None
        if parent_languages:
            code = parent_languages[0].preferred_code
            if code not in {"multiple", "generic", "unknown"} and len(code) in (2, 3):
                language_code = code

        # Pass disable_tokenization flag to lookup_matcher
        lookup_cjk = lookup_matcher(
            original_text, language_code, disable_tokenization=has_disable_tokenization
        )

        # lookup_cjk now returns: {'zh': [('可能', False), ('麻将', False)], 'ko': [('시계', True)]}
        logger.debug(
            f"lookup_cjk: found {sum(len(v) for v in lookup_cjk.values())} term(s) "
            f"across {len(lookup_cjk)} language(s). disable_tokenization={has_disable_tokenization}"
        )
        for lang, terms_with_flags in lookup_cjk.items():
            if lang == "lookup":
                # Old format without explicit flag - shouldn't happen with new lookup_matcher
                commands_dict["lookup_cjk"].extend(terms_with_flags)
            else:
                for term, is_explicit in terms_with_flags:
                    # Store as 3-tuple: (lang, term, explicit)
                    commands_dict["lookup_cjk"].append((lang, term, is_explicit))

    # Special: Wikipedia lookup using {{braces}}
    if text.count("{{") > 0 and text.count("}}") > 0:
        wiki_terms = extract_text_within_curly_braces(original_text)
        if wiki_terms:
            commands_dict["lookup_wp"].extend(wiki_terms)

    # Finalize Komando list with deduplication
    commands = []
    for name, args in commands_dict.items():
        is_specific = specific_mode_dict.get(name, False)
        disable_tokenization = disable_tokenization_dict.get(name, False)

        # Deduplicate arguments
        deduped_args = _deduplicate_args(args)

        if any(isinstance(arg, tuple) for arg in deduped_args):
            commands.append(
                Komando(
                    name,
                    deduped_args,
                    specific_mode=is_specific,
                    disable_tokenization=disable_tokenization,
                )
            )
        else:
            commands.append(
                Komando(
                    name,
                    list(deduped_args),
                    specific_mode=is_specific,
                    disable_tokenization=disable_tokenization,
                )
            )

    logger.debug(f"Returning {len(commands)} komando(s): {[c.name for c in commands]}")
    return commands


if "__main__" == __name__:
    while True:
        my_input = input(
            "Enter the comment text with commands you'd like to test here: "
        )
        commands_new = extract_commands_from_text(my_input)
        if not commands_new:
            print("No commands found.")
        else:
            for command_new in commands_new:
                print(f"* {command_new}")
                print("=" * 10)
