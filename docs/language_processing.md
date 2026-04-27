# Language Processing

[← Back to Home](./index.md)

## Introduction

#### Codes

As noted in the home/index documentation, all routines support:

* [ISO 639-1/3](https://en.wikipedia.org/wiki/ISO_639), two or three-letter codes for languages (`ar`, `ja`, etc.)
* [ISO 15924](https://en.wikipedia.org/wiki/ISO_15924#List_of_codes), four-letter codes for scripts (`Cyrl`, `Latn`, etc.)
* [ISO 3166](https://en.wikipedia.org/wiki/ISO_3166), two or three-letter codes for countries (`GB`, `MX`, etc.)

Less publicly advertised is that routines also support [ISO 639-2B](https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes), a subset of ISO 639-2 that contains "bibliographic" codes derived from the English name of the language. There are only twenty of these codes and they are not widely known or used; examples would include `wel` for [Welsh](https://en.wikipedia.org/wiki/Welsh_language) and `arm` for [Armenian](https://en.wikipedia.org/wiki/Armenian_language). Their inclusion is solely for completion's sake.

Also supported, though rarely seen, are [Linguist List's local use codes](https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Languages/List_of_ISO_639-3_language_codes_used_locally_by_Linguist_List), though standard ISO equivalents are always better and preferred.

Generally speaking, any field or value that accepts a language code will also accept a language *name*.

#### Unsupported

Routines *do not* support the [rest of the ISO 639-2](https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes) standard, as most of those codes:

1. Also exist in ISO 639-3
2. Are for a language family that contains multiple individual languages (e.g. `apa` for the [Apache](https://en.wikipedia.org/wiki/Southern_Athabaskan_languages) language family)

If someone wishes to use an ISO 639-2 code for a language family, they should instead choose a more specific ISO 639-3 code that fits. 

## Converter

The `converter()` function in `languages.py` is the most essential function in the codebase. Its purpose is to accept any input and interpret what language that input intended. The converter will accept the aforementioned codes, standard language names, and even misspellings to help return accurate identification of languages from user input.

#### The Lingvo Class 

The converter returns language identifications as `Lingvo` objects ([Esperanto](https://en.wikipedia.org/wiki/Esperanto) for "[language](https://en.wiktionary.org/wiki/lingvo)"), which contain practically all the information needed for a language's details, including its name and code, but also statistical information from the subreddit and some reference data.

All `Lingvo` objects also have a `preferred_code`, which is also the attribute used most often in the code. For non-script languages, the `preferred_code` is the ISO 639-1 code if it exists, or the ISO 639-3 code if an ISO 639-1 code does not exist. In previous documentation for translator-BOT v1.0+ this was often referred to as the "CSS code".

Therefore, [German's](https://en.wikipedia.org/wiki/German_language) `preferred_code` is `de` (not `deu`), while [Cantonese](https://en.wikipedia.org/wiki/Cantonese), which does not have an ISO 639-1 code, has a `preferred_code` of `yue`. 

Three non-language `preferred_code` attributes are non-standard due to the need for backwards compatibility:

| Name               | Preferred Code | [Standard ISO 639-3](https://en.wikipedia.org/wiki/ISO_639-3#Special_codes) Code |
|--------------------|----------------|----------------------------------------------------------------------------------|
| Generic            | `generic`      | `mis`                                                                            |
| Unknown            | `unknown`      | `und`                                                                            |
| Multiple Languages | `multiple`     | `mul`                                                                            |

In all of these cases, the standard code will also work in `converter()`.

Scripts' `preferred_code` are their ISO 15924 codes in lowercase. As an example, [Siddham's](https://en.wikipedia.org/wiki/Siddha%E1%B9%83_script) `preferred_code` is `sidd`.

###### Regional Codes

By default, Lingvos are *not* associated with a country and will not have a `country` attribute. Note that the `language_data` YAML file will have a country associated with each language, but that is the [Ethnologue](https://www.ethnologue.com/) association and not relevant for Lingvos, as it is considered over-descriptive to have every Japanese post be a `ja-JP` Lingvo.

However, specific identifications made by users or country/region-language combination strings can be used to further define a language and give its Lingvo a country attribute. For example:

```markdown
!identify:pt-BR                                             # Portuguese {Brazil}
!identify:french-canada                                     # French {Canada}
!translate:cantonese-HK                                     # Cantonese {Hong Kong}
```

Such regional language combinations are formatted as `language_name {country/region}`.

#### Examples

**Language name**
```
Input:  "zhuang"
Output: preferred_code `za`  |  ISO 639-3: zha  |  Name: Zhuang
```
 
**ISO 639-1 two-letter code**
```
Input:  "so"
Output: preferred_code `so`  |  ISO 639-3: som  |  Name: Somali
```

**ISO 639-3 three-letter code**
```
Input:  "haw"
Output: preferred_code `haw`  |  ISO 639-3: haw  |  Name: Hawaiian
```
Because Hawaiian has no ISO 639-1 code, its `preferred_code` falls back to the ISO 639-3 code.

**Language name (misspelled)**
```
Input:  "krean"   ← typo
Output: preferred_code `ko`  |  ISO 639-3: kor  |  Name: Korean
```
When an exact match is not found, the converter falls back to fuzzy matching against known names and alternates (e.g. `name_alternates` for Korean includes `Hangul`, `한국어`, etc.).
 
**ISO 15924 four-letter script code**
```
Input:  "blis"
Output: preferred_code `blis`  |  script_code: blis  |  Name: Blissymbols
```
Scripts are identified by their ISO 15924 code. Note that `language_code_1` and `language_code_3` are `unknown` for scripts, as they are not languages in the traditional sense.
 
**Language with Regional tag**
```
Input:  "pt-BR"
Output: preferred_code `pt`  |  ISO 639-3: por  |  Name: Portuguese {Brazil}
        country: BR  |  countries_associated: ['AO', 'BR', 'MZ', 'TL', 'CV']
```
A BCP 47-style language-region tag sets the `country` attribute on the returned Lingvo and appends the region to `name`, while `preferred_code` remains the base language code.
 
In each case the converter returns the same `Lingvo` structure regardless of how the language was specified, making downstream code agnostic to input format.
