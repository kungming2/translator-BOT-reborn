#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles processing commands by users.
"""
import re

from languages import converter, iso_codes_deep_search, define_language_lists


def command_parser(comment_text, command):
    """
    Parses a comment for actionable information related to Ziwen commands like `!identify:`.
    # TODO allow for multiple id+ms+zh
    The command must include the colon `:` (e.g. `!identify:`).

    Parameters:
        comment_text (str): The comment body containing a Ziwen command.
        command (str): The command to parse, such as `!identify:`.
                       Note that the exclamation point and the colon should
                       be included if it's part of the command.

    Returns:
        tuple[str, bool] | None: A tuple containing the target string and a flag for advanced mode,
                                 or None if parsing fails.
    """
    advanced_mode = False
    longer_search = False
    match_text = ""

    # Normalize shorthand
    comment_text = comment_text.replace("!id:", "!identify:")
    comment_text = comment_text.replace("\n", " ")

    # Normalize common syntax issues
    if command + " " in comment_text:
        comment_text = comment_text.replace(command + " ", command)
    elif ":[" in comment_text:
        comment_text = comment_text.replace("[", '"').replace("]", '"')

    # Handle ":unknown-XXXX" syntax
    if ":unknown-" in comment_text:
        script_code = comment_text.split(":unknown-", 1)[1][:4]
        replacement = f":{script_code}! " if len(script_code) == 4 else f":{script_code} "
        comment_text = comment_text.replace(":unknown-", replacement)

    if command not in comment_text:
        return None

    remainder = comment_text.split(command, 1)[1]

    if "!" in remainder[:5]:  # Advanced mode with ! marker
        found = re.search(f"{re.escape(command)}(.*?)!", comment_text)
        if found:
            match_text = found.group(1).strip().lower()
            advanced_mode = " " not in match_text and "\n" not in match_text

    elif '"' in remainder[:2]:  # Longer phrase inside quotes
        try:
            found = re.search(r':"(.*?)"', comment_text)
            if found:
                match_text = found.group(1).strip().title()
                longer_search = True
        except AttributeError:
            return None
    match_lingvo = converter(match_text)

    if not longer_search:
        if not advanced_mode:
            found = re.search(rf"(?<={re.escape(command)})[\w\-<^'+]+", comment_text)
            if not found:
                return None
            match_text = found.group(0).strip().lower()
            match_lingvo = converter(match_text)

            # If it's a possible script code, double check TODO
            if len(match_text) == 4:
                script_check = iso_codes_deep_search(match_text, True)
                if script_check and match_text.title() not in define_language_lists()['ISO_NAMES']:
                    advanced_mode = True

        return match_lingvo, advanced_mode

    return (match_lingvo, advanced_mode) if match_text else None


if __name__ == "__main__":
    print(command_parser("!identify:tlh+sindarin", "!identify:"))
