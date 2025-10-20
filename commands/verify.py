#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Simple wrapper for the !verify command, which automatically
will verify someone for a language and change their flair accordingly.
"""

from verification import process_verification


def handle(comment, _instruo, _komando, _ajo) -> None:
    """Command handler called by ziwen_commands()."""

    process_verification(comment)
