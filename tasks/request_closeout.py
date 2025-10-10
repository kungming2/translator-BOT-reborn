import re
import time

import praw

from config import logger
from reddit_sender import message_send
from responses import RESPONSE
from tasks import WENJU_SETTINGS


def closeout_posts():

    # TODO get a list of Ajos matching a certain time period between 7-10 days

    # TODO exclude posts that are translated or doublecheck

    # TODO exclude posts from a new SQLite3 table that have been seen

    # TODO add to that new SQLite3 table

    # TODO check for number of comments if more than minimum take action

    # TODO message the people regarding their post

    pass


if __name__ == "__main__":
    print(WENJU_SETTINGS)
