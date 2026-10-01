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
"""A path with brackets in it is a placeholder nobody substituted.

PathUtils leaves an unset [Name] in a PgeConfig as the literal text, so

    <cmd>mkdir -p "[JobOutputDir]"</cmd>

run without that key in the metadata creates a directory called
"[JobOutputDir]" in whatever directory the command ran from. Run the join by
hand inside a clone to test it and "git add -A" commits the result.

That is how [JobOutputDir]/join.done reached master on 2026-09-28, in the commit
that fixed the join's shard loop, and sat in the tree for three days before
anybody noticed. bin/bt-join-index has guarded its own arguments against the
same pattern since the run that followed, which catches it at execution time;
this catches the artefact that gets committed.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The same shape bin/bt-join-index refuses at runtime: a bracketed name that
# looks like a PathUtils key, rather than any bracket at all. A file genuinely
# named "[2026] notes.txt" is somebody's choice; "[JobOutputDir]" is a bug.
PLACEHOLDER = re.compile(r"\[[A-Za-z][A-Za-z0-9_]*\]")


def tracked_paths():
    """Every path git knows about, or None when this is not a checkout."""
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=str(ROOT),
                             capture_output=True)
    except OSError:
        return None
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


def placeholders_in(paths):
    return [p for p in paths if PLACEHOLDER.search(p)]


class TestTheMatcherWorks:
    """Proved against known input, so the real check below cannot pass empty."""

    def test_it_finds_the_one_that_got_through(self):
        assert placeholders_in(["[JobOutputDir]/join.done"]) == [
            "[JobOutputDir]/join.done"]

    def test_it_finds_a_placeholder_at_any_depth(self):
        found = placeholders_in([
            "data/[JobLogDir]/extract.log",
            "pge/policy/[ChunkFile]",
        ])
        assert len(found) == 2

    def test_it_leaves_ordinary_paths_alone(self):
        assert placeholders_in([
            "distribution/src/main/resources/bin/bt-join-index",
            "pge/src/main/resources/policy/no_filter/PgeConfig_JoinIndex.xml",
            "tests/test_the_join_gets_the_corpus.py",
        ]) == []

    def test_a_deliberate_bracket_is_not_a_placeholder(self):
        # Brackets that are not a PathUtils key: a year, a space inside, a
        # leading digit. Refusing these would make the check something people
        # route around.
        assert placeholders_in([
            "notes/[2026] plan.md",
            "docs/[draft notes].md",
        ]) == []


class TestTheTreeIsClean:

    def test_no_tracked_path_holds_an_unsubstituted_placeholder(self):
        paths = tracked_paths()
        if paths is None:
            return  # not a git checkout; nothing to assert about
        assert paths, "git ls-files returned nothing, so this proved nothing"
        found = placeholders_in(paths)
        assert not found, (
            "these tracked paths are unsubstituted PathUtils keys, not "
            "filenames anybody chose: %s. Something ran a PgeConfig command "
            "inside the repository without that key set, and git add -A "
            "committed the result." % found)

    def test_gitignore_keeps_them_out(self):
        """So the next one is never offered to git in the first place."""
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "\\[*\\]/" in text, (
            "the .gitignore rule for bracketed directories is gone; a bracket "
            "is a character class in gitignore, so it has to be escaped")
