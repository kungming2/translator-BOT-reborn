#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Defines the Komando command structure and class,
along with related functions. This represents a command called within a
comment, along with the data associated with that comment call.
"""

import re
import shlex
from collections import defaultdict

from config import SETTINGS
from languages import converter
from utility import extract_text_within_curly_braces


class Komando:
    def __init__(self, name, data=None, specific_mode=False):
        self.name = name  # e.g., "identify", "translated"
        # For data, ["es"], ["la", "grc"] as Lingvos or None
        # lookup and wiki ones get a list of strings
        self.data = data
        self.specific_mode = specific_mode

    def __repr__(self):
        return f"Komando(name={self.name!r}, data={self.data!r}, specific_mode={self.specific_mode!r})"

    def to_dict(self):
        return {
            "name": self.name,
            "data": self.data,
            "specific_mode": self.specific_mode,
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
                name=self.name, data=self.data, specific_mode=self.specific_mode
            )

        remapped_data = [[target_lang_code, term] for _, term in self.data]

        return Komando(
            name=self.name, data=remapped_data, specific_mode=self.specific_mode
        )


def check_specific_mode(arg_str):
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


def split_arguments(arg_str):
    """Splits arguments respecting quoted substrings."""
    try:
        return shlex.split(arg_str)
    except ValueError:
        return [arg_str]


def extract_commands_from_text(text):
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

    Arguments are converted to Lingvo objects via the converter() function unless
    the command is in the skip-conversion list.

    :param text: The input text to parse for commands.
    :return: A list of Komando objects with extracted commands and their arguments.
    """
    commands_dict = defaultdict(list)
    specific_mode_dict = defaultdict(bool)
    original_text = text.strip()

    # Normalize curly quotes in both cases
    text = original_text.replace(""", '"').replace(""", '"')
    text = text.replace("'", "'").replace("'", "'")

    # Remove backslash escapes before backticks (from Reddit's rich text formatter)
    text = text.replace("\\`", "`")

    text_lower = text.lower()  # For case-insensitive command detection

    # Replace !id with synonym !identify.
    text = text.replace("!id:", "!identify:")

    def process_args(arg_string, is_quoted):
        """Process arguments and extract specific_mode flags."""
        if is_quoted:
            return [arg_string], [False]

        args_temp = re.split(r"[,+]", arg_string)
        processed_args = []
        mode_flags = []

        for arg in args_temp:
            cleaned, is_specific_mode = check_specific_mode(arg)
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

            should_convert = cmd_lower not in ["!search:"]
            args = [
                converter(arg, specific_mode=specific_modes[i])
                if should_convert
                else arg
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
    # Supports: `term`, `term`:lang formats
    from lookup.match_helpers import lookup_matcher

    if text.count("`") >= 1:
        lookup_cjk = lookup_matcher(original_text, None)
        for lang, terms in lookup_cjk.items():
            if lang == "lookup":
                commands_dict["lookup_cjk"].extend(terms)
            else:
                for term in terms:
                    commands_dict["lookup_cjk"].append([lang, term])

    # Special: Wikipedia lookup using {{braces}}
    if text.count("{{") > 0 and text.count("}}") > 0:
        wiki_terms = extract_text_within_curly_braces(original_text)
        if wiki_terms:
            commands_dict["lookup_wp"].extend(wiki_terms)

    # Finalize Komando list
    commands = []
    for name, args in commands_dict.items():
        is_specific = specific_mode_dict.get(name, False)
        if any(isinstance(arg, list) for arg in args):
            commands.append(Komando(name, args, specific_mode=is_specific))
        else:
            commands.append(Komando(name, list(args), specific_mode=is_specific))

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
