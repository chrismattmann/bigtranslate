# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Decoding a corpus that is not all UTF-8.

The employment TSVs were collected in 2012 from sites that did not agree on
an encoding, and they are still whatever they were then: of forty files
sampled, forty failed to decode as UTF-8. "Bolivar" is written with a
latin-1 0xed, and there are files where a single row carries both.

The original pipeline knew this. tsvtojson took ``-e conf/encoding.txt`` and
tried each encoding listed there in turn. The replacement scripts hardcoded
``decode("utf-8", "replace")``, which never fails and never says anything --
every non-UTF-8 byte simply became U+FFFD. It reached Solr that way: a
quarter of the indexed documents carry a damaged ``location``, which is the
field the density-bubble map and the geocoder both read.

The fix has to work a byte sequence at a time, not a line at a time. Most
lines here are valid UTF-8 carrying one stray latin-1 byte somewhere, so
"try UTF-8, fall back to latin-1 for the line" re-decodes the whole line and
turns every correct accent into mojibake -- "Bogota" with a valid UTF-8
a-acute came back as "BogotA-a" nonsense. That is worse than the bug it
replaces.

So UTF-8 decodes the line, and only the byte runs it rejects fall back
through the remaining encodings. Valid UTF-8 stays valid; the stray latin-1
byte beside it is read as latin-1; nothing becomes U+FFFD unless no listed
encoding can read it at all.
"""

import codecs
import os

# What conf/encoding.txt has always listed, for when it cannot be read.
DEFAULT_ENCODINGS = ("utf-8", "us-ascii", "latin-1")


def read_encodings(path=None):
    """The encodings to try, in order.

    Reads the same conf/encoding.txt the original pipeline passed to
    tsvtojson, so the two stay in step. Missing or empty falls back to the
    defaults rather than to bare UTF-8: a corpus that needed the fallback
    chain does not stop needing it because a config file went missing.
    """
    if not path or not os.path.exists(path):
        return list(DEFAULT_ENCODINGS)
    found = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            name = line.strip()
            if name and not name.startswith("#"):
                found.append(name)
    return found or list(DEFAULT_ENCODINGS)


def decode(value, encodings=DEFAULT_ENCODINGS):
    """Decode bytes, falling back per bad byte run rather than per line.

    The first listed encoding decodes the whole value; each run of bytes it
    rejects is retried against the ones after it. Doing this at the line
    level instead looks simpler and is wrong: these lines are mostly valid
    UTF-8 with one stray latin-1 byte, and re-reading the whole line as
    latin-1 to accommodate that byte mojibakes every accent that was already
    correct.
    """
    if isinstance(value, str):
        return value
    if not encodings:
        return value.decode("utf-8", "replace")
    primary, rest = encodings[0], list(encodings[1:])
    try:
        return value.decode(primary)
    except LookupError:
        # An unusable codec name in the config is not worth failing a run.
        return decode(value, rest) if rest else value.decode("utf-8", "replace")
    except UnicodeDecodeError:
        pass
    return value.decode(primary, _handler_for(rest))


_HANDLERS = {}


def _handler_for(fallbacks):
    """An error handler that reads rejected bytes with the next encoding.

    Registered once per fallback list because codecs.register_error is
    global; the name encodes the list so two different chains cannot collide.
    """
    name = "bt_encoding_" + "_".join(fallbacks or ["replace"])
    if name in _HANDLERS:
        return name

    def handle(error):
        raw = error.object[error.start:error.end]
        for encoding in fallbacks:
            try:
                return raw.decode(encoding), error.end
            except (UnicodeDecodeError, LookupError):
                continue
        # Nothing could read it. A replaced byte still beats a lost row.
        return "\ufffd" * len(raw), error.end

    codecs.register_error(name, handle)
    _HANDLERS[name] = True
    return name


def lines(path, encodings=DEFAULT_ENCODINGS):
    """Yield decoded lines, choosing an encoding a line at a time.

    Per line, not per file, because these files are concatenations of
    several days' collection and the encoding changes partway through more
    than one of them.
    """
    with open(path, "rb") as handle:
        for raw in handle:
            yield decode(raw, encodings)
