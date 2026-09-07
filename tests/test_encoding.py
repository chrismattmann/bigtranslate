"""Decoding a corpus that is not all UTF-8.

The employment TSVs were collected in 2012 from sites that did not agree on
an encoding. The replacement pipeline hardcoded ``decode("utf-8", "replace")``,
which never raises and never warns, so every latin-1 accent became U+FFFD on
the way to Solr -- a quarter of the indexed documents carried a damaged
``location``, the field the map and the geocoder read.
"""

import importlib.util
import os
import sys

import pytest

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "distribution", "src", "main", "resources", "bin")
sys.path.insert(0, BIN)
import bt_encoding  # noqa: E402


# "Bolívar" as the corpus actually stores it: latin-1, invalid as UTF-8.
BOLIVAR_LATIN1 = b"Cartagena, Bol\xedvar, Colombia"


class TestDecode:

    def test_latin_1_survives_instead_of_becoming_a_replacement_char(self):
        got = bt_encoding.decode(BOLIVAR_LATIN1)
        assert got == "Cartagena, Bolívar, Colombia"
        assert "�" not in got

    def test_utf_8_is_preferred_when_both_would_decode(self):
        # latin-1 accepts any byte sequence, so order is what makes this
        # UTF-8 rather than mojibake.
        assert bt_encoding.decode("Bolívar".encode("utf-8")) == "Bolívar"

    def test_an_undecodable_byte_still_yields_a_row(self):
        # Only reachable when the list has no total codec; a lost row is
        # worse than a replaced byte.
        got = bt_encoding.decode(b"\xff\xfe bad", ["utf-8"])
        assert "bad" in got

    def test_str_passes_through(self):
        assert bt_encoding.decode("already text") == "already text"

    def test_valid_utf_8_is_not_mojibaked_to_rescue_one_stray_byte(self):
        # The bug this nearly shipped with. Most lines in this corpus are
        # valid UTF-8 carrying one stray latin-1 byte somewhere. Falling back
        # a line at a time re-reads the whole line as latin-1, so every
        # accent that was already correct comes back as mojibake -- strictly
        # worse than the U+FFFD it was meant to fix.
        mixed = "Bogotá".encode("utf-8") + b" Bol\xedvar"
        got = bt_encoding.decode(mixed)
        assert got == "Bogotá Bolívar", got
        assert "Ã" not in got

    def test_only_the_rejected_run_falls_back(self):
        good = "café".encode("utf-8")
        assert bt_encoding.decode(good + b"\xed" + good) == "café" + "í" + "café"

    def test_an_unknown_codec_name_is_skipped_not_fatal(self):
        assert bt_encoding.decode(BOLIVAR_LATIN1,
                                  ["no-such-codec", "latin-1"]).endswith("Colombia")


class TestReadEncodings:

    def test_reads_the_file_the_original_pipeline_used(self, tmp_path):
        f = tmp_path / "encoding.txt"
        f.write_text("utf-8\n# a comment\n\nus-ascii\nlatin-1\n")
        assert bt_encoding.read_encodings(str(f)) == ["utf-8", "us-ascii", "latin-1"]

    def test_a_missing_file_keeps_the_fallback_chain(self, tmp_path):
        # Not bare utf-8: a corpus that needed the chain does not stop
        # needing it because a config file went missing.
        got = bt_encoding.read_encodings(str(tmp_path / "absent.txt"))
        assert "latin-1" in got

    def test_an_empty_file_keeps_the_fallback_chain(self, tmp_path):
        f = tmp_path / "encoding.txt"
        f.write_text("\n# only comments\n")
        assert "latin-1" in bt_encoding.read_encodings(str(f))


class TestLines:

    def test_encoding_is_chosen_per_line_not_per_file(self, tmp_path):
        # These files are concatenations of several days' collection, and
        # more than one changes encoding partway through.
        f = tmp_path / "mixed.tsv"
        f.write_bytes("Bogotá\n".encode("utf-8") + "Bolívar\n".encode("latin-1"))
        assert [l.strip() for l in bt_encoding.lines(str(f))] == ["Bogotá", "Bolívar"]

    def test_no_replacement_chars_on_the_shipped_chain(self, tmp_path):
        f = tmp_path / "mixed.tsv"
        f.write_bytes(BOLIVAR_LATIN1 + b"\n")
        assert "�" not in "".join(bt_encoding.lines(str(f)))


class TestTheShippedConfig:

    def test_the_shipped_encoding_txt_ends_in_a_total_codec(self):
        # latin-1 accepts any byte, so it must come last: anything after it
        # is dead, and without it undecodable rows fall back to replacement.
        conf = os.path.join(os.path.dirname(BIN), "conf", "encoding.txt")
        names = bt_encoding.read_encodings(conf)
        assert names[-1] == "latin-1", names
        assert names[0] == "utf-8", names
