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
from lookup.other import lookup_matcher
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
    commands = []

    text = text.strip()

    # Commands with required arguments
    for cmd in SETTINGS['commands_with_args']:
        pattern = re.escape(cmd) + r'(?:\"([^\"]+)\"|([^\s]+))'
        matches = re.findall(pattern, text)
        for match in matches:
            canonical = SETTINGS['command_aliases'].get(cmd, cmd).rstrip(':').lstrip('!')
            if match[0]:  # quoted group matched
                raw_args = [match[0]]  # preserve as single argument
            else:
                raw_args = re.split(r'[,+]', match[1])  # unquoted → split on comma or plus

            should_convert = cmd not in ["!search:"]
            args = [converter(arg) if should_convert else arg for arg in raw_args]
            commands.append(Komando(canonical, args))

    for cmd in SETTINGS['commands_optional_args']:
        base = cmd.lstrip('!')
        pattern = re.escape(cmd) + r'(?:\"([^\"]+)\"|:([^\s]+))?'
        matches = re.findall(pattern, text)
        for match in matches:
            raw = match[0] or match[1]
            if raw:
                if match[0]:  # quoted
                    raw_args = [match[0]]
                else:
                    raw_args = re.split(r'[,+]', match[1])
                should_convert = cmd not in SETTINGS.get('commands_skip_conversion', [])
                args = [converter(arg) if should_convert else arg for arg in raw_args]
                commands.append(Komando(base, args))
            else:
                commands.append(Komando(base, []))

    # Commands with no arguments
    for cmd in SETTINGS['commands_no_args']:
        if cmd in text:
            commands.append(Komando(cmd.lstrip('!')))

    # Special: CJK lookup using lookup_matcher
    if text.count('`') > 1:
        cjk_lookup = lookup_matcher(text, None)  # TODO change when we have Lingvos integrated. it should pass the language on through.
        for lang, terms in cjk_lookup.items():
            # If the key is 'lookup', treat all terms as a single bucket without a language code
            if lang == 'lookup':
                for term in terms:
                    commands.append(Komando('cjk_lookup', [term]))  # just the term, no lang
            else:
                # Normal language-keyed terms
                for term in terms:
                    commands.append(Komando('cjk_lookup', [lang, term]))

    # Special: Wikipedia lookup using extract_text_within_curly_braces
    if text.count('{{') > 0 and text.count('}}') > 0:
        wiki_terms = extract_text_within_curly_braces(text)
        if wiki_terms:
            commands.append(Komando('wikipedia_lookup', wiki_terms))

    return commands


if "__main__" == __name__:
    while True:
        my_input = input("Enter the comment with commands you'd like to test here: ")
        print(extract_commands_from_text(my_input))
