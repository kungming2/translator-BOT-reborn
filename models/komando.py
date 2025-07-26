#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Defines the Komando command structure and class,
along with related functions. This represents a command called within a
comment, along with the data associated with that comment call.
"""
import re
import shlex

from config import SETTINGS
from languages import converter
from utility import extract_text_within_curly_braces


class Komando:
    def __init__(self, name, data=None):
        self.name = name  # e.g., "identify", "translated"
        # For data, ["es"], ["la", "grc"] as Lingvos or None
        # lookup and wiki ones get a list of strings
        self.data = data

    def __repr__(self):
        return f"Komando(name={self.name!r}, data={self.data!r})"


def split_arguments(arg_str):
    """Splits arguments respecting quoted substrings."""
    try:
        return shlex.split(arg_str)
    except ValueError:
        return [arg_str]


def extract_commands_from_text(text):
    from collections import defaultdict

    commands_dict = defaultdict(list)
    original_text = text.strip()

    # Normalize curly quotes in both cases
    text = original_text.replace('“', '"').replace('”', '"')
    text = text.replace('‘', "'").replace('’', "'")
    text_lower = text.lower()  # For case-insensitive command detection

    # Replace !id with synonym !identify.
    text = text.replace('!id:', "!identify:")

    # Commands with required arguments
    for cmd in SETTINGS['commands_with_args']:
        cmd_lower = cmd.lower()
        pattern = r"(?i)" + re.escape(cmd) + r'(?:\"([^\"]+)\"|([^\s]+))'
        matches = re.findall(pattern, text)

        for match in matches:
            canonical = SETTINGS['command_aliases'].get(cmd_lower, cmd_lower).rstrip(':').lstrip('!')
            if match[0]:  # quoted group matched
                raw_args = [match[0]]
            else:
                raw_args = re.split(r'[,+]', match[1])

            should_convert = cmd_lower not in ["!search:"]
            args = [converter(arg) if should_convert else arg for arg in raw_args]
            commands_dict[canonical].extend(args)

    # Commands with optional arguments
    for cmd in SETTINGS['commands_optional_args']:
        cmd_lower = cmd.lower()
        base = cmd_lower.lstrip('!')
        pattern = r"(?i)" + re.escape(cmd) + r'(?:\"([^\"]+)\"|:([^\s]+))?'
        matches = re.findall(pattern, text)

        for match in matches:
            raw = match[0] or match[1]
            if raw:
                if match[0]:
                    raw_args = [match[0]]
                else:
                    raw_args = re.split(r'[,+]', match[1])

                should_convert = cmd_lower not in SETTINGS.get('commands_skip_conversion', [])
                args = [converter(arg) if should_convert else arg for arg in raw_args]
                commands_dict[base].extend(args)
            else:
                commands_dict.setdefault(base, [])

    # Commands with no arguments
    for cmd in SETTINGS['commands_no_args']:
        cmd_lower = cmd.lower()
        if cmd_lower in text_lower:
            canonical = cmd_lower.lstrip('!')
            commands_dict.setdefault(canonical, [])

    # Special: CJK lookup using lookup_matcher
    # Note that since the language code here is OPTIONAL, it won't
    # tokenize. Call lookup_matcher directly to do that.
    from lookup.other import lookup_matcher
    if text.count('`') > 1:
        cjk_lookup = lookup_matcher(original_text, None)
        for lang, terms in cjk_lookup.items():
            if lang == 'lookup':
                commands_dict['cjk_lookup'].extend(terms)
            else:
                for term in terms:
                    commands_dict['cjk_lookup'].append([lang, term])

    # Special: Wikipedia lookup using {{braces}}
    if text.count('{{') > 0 and text.count('}}') > 0:
        wiki_terms = extract_text_within_curly_braces(original_text)
        if wiki_terms:
            commands_dict['wikipedia_lookup'].extend(wiki_terms)

    # Finalize Komando list
    commands = []
    for name, args in commands_dict.items():
        if any(isinstance(arg, list) for arg in args):
            commands.append(Komando(name, args))
        else:
            commands.append(Komando(name, list(args)))

    return commands


if "__main__" == __name__:
    while True:
        my_input = input("Enter the comment with commands you'd like to test here: ")
        commands_new = extract_commands_from_text(my_input)
        for command_new in commands_new:
            print(command_new)

