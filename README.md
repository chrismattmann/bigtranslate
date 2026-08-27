BigTranslate
============

[![Build](https://github.com/chrismattmann/bigtranslate/actions/workflows/build.yml/badge.svg?branch=master)](https://github.com/chrismattmann/bigtranslate/actions/workflows/build.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![JDK](https://img.shields.io/badge/JDK-21-orange.svg)](https://adoptium.net/)
[![Powered by Mnemosyne](https://img.shields.io/badge/powered%20by-Mnemosyne%201.11.0-6E4B8E.svg)](https://github.com/chrismattmann/mnemosyne)
[![Website](https://img.shields.io/badge/website-chrismattmann.github.io%2Fbigtranslate-informational.svg)](https://chrismattmann.github.io/bigtranslate/)

A distributed, parallelized (Map Reduce) system that uses [Pantogloss](https://github.com/chrismattmann/pantogloss) to machine-translate many millions of rows of TSV data. Pantogloss is a TensorFlow/Keras many-to-English library that runs locally — no hosted translation APIs. BigTranslate uses [Mnemosyne](https://github.com/chrismattmann/mnemosyne) to split and distribute those translations. The system has been tested on up to 190 million rows of TSV data involving millions of translations on 16-core nodes and finishes in reasonable amounts of time. BigTranslate uses [ETLLib](https://github.com/chrismattmann/etllib/) (`tsvtojson`, `repackage`, `poster`) to prepare records for Pantogloss. Once the data is translated it is ingested into Apache&trade; Solr for querying and large scale analytics and retrieval. [Gloss](https://github.com/chrismattmann/bigtranslate/wiki/Gloss) is the GUI: Vue 3 at `http://localhost:8080/gloss/`, with Translate/Reset from the browser (the CLI still starts runs) and a D3 density-bubble map of postings by location.

Translation is performed by Pantogloss with a Spanish&rarr;English employment glossary and a local cache. The PGE `pantogloss-translatejson` runs the model offline over selected columns.

BigTranslate needs the Python tools `tsvtojson`, `repackage` and `poster` from
ETLLib (Python 3.10+, plus libmagic). In an unpacked distribution, one command
installs them into a virtual environment beside the services:

```bash
PANTOGLOSS_SOURCE=~/git/pantogloss bin/bigtranslate-setup
bin/oodt restart
```

Pantogloss is not in `requirements.txt` because it is not published, so
`PANTOGLOSS_SOURCE` points the setup script at a checkout, a wheel, or any pip
specifier. It goes into the same environment as ETLLib rather than one of its
own: the PGE runs `pantogloss-translatejson` through `#!/usr/bin/env python3`,
which picks whichever interpreter is first on `PATH`. Omit `PANTOGLOSS_SOURCE`
if you only want the ETLLib tools; the setup script says which of the four it
ended up with.

Use Python 3.10--3.12. Pantogloss needs TensorFlow 2.18, which publishes no
wheels above 3.12, so `bigtranslate-setup` prefers `python3.12` and works down
from there. `PYTHON` overrides the choice.

The restart matters. The PGEs that call these tools are run by the workflow
manager and inherit *its* environment, so putting the tools on your own `PATH`
is not enough; `env.sh` adds `$BIGTRANSLATE_HOME/.venv/bin` when the services
start. `bin/bigtranslate translate` checks the tools resolve before it does
anything, because without them each step logs "command not found" into its own
file while the workflow still reports `FINISHED` -- a run that looks like it
worked and translated nothing.

To install into an environment you manage yourself instead, the dependency list
is `requirements.txt`, shipped in the distribution:

```bash
python3 -m pip install -r requirements.txt
```

Translation is Pantogloss; the `etllib[translate]` extra is not needed.

See the wiki for more information on installing and running BigTranslate:  
* [Installation instructions](https://github.com/chrismattmann/bigtranslate/wiki/Installation)  
* [How to run](https://github.com/chrismattmann/bigtranslate/wiki/How-to-Run)  
* [How to re-run](https://github.com/chrismattmann/bigtranslate/wiki/Re-running-BigTranslate)  
* [How to interact with BigTranslate](https://github.com/chrismattmann/bigtranslate/wiki/Interacting-with-BigTranslate)
* [Gloss](https://github.com/chrismattmann/bigtranslate/wiki/Gloss) — Vue 3 GUI at `/gloss/` (Translate/Reset from the browser, density-bubble map of postings)  

You can clone the wiki by running  
`git clone https://github.com/chrismattmann/bigtranslate.wiki.git`
