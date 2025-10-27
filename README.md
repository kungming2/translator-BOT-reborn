# About

**translator-BOT** contains various routines that handle functions for [r/translator](https://www.reddit.com/r/translator/), the largest translation community on the [website](https://www.reddit.com). 

It consists of four separate routines that share codebases:

| Routine Name | Functions                                                                             |
|--------------|---------------------------------------------------------------------------------------|
| Ziwen        | Organizes the community through Reddit bot commands and sends notifications.          | 
| Wenju        | Runs regular maintenance and summary functions.                                       |
| Wenyuan      | Gathers statistics and makes monthly posts on the state of the community.             |
| Zhongsheng   | Responds to commands on Discord; mostly for inquiry into the state of bot operations. |

All functions generally post comments and send messages under the username [u/translator-BOT](https://www.reddit.com/user/translator-bot/). This bot was first deployed in late 2016 and after a period of feature expansion and consolidation, rewritten in 2025 to improve code readability, functions, and potential extensibility, hence the "reborn" tag.

# Documentation

Detailed documentation for Ziwen's various commands and functions can be found in the **[docs](/docs/index.md)** folder of this repo.