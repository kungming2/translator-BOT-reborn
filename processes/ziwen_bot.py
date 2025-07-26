#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Main script to check comments and act upon them.
"""
from prawcore import exceptions

from commands import HANDLERS
from config import logger, SETTINGS
from connection import REDDIT, credentials_source
from database import db
from models.ajo import Ajo
from models.instruo import Instruo, comment_has_command
from statistics import user_statistics_writer
from title_handling import Titolo
from points import points_tabulator


def ziwen_bot():
    """
    Main runtime for r/translator that checks for keywords and commands.

    :return: Nothing.
    """
    subreddit = SETTINGS['subreddit']
    thanks_keywords = SETTINGS['thanks_keywords']
    username = credentials_source['USERNAME']
    logger.debug(f'Fetching new r/{subreddit} comments...')
    r = REDDIT.subreddit(subreddit)

    try:
        comments = list(r.comments(limit=SETTINGS['max_posts']))
    except exceptions.ServerError:
        # Server issues.
        return

    # Start processing comments.
    for comment in comments:
        comment_id = comment.id
        original_post = comment.submission  # Returns a submission object of the parent to work with
        comment_body = comment.body.lower()

        # Skip comments with deleted authors
        try:
            author_name = comment.author.name
        except AttributeError:
            continue

        # Skip own bot comments
        if author_name == username:
            continue

        # Check to see if the comment has already been acted upon.
        if db.cursor_main.execute('SELECT 1 FROM old_comments WHERE ID = ?', (comment_id,)).fetchone():
            # Comment already processed
            continue

        # Mark comment as processed in the database
        # TODO remove block out
        '''
        db.cursor_main.execute('INSERT INTO old_comments (ID) VALUES (?)', (comment_id,))
        db.conn_main.commit()
        '''

        # Derive an Instruo, and act on it if there are commands.
        # Note that an Instruo can have multiple commands associated
        # with it.
        if comment_has_command(comment_body):

            # Initialize the variables the handlers will require.
            instruo = Instruo.from_comment(comment)

            # TODO actual version will load from Ajo database, this is a test.
            post_ajo = Ajo.from_titolo(Titolo.process_title(original_post), original_post)

            print(instruo)
            print(comment.permalink)

            # Pass off to handling functions depending on the command.
            # e.g. an identify command will pass off to the handler
            # function located in identify.py
            for komando in instruo.commands:
                handler = HANDLERS.get(komando.name.lower())

                # A matching handler for the command is found.
                # Pass off the information for it to handle.
                if handler:
                    handler(comment, instruo, komando, post_ajo)
                else:
                    logger.warning(f"No handler for command: {komando.name}")

            print('-------------------')
            # TODO calculate points for the comment
            # points_tabulator(comment, original_post)  # Requires an AJO

            # Record data on user commands.
            user_statistics_writer(instruo)
            logger.debug("[ZW] Bot: Recorded user commands in database.")

        # TODO Process THANKS keywords from original posters.
        if any(keyword in comment_body for keyword in thanks_keywords):
            # create a separate function here
            pass


if __name__ == '__main__':
    ziwen_bot()
