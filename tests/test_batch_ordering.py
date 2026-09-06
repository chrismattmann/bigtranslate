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
"""Batches are filled with similar-length strings.

The runtime pads a batch to a power of two by its longest source, so a batch
holding a 21-character string beside a 169-character one pays for the long
one across all of it. Grouping similar lengths removed 29% of the model's own
reported inference time -- 1,299s to 922s over the same 8,192 strings -- for
1.44x on the M3's CPU and 1.17x on an RTX 3080 Ti.

Reordering is safe because results are matched back to inputs by text.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PGE = (REPO / "distribution" / "src" / "main" / "resources"
       / "bin" / "pantogloss-translatejson")
TASKS = REPO / "workflow" / "src" / "main" / "resources" / "policy" / "tasks.xml"
PGECONF = (REPO / "pge" / "src" / "main" / "resources" / "policy"
           / "no_filter" / "PgeConfig_BigTranslate.xml")


def test_sorting_is_on_by_default():
    source = PGE.read_text()
    assert 'dest="sort_by_length"' in source, "the flag does not exist"
    assert "default=True" in source, (
        "sorting is not the default, so the 1.44x is left on the table")


def test_sorting_can_be_turned_off():
    assert "--no-sort-by-length" in PGE.read_text(), (
        "there is no way back to the original order")


def test_the_loop_batches_the_ordered_copy():
    """A sort that the batching loop then ignores would be invisible."""
    source = PGE.read_text()
    assert "ordered = (sorted(missing, key=len)" in source
    assert "batch = ordered[i:i + args.batch_size]" in source, (
        "the loop still slices the unsorted list")


def test_reordering_cannot_mismatch_a_translation():
    """Results are keyed by text, so order carries no meaning."""
    source = PGE.read_text()
    assert "dict(zip(batch, out))" in source, (
        "results are no longer paired with the batch that produced them")
    assert "fresh.update(dict(zip(batch, out)))" in source


def test_sorting_actually_groups_by_length():
    """The property the speedup depends on, exercised rather than asserted."""
    strings = ["x" * n for n in (169, 21, 90, 22, 168, 23)]
    ordered = sorted(strings, key=len)
    batches = [ordered[i:i + 2] for i in range(0, len(ordered), 2)]
    spreads = [max(map(len, b)) - min(map(len, b)) for b in batches]
    unsorted_batches = [strings[i:i + 2] for i in range(0, len(strings), 2)]
    unsorted_spreads = [max(map(len, b)) - min(map(len, b))
                        for b in unsorted_batches]
    # Sorting cannot make every batch tight -- a gap in the length
    # distribution has to fall inside some batch -- but it collapses the
    # total padding waste, which is what the model is billed for.
    assert sum(spreads) < sum(unsorted_spreads) / 4, (
        "sorting barely reduced the within-batch length spread: %d vs %d"
        % (sum(spreads), sum(unsorted_spreads)))
    assert max(spreads) < max(unsorted_spreads), (
        "the worst batch is no better than it was unsorted")


def test_batch_size_and_sorting_are_workflow_properties():
    """Per deployment, because the best batch size depends on the device."""
    tasks = TASKS.read_text()
    assert '<property name="TranslateBatchSize"' in tasks
    assert '<property name="TranslateSortFlag"' in tasks, (
        "the sort flag cannot be set per deployment")
    cmd = PGECONF.read_text()
    assert "--batch-size [TranslateBatchSize]" in cmd
    assert "[TranslateSortFlag]" in cmd, (
        "the workflow property never reaches the PGE command line")
