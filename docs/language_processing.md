# Language Processsing

[← Back to Home](./index.md)

## Introduction

#### Codes

As noted in the index documentation, all routines support:

* [ISO 639-1/3](https://en.wikipedia.org/wiki/ISO_639), two or three-letter codes for languages (`ar`, `ja`, etc.)
* [ISO 15924](https://en.wikipedia.org/wiki/ISO_15924#List_of_codes), four-letter codes for scripts (`Cyrl`, `Latn`, etc.)
* [ISO 3166](https://en.wikipedia.org/wiki/ISO_3166), two or three-letter codes for countries (`GB`, `MX`, etc.)

Less publicly advertised is that routines also support [ISO 639-2B](https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes), a subset of ISO 639-2 that contains "bibliographic" codes derived from the English name of the language. There are only twenty of these codes and they are not widely known or used; examples would include `wel` for [Welsh](https://en.wikipedia.org/wiki/Welsh_language) and `arm` for [Armenian](https://en.wikipedia.org/wiki/Armenian_language). Their inclusion is solely for completion's sake.

Also supported, though rarely seen, is [Linguist Lists's local use codes](https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Languages/List_of_ISO_639-3_language_codes_used_locally_by_Linguist_List), though standard ISO equivalents are always better and preferred.

#### Unsupported

Routines *do not* support the [rest of the ISO 639-2](https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes) standard, as most of those codes are:

1. Also exist in ISO 639-3
2. For a language family that contains multiple languages (e.g. `apa` for the [Apache](https://en.wikipedia.org/wiki/Southern_Athabaskan_languages) language family)

If someone wishes to use an ISO 639-2 code for a language family, they should instead choose a more specific ISO 639-3 code that fits. 

## Converter

The `converter()` function in `languages.py` is the most used function in the codebase. Its purpose is to accept any input and interpret what language that input intended. The converter will accept the aforementioned codes, standard language names, but even misspelllings to help return accurate identification of languages from user input.

#### The Lingvo Class 

The converter returns language identifications as `Lingvo` objects ([Esperanto](https://en.wikipedia.org/wiki/Esperanto) for "[language](https://en.wiktionary.org/wiki/lingvo)"), which contain practically all the information needed for a language's details, including its name and code, but also statistical information from the subreddit and some reference data.

All `Lingvo` objects also have a `preferred_code`, which is what is used most often in the code. For non-script languages, the `preferred_code` is the ISO 639-1 code if it exists, or the ISO 639-3 code if an ISO 639-1 does not exist. 

Therefore, [German's](https://en.wikipedia.org/wiki/German_language) `preferred_code` is `de` (not `deu`), while [Cantonese](https://en.wikipedia.org/wiki/Cantonese), which does not have an ISO 639-1 code, has a `preferred_code` of `yue`. 

Scripts' `preferred_code` are their ISO 15924 codes in lowercase. As an example, [Siddham's](https://en.wikipedia.org/wiki/Siddha%E1%B9%83_script) `preferred_code` is `sidd`.
