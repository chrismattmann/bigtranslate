BigTranslate
============

A distributed, parallelized (Map Reduce) wrapper around [Apache&trade; Tika](http://tika.apache.org/) and its Translation API provided by [Tika-Python](http://github.com/chrismattmann/tika-python). BigTranslate uses Apache&trade; OODT to split and distribute machine translation of many millions of rows of data. The system has been tested on up to 190 million rows of TSV data involving millions of translations on 16-core nodes and finishes in reasonable amounts of time. BigTranslate uses [ETLLib](http://github.com/chrismattmann/etllib/) to provide a clean facade to JSON and TSV data processing, and to prepare data for translation using Tika. Once the data is translated it is ingested into Apache&trade; Solr for querying and large scale analytics and retrieval.

See the wiki for more information on installing and running BigTranslate:  
* [Installation instructions](https://github.com/chrismattmann/bigtranslate/wiki/Installation)  
* [How to run](https://github.com/chrismattmann/bigtranslate/wiki/How-to-Run)  
* [How to re-run](https://github.com/chrismattmann/bigtranslate/wiki/Re-running-BigTranslate)  
* [How to interact with DRAT](https://github.com/chrismattmann/bigtranslate/wiki/Interacting-with-BigTranslate)  

You can clone the wiki by running  
`git clone https://github.com/chrismattmann/bigtranslate.wiki.git`
