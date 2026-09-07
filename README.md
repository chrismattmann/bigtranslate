BigTranslate
============

[![Build](https://github.com/chrismattmann/bigtranslate/actions/workflows/build.yml/badge.svg?branch=master)](https://github.com/chrismattmann/bigtranslate/actions/workflows/build.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![JDK](https://img.shields.io/badge/JDK-21-orange.svg)](https://adoptium.net/)
[![Powered by Mnemosyne](https://img.shields.io/badge/powered%20by-Mnemosyne%201.11.0-6E4B8E.svg)](https://github.com/chrismattmann/mnemosyne)
[![Website](https://img.shields.io/badge/website-chrismattmann.github.io%2Fbigtranslate-informational.svg)](https://chrismattmann.github.io/bigtranslate/)
[![Wiki](https://img.shields.io/badge/wiki-github-informational.svg)](https://github.com/chrismattmann/bigtranslate/wiki)

<a href="https://chrismattmann.github.io/bigtranslate/"><img align="left" width="80" height="80" src="https://chrismattmann.github.io/bigtranslate/assets/bt-mark.svg" alt="BigTranslate"></a>

A distributed system that machine-translates many millions of rows of TSV data
and indexes them into Apache&trade; Solr. Translation is
[Pantogloss](https://github.com/chrismattmann/pantogloss), a TensorFlow/Keras
many-to-English library that runs locally — no hosted translation APIs.
[Mnemosyne](https://github.com/chrismattmann/mnemosyne) splits the corpus and
distributes the work.

## How a run works

Translating every cell of a 38GB corpus is 836 million model calls; translating
every *distinct* string is 2.3 million. That 365x difference is the design, so
the pipeline deduplicates globally before translating anything and joins the
results back afterwards. One 8-core machine finishes in about 14 hours.

| Stage | Workflow | Does |
| --- | --- | --- |
| Extract | `ExtractStringsWorkflow` | Reads the corpus once, deduplicates every translatable cell, writes length-sorted chunks |
| Translate | `TranslateChunkWorkflow` | One instance per chunk, distributed across nodes; calls the Pantogloss server |
| Join | `JoinIndexWorkflow` | Builds a SQLite table of the translations, then sharded workers rejoin the corpus and post to Solr |

These are Workflow 2 (`PrioritizedQueueBasedWorkflowEngine`) workflows, so the
run scales with chunks rather than with files.
[Gloss](https://github.com/chrismattmann/bigtranslate/wiki/Gloss) is the GUI:
Vue 3 at `/gloss/`, with Translate/Reset from the browser, live run progress,
and a D3 density-bubble map of postings by location.

## Installing

```bash
PANTOGLOSS_SOURCE=~/git/pantogloss bin/bigtranslate-setup
bin/oodt restart
```

Pantogloss is not in `requirements.txt` because it is not published;
`PANTOGLOSS_SOURCE` takes a checkout, a wheel, or any pip specifier, and must
resolve to 0.19.0 or later. Use Python 3.10–3.12 — TensorFlow 2.18 publishes no
wheels above 3.12.

Restart the services rather than putting the tools on your own `PATH`: the PGEs
inherit the workflow manager's environment, and `env.sh` adds
`$BIGTRANSLATE_HOME/.venv/bin` at startup. `bin/bigtranslate translate` checks
the tools resolve first, because otherwise every step logs "command not found"
while the workflow still reports `FINISHED`.

## The original single-task pipeline

`BigTranslateWorkflow` is the earlier design: one task per TSV file, running
[ETLLib](https://github.com/chrismattmann/etllib/)'s `tsvtojson`, `repackage`
and `poster` around the translation step. It still ships and `requirements.txt`
still installs ETLLib for it, but it translates every cell and creates one
instance per file, so it is not the path to use at corpus scale.

## More

* [Installation](https://github.com/chrismattmann/bigtranslate/wiki/Installation)
* [How to run](https://github.com/chrismattmann/bigtranslate/wiki/How-to-Run)
* [How to re-run](https://github.com/chrismattmann/bigtranslate/wiki/Re-running-BigTranslate)
* [Interacting with BigTranslate](https://github.com/chrismattmann/bigtranslate/wiki/Interacting-with-BigTranslate)
* [Gloss](https://github.com/chrismattmann/bigtranslate/wiki/Gloss)

Clone the wiki with
`git clone https://github.com/chrismattmann/bigtranslate.wiki.git`
