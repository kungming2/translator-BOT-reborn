
### Points

The points system on r/translator is designed to serve as a way for community members to track their contributions. 

#### Design Principles

1. **Points are somewhat weighted by language**, since the opportunity to translate posts is not always equal on this subreddit. For example, Japanese is at least 150 times more requested than Tamil. The points system has a "language multiplier" (see below) that is used for awarding translation points.
2. **People who contribute should get some points**, even if their comment isn't the first one with `!translated` in it. Thus, someone who verifies a translation is correct, identifies an "Unknown" post, or writes something substantive will get some points, too, since they help keep our subreddit organized and informative. 
3. **There should be a flat system to reward good comments**, regardless of language. If other redditors comment `+` on a comment, they can give that person a flat amount of points for contributing something good. Sometimes there is a detailed Japanese translation that deserves more than 2 points! 
4. **Points won't be displayed "live" in flairs**. This is unlike comparable discovery/solving subreddits like r/excel, r/PhotoshopRequest, or r/findareddit. On those other subreddits, commenters *can't* give themselves points; only the OP can. In our subreddit, translators *themselves* mark the posts as resolved since OPs generally have no way of assessing the translation themselves. The objective is also to make the points system to be one of recognition rather than competition, and that people would be motivated by other things than a small number next to their name. 

#### Language Multiplier

The formula for the language multiplier is `( 1 / ( 100 * [percentage of posts per month] ) * 35)`, up to a cap of `20`. This percentage is dynamically retrieved from the recorded statistics of the previous month, and will therefore adjust over time as languages get less or more popular. Hypothetically, if 35% of posts in a single month were for Arabic, its multiplier would go down to `1` next month. 

###### Examples (from 2017-09)

| Language | Percent of Posts | Multiplier |
|----------|------------------|------------|
| [Japanese](https://www.reddit.com/r/translator/wiki/japanese) | 35.89% | 1 |
| [Chinese](https://www.reddit.com/r/translator/wiki/chinese) | 17.53% | 2 |
| [German](https://www.reddit.com/r/translator/wiki/german) | 6.45% | 5 |
| [Arabic](https://www.reddit.com/r/translator/wiki/arabic) | 5.06% | 7 |
| [Spanish](https://www.reddit.com/r/translator/wiki/spanish) | 2.95% | 12 |
| [Hebrew](https://www.reddit.com/r/translator/wiki/hebrew) | 0.60% | 20 |
| [Tamil](https://www.reddit.com/r/translator/wiki/tamil) | 0.24% | 20 |

#### Point Values

| Item                                             | Points Value |
|--------------------------------------------------|--------------|
| *!translated* (provided a translation)           | 1 + (1 * language multiplier) |
| *!doublecheck*                                   | 1 + (1 * language multiplier) |
| *!identify*                                      | 3 |
| \` Character/word Lookup                         | 2 |
| Substantive comment (no *!translated* comment)   | 1 + (.25 * language multiplier) |
| *!translated* (confirming another's translation) | 1 (and full points awarded to other translator) |
| *!missing*                                       | 1 |
| *!claim*                                         | 1 |
| *!page*                                          | 1 |
| *!search*                                        | 1 |