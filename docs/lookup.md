# Lookup Functions (Reddit)

[← Back to Home](./index.md)

## Introduction

Ziwen has two lookup functions that are called by wrapping lookup terms with characters, instead of calling an overt command.

## CJK Lookup

When a user submits a comment with two \` ([grave accents](https://en.wikipedia.org/wiki/Grave_accent), also known as backticks) around a text string, Ziwen will look up the string to see if it's a Chinese, Japanese, or Korean character, word, or *[chengyu](https://en.wikipedia.org/wiki/Chengyu)/[yojijukugo](https://en.wikipedia.org/wiki/Yojijukugo)* (idioms), or a word for the post's language. Ziwen will then return its findings, including pronunciations, meanings, and links to online dictionaries for that search. Unlike other commands, there is no explicit word trigger for this function - the presence of two \` around the lookup term is sufficient. (This syntax is often used to indicate programming code text on Reddit)

Chinese or Japanese explanations are included in *chengyu* and *yojijukugo* lookups if Ziwen can find them.

On average, [55% of posts](https://www.reddit.com/r/translator/wiki/overall_statistics) on r/translator are for one of the Chinese, Japanese, or Korean (CJK) languages, thus necessitating a robust function for returning dictionary results in that language. 

#### Optional Syntax

A language tag added to a lookup will force a lookup in that language, even on a post that's of a different language. E.g. `文化`:ja will return a Japanese lookup for that term, even if the comment is on a Chinese post and would normally result in the Chinese information for that term.

An exclamation mark ! appended to the lookup (`年年有余`!, `井底之蛙`:zh!) will disable tokenization of the lookup. If you're adding a language tag to the lookup, the exclamation mark should go on the very end.


```text
`大`          # Returns character data for 大 ("big, great"), depending on the post's language category 
`立`:ja       # Returns character data for 立 ("establish, stand") in Japanese regardless of post language
`芒果`        # Returns word data for 芒果 ("mango") in Chinese
`睡觉`:zh     # Returns word data for 睡觉 ("sleep") in Chinese
`場合`:ja     # Returns word data for 場合 ("situation") in Japanese
`守株待兔`    # Returns word and chengyu data for 守株待兔 ("to sit around and wait") in Chinese
`천하`        # Returns word data for 천하 ("all-under-Heaven") in Korean
```

#### Dictionaries

The following sources are used by CJK lookup functions:

| Key | Language | Sources |
|-----|----------|---------|
| `zh_character` | Chinese (characters) | [MDBG](https://www.mdbg.net/chinese/dictionary) · [Chinese Character Web API](http://ccdb.hemiola.com/) · [Dictionary of Chinese Character Variants](https://dict.variants.moe.edu.tw/) · [书法字典](https://www.shufazidian.com/) |
| `zh_word` | Chinese (words) | [MDBG](https://www.mdbg.net/chinese/dictionary) · [Soothill-Hodous](https://mahajana.net/en/library/texts/a-dictionary-of-chinese-buddhist-terms) · [CC-Canto](https://cantonese.org/) |
| `ja_character` | Japanese (characters) | [Jisho](https://jisho.org/) |
| `ja_word` | Japanese (words) | [Jisho](https://jisho.org/) · [Japanese Onomatopoeia Search](https://nsk.sh/tools/jp-onomatopoeia/) · [人名漢字辞典](https://kanji.reader.bz/) · [四字熟語辞典](https://yoji.jitenon.jp/) |
| `ko_word` | Korean (words) | [National Institute of Korean Language](https://krdict.korean.go.kr/eng/mainAction) |

#### Notes

* The information that Ziwen returns generally depends on the language of the post. Chinese posts will return Chinese information, and so on. 
  * But, **if there's a language identification command in the comment, Ziwen will return information for that language.** For example, a comment "This is Chinese: ``吹牛`` !identify:zh" on a Japanese post will result in a Chinese lookup.
* If no words are found for a multi-character compound, it will collate individual character data together in a table. For example, the nonsensical search `強彥` will return separate entries for 強 and 彥 in a table.
* If a single Chinese or Japanese character is looked up, Ziwen will retrieve [calligraphy and seal script](https://www.reddit.com/r/translator/comments/6wsaks/japanese_english_shirt_post/dmahdae/) images for it and include those images in its findings.
* The edit tracking system tracks lookup terms, so if comments are edited and the lookup term (or tokenization) changes, Ziwen will edit its lookup comment to return the new information.
* The ability to call specific language and Japanese surnames was first suggested by u/nomfood.


## Wiktionary Lookup

Separate from the CJK lookup function detailed above is a catch-all [Wiktionary](https://en.wiktionary.org/wiki/Wiktionary:Main_Page) lookup that can search for words in any other (non-CJK) language.

Due to the not-fully-standardized nature of English Wiktionary content, lookup results may vary in how clean their formatting is, and words with clear entries (e.g. nouns, dictionary forms of verbs, etc.) will have the best results. For the most part, the lookup function will return etymology, pronunciation, and definitions for a word. Note that tokenization *will not be active* for Wiktionary lookups. 

The Wiktionary lookup uses the same backtick syntax as CJK lookup. Internally, Ziwen first runs the backtick text through the lookup matcher. Chinese, Japanese, and Korean terms are routed to `lookup_cjk`; all other recognized languages are routed to `lookup_wt`. The Wiktionary lookup will generally be conducted in the language of the post. That is, a lookup for `Sprache` on a German post will be automatically conducted for German. Appending a language tag like the CJK lookup text above will also work.

```text
`Wasser`               # Returns word data for Wasser ("water") on a German post
`вода`:ru              # Returns word data for вода ("water") in Russian
`vand`:danish          # Returns word data for vand ("water") in Danish
`ᎠᎹ`:chr              # Returns word data for ᎠᎹ ("water") in Cherokee
```


## Wikipedia Lookup

Wrapping dual curly braces around a search term tags something for Ziwen to look up on [Wikipedia](https://en.wikipedia.org/wiki/Main_Page) and returns the results in a comment reply. This is usually to give the requester more cultural context and information.

```
This is from the {{Qianlong Era}}, and it's {{Jingdezhen porcelain}} from China.
```

This example would return Wikipedia links and short summaries for "[Qianlong Emperor](https://en.wikipedia.org/wiki/Qianlong_Emperor)" and "[Jingdezhen porcelain](https://en.wikipedia.org/wiki/Jingdezhen_porcelain)".

#### Optional Syntax

A language tag added to a lookup will search the Wikipedia for that language instead of the English Wikipedia. For example:

```text
{{Cyrus the Great}}     # Searches en.wikipedia.org (default)
{{琵琶行}}:chinese       # Searches zh.wikipedia.org (Chinese Wikipedia)
{{Don Quijote}}:es      # Searches es.wikipedia.org (Spanish Wikipedia)
{{L. L. Zamenhof}}:eo   # Searches eo.wikipedia.org (Esperanto Wikipedia)
```

#### Notes

* If Wikipedia has location coordinates that are associated with the page, Ziwen will try and include a relevant [OpenStreetMap](https://www.openstreetmap.org/) link to that location (e.g. `{{Forbidden City}}`).
