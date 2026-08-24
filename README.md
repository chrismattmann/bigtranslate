BigTranslate
============

[![Build](https://github.com/chrismattmann/bigtranslate/actions/workflows/build.yml/badge.svg?branch=master)](https://github.com/chrismattmann/bigtranslate/actions/workflows/build.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![JDK](https://img.shields.io/badge/JDK-21-orange.svg)](https://adoptium.net/)
[![Powered by Mnemosyne](https://img.shields.io/badge/powered%20by-Mnemosyne%201.11.0-6E4B8E.svg)](https://github.com/chrismattmann/mnemosyne)
[![Website](https://img.shields.io/badge/website-chrismattmann.github.io%2Fbigtranslate-informational.svg)](https://chrismattmann.github.io/bigtranslate/)

A distributed, parallelized (Map Reduce) system that uses [Pantogloss](https://github.com/chrismattmann/pantogloss) to machine-translate many millions of rows of TSV data. Pantogloss is a TensorFlow/Keras many-to-English library that runs locally — no hosted translation APIs. BigTranslate uses [Mnemosyne](https://github.com/chrismattmann/mnemosyne) to split and distribute those translations. The system has been tested on up to 190 million rows of TSV data involving millions of translations on 16-core nodes and finishes in reasonable amounts of time. BigTranslate uses [ETLLib](https://github.com/chrismattmann/etllib/) (`tsvtojson`, `repackage`, `poster`) to prepare records for Pantogloss. Once the data is translated it is ingested into Apache&trade; Solr for querying and large scale analytics and retrieval.

Translation is performed by Pantogloss with a Spanish&rarr;English employment glossary and a local cache. The PGE `pantogloss-translatejson` runs the model offline over selected columns.

Install ETLLib (Python 3.10+, plus libmagic) so `tsvtojson`, `repackage`, and `poster` are on your `PATH`. Translation is Pantogloss; the `etllib[translate]` extra is not needed:

```bash
python3 -m pip install "etllib @ git+https://github.com/chrismattmann/etllib.git"
# or, from this repo:
python3 -m pip install -r requirements.txt
```

See the wiki for more information on installing and running BigTranslate:  
* [Installation instructions](https://github.com/chrismattmann/bigtranslate/wiki/Installation)  
* [How to run](https://github.com/chrismattmann/bigtranslate/wiki/How-to-Run)  
* [How to re-run](https://github.com/chrismattmann/bigtranslate/wiki/Re-running-BigTranslate)  
* [How to interact with BigTranslate](https://github.com/chrismattmann/bigtranslate/wiki/Interacting-with-BigTranslate)  

You can clone the wiki by running  
`git clone https://github.com/chrismattmann/bigtranslate.wiki.git`
