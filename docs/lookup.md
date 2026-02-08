# Lookup Functions (Reddit)

[← Back to Home](./index.md)

## Introduction

Ziwen has two lookup functions that are called by wrapping lookup terms with characters, instead of calling an overt command.

## CJK Lookup

When a user submits a comment with two \` ([grave accents](https://en.wikipedia.org/wiki/Grave_accent), also known as back ticks) around a text string, Ziwen will look up the string to see if it's a Chinese, Japanese, or Korean character, word, or *[chengyu](https://en.wikipedia.org/wiki/Chengyu)/[yojijukugo](https://en.wikipedia.org/wiki/Yojijukugo)* (idioms) or a word for the post's language. Ziwen will then return its findings, including pronunciations, meaning, and links to online dictionaries for that search. Unlike other commands, there is no explicit word trigger for this function - the presence of two \` around the lookup term is sufficient. (This is usually used to indicate code text on Reddit)

Chinese or Japanese explanations are included in *chengyu* and *yojijukugo* lookups if Ziwen can find them.

On average, [55% of posts](https://www.reddit.com/r/translator/wiki/overall_statistics) on r/translator are for one of the Chinese, Japanese, or Korean (CJK) languages. 

#### Optional Syntax

A language tag added to a lookup will force a lookup in that language, even on a post that's of a different language. E.g. `文化`:ja will return a Japanese lookup for that term, even if the comment is on a Chinese post and would normally result in the Chinese information for that term.

An exclamation mark ! appended to the lookup (`年年有余`!, `井底之蛙`:zh!) will disable tokenization of the lookup. If you're adding a language tag to the lookup, the exclamation mark should go on the very end.


#### Dictionaries

Information from the following dictionaries/databases are included directly in CJK lookup:

* `zh_character`: [MDBG](https://www.mdbg.net/chinese/dictionary), [Chinese Character Web API](http://ccdb.hemiola.com/), [Dictionary of Chinese Character Variants](https://dict.variants.moe.edu.tw/), [书法字典](https://www.shufazidian.com/)
* `zh_word`: [MDBG](https://www.mdbg.net/chinese/dictionary), [Soothill-Hodous Dictionary of Chinese Buddhist Terms](https://mahajana.net/en/library/texts/a-dictionary-of-chinese-buddhist-terms), [CC-Canto](https://cantonese.org/), [Babelcarp](https://babelcarp.org/babelcarp/)
* `ja_character`: [Jisho](https://jisho.org/)  
* `ja_word`: [Jisho](https://jisho.org/), [Japanese Onomatopoeia Search](https://nsk.sh/tools/jp-onomatopoeia/), [人名漢字辞典](https://kanji.reader.bz/), [四字熟語辞典](https://yoji.jitenon.jp/)
* `ko_word`: [National Institute of Korean Language's Korean-English Learners' Dictionary](https://krdict.korean.go.kr/eng/mainAction)

#### Notes

* The information that Ziwen returns generally depends on the language of the post. Chinese posts will return Chinese information, and so on. 
  * But, **if there's a language identification command in the comment, Ziwen will return information for that language.** For example, a comment "This is Chinese: ``吹牛`` !identify:zh" on a Japanese post will result in a Chinese lookup.
* If no words are found for a multi-character compound, it will collate individual character data together in a table. For example, the nonsensical search `強彥` will return separate entries for 強 and 彥 in a table.
* If a single Chinese or Japanese character is looked up, Ziwen will retrieve [calligraphy and seal script](https://www.reddit.com/r/translator/comments/6wsaks/japanese_english_shirt_post/dmahdae/) images for it and include those images in its findings. 
* The ability to call specific language and Japanese surnames was first suggested by u/nomfood.


## Wikipedia Lookup

Wrapping dual curly braces around a search term, tags something for Ziwen to look up on [Wikipedia](https://en.wikipedia.org/wiki/Main_Page) and returns the results in a comment reply. This is usually to give the requester more cultural context and information.

```
This is from the {{Qianlong Era}}, and it's {{Jingdezhen porcelain}} from China.
```

This example would return Wikipedia links and short summaries for "[Qianlong Emperor](https://en.wikipedia.org/wiki/Qianlong_Emperor)" and "[Jingdezhen porcelain](https://en.wikipedia.org/wiki/Jingdezhen_porcelain)".

#### Notes

* If Wikipedia has a location coordinates that is associated with the page, Ziwen will try and include a relevant [OpenStreetMap](https://www.openstreetmap.org/) link to that location. 