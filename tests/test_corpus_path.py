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
"""The corpus path is checked before anything is started.

A path is pasted, and a pasted path picks things up: a comma from a list, a
stray quote, a "~" that never expanded because it was quoted. DRAT accepted
one of those and reported a running audit over a directory that did not
exist -- catalog cleared, crawl found nothing, and the first sign of trouble
was a zero where a count should have been. Refusing costs a second.
"""
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DRIVER = REPO / "distribution" / "src" / "main" / "resources" / "bin" / "bigtranslate"


def run_validation(argument):
    """Call validate_corpus_path on its own, out of the driver script."""
    body = subprocess.run(
        ["sed", "-n", "/^validate_corpus_path() {/,/^}/p", str(DRIVER)],
        capture_output=True, text=True, check=True).stdout
    assert body.strip(), "validate_corpus_path is not in the driver script"
    script = body + '\nvalidate_corpus_path "$1"\necho "RESOLVED=$CORPUS_PATH"\n'
    return subprocess.run(["bash", "-c", script, "bash", argument],
                          capture_output=True, text=True)


@pytest.fixture
def corpus(tmp_path):
    (tmp_path / "one.tsv").write_text("a\tb\n")
    (tmp_path / "two.tsv").write_text("c\td\n")
    return tmp_path


def test_a_directory_of_tsv_is_accepted_and_resolved(corpus):
    done = run_validation(str(corpus))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "RESOLVED=" in done.stdout
    assert "2 TSV file(s)" in done.stdout


def test_a_trailing_comma_is_refused(corpus):
    """The one that actually happened."""
    done = run_validation(str(corpus) + ",")
    assert done.returncode != 0
    assert "ends in ','" in done.stdout
    assert "pasted" in done.stdout, "does not say what probably went wrong"


@pytest.mark.parametrize("junk", ['"', "'", ";", "|", "&"])
def test_other_pasted_punctuation_is_refused(corpus, junk):
    done = run_validation(str(corpus) + junk)
    assert done.returncode != 0, "accepted a path ending in %r" % junk


def test_a_path_that_is_not_there_is_refused(tmp_path):
    done = run_validation(str(tmp_path / "nope"))
    assert done.returncode != 0
    assert "nothing at" in done.stdout


def test_a_file_is_refused_with_the_right_advice(corpus):
    done = run_validation(str(corpus / "one.tsv"))
    assert done.returncode != 0
    assert "is a file, not a directory" in done.stdout


def test_an_empty_directory_is_refused(tmp_path):
    """A crawl of nothing finishes instantly and reads exactly like success."""
    done = run_validation(str(tmp_path))
    assert done.returncode != 0
    assert "No .tsv files" in done.stdout


def test_an_unexpanded_tilde_is_refused():
    done = run_validation("~/bigtranslate/input")
    assert done.returncode != 0
    assert "literal ~" in done.stdout


def test_nothing_at_all_is_refused():
    done = run_validation("")
    assert done.returncode != 0
    assert "No path given" in done.stdout


def test_translate_validates_before_it_marks_a_run():
    """Order matters: marking first would leave a marker for a run that never
    started, and Gloss would report it as running for ever."""
    text = DRIVER.read_text()
    validate_at = text.index("validate_corpus_path \"$PRODUCT_PATH\"")
    mark_at = text.index('mark_run "TRANSLATING"')
    assert validate_at < mark_at, (
        "the run is marked before the path is checked")


def test_the_service_runs_as_many_at_once_as_there_are_workers():
    """One at a time is the default, and it is the wrong answer here: eight
    workers sharing one translation queue behind each other, which measured
    slower than loading the model separately in every worker."""
    oodt = (REPO / "distribution" / "src" / "main" / "resources" / "bin" / "oodt").read_text()
    assert "--max-concurrency" in oodt
    assert "minPoolSize" in oodt, (
        "concurrency is not derived from the engine's pool size, so the two "
        "can drift apart")


def test_the_device_is_configurable():
    oodt = (REPO / "distribution" / "src" / "main" / "resources" / "bin" / "oodt").read_text()
    setenv = (REPO / "distribution" / "src" / "main" / "resources" / "bin" / "setenv.sh").read_text()
    assert "--device" in oodt
    assert "PANTOGLOSS_DEVICE" in setenv
    assert "PANTOGLOSS_DEVICE:-auto}" in setenv, "the default is not auto"


def test_translate_waits_for_the_workflow_and_clears_the_marker():
    """The crawl ending is not the run ending.

    Translating happens in the workflow manager after the crawl returns.
    Marking the run and walking away left the marker behind for good: every
    instance finished and Gloss went on reporting TRANSLATING, because the
    only thing that could have said otherwise had exited.
    """
    text = DRIVER.read_text()
    assert "wait_for_workflow" in text, (
        "translate does not wait for the workflow it started")
    wait_at = text.index("    wait_for_workflow")
    unmark_at = text.index("    unmark_run", wait_at)
    assert wait_at < unmark_at, "the marker is cleared before the run is over"


def test_the_wait_needs_two_quiet_passes():
    """Instances appear as splits are made, so there is a moment early on with
    none running and more still to come. Ending there reports success in the
    middle of the run."""
    text = DRIVER.read_text()
    import re
    assert re.search(r'quiet"?\s+-ge\s+2', text), (
        "a single quiet poll ends the wait")


SETUP = (REPO / "distribution" / "src" / "main" / "resources"
         / "bin" / "bigtranslate-setup")


def test_setup_asks_for_the_gpu_extra_this_machine_can_use():
    """Without the right extra TensorFlow sees no GPU, so --device auto has
    nothing to choose and everything runs on the CPU -- invisibly, unless
    somebody reads /info and notices the backend.

    Two extras exist and they are not interchangeable: [metal] needs Apple
    silicon, [cuda] needs Linux and a card.
    """
    text = SETUP.read_text()
    assert "metal" in text, "the Metal extra is never installed"
    assert "arm64" in text, "Metal is not conditioned on Apple silicon"
    assert "cuda" in text, "the CUDA extra is never installed"
    assert "nvidia-smi" in text, (
        "CUDA is installed without checking there is a card for it, which "
        "pulls a large stack onto machines that cannot use it")


def test_the_gpu_extra_can_be_overridden():
    """For a machine the guess gets wrong."""
    assert "PANTOGLOSS_EXTRAS" in SETUP.read_text()


def test_setup_reports_whether_a_gpu_will_actually_be_used():
    """Asked of TensorFlow rather than inferred from what was installed: a
    CPU-only deployment otherwise looks identical to a GPU one."""
    text = SETUP.read_text()
    assert "list_physical_devices" in text, (
        "the GPU is inferred from the install rather than confirmed")
    assert "NONE visible" in text, "a CPU-only deployment says nothing"


OODT = REPO / "distribution" / "src" / "main" / "resources" / "bin" / "oodt"


def test_the_translation_service_is_part_of_the_lifecycle():
    """It starts, stops and bounces with everything else."""
    text = OODT.read_text()
    assert "start_pantogloss" in text and "stop_pantogloss" in text
    # restart goes through both, so a bounce actually bounces it.
    restart_at = text.index('elif [ "$1" = "restart" ]')
    after = text[restart_at:]
    assert "stop_oodt" in after and "start_oodt" in after
    start_body = text[text.index("start_oodt() {"):text.index("stop_oodt() {")]
    stop_body = text[text.index("stop_oodt() {"):restart_at]
    assert "start_pantogloss" in start_body, "start does not start the service"
    assert "stop_pantogloss" in stop_body, "stop does not stop the service"


def test_the_service_pid_is_findable_without_the_pid_file():
    """A service can outlive its pid file, and a pid file can outlive its
    service. Either way start and stop have to agree with what is running."""
    text = OODT.read_text()
    assert "pantogloss_pid()" in text
    assert "lsof -ti tcp" in text, (
        "the pid can only come from the file, so a service started any other "
        "way cannot be stopped")
    assert "kill -0" in text, "a stale pid file is never detected"


def test_a_stale_pid_file_is_cleared_rather_than_believed():
    text = OODT.read_text()
    body = text[text.index("pantogloss_pid()"):text.index("start_pantogloss()")]
    assert 'rm -f "$PANTOGLOSS_PID"' in body


def test_stop_says_when_the_port_belongs_to_someone_else():
    """It used to wait out its timeout in silence."""
    body = OODT.read_text()
    stop_body = body[body.index("stop_pantogloss() {"):body.index('if [ "$1" = "start" ]')]
    assert "did not start" in stop_body, (
        "stop says nothing about a port held by a foreign process")


def test_only_our_own_service_is_ever_killed():
    """The same rule start follows: a port we do not own is not ours to stop."""
    body = OODT.read_text()
    finder = body[body.index("pantogloss_pid()"):body.index("start_pantogloss()")]
    assert ".venv/bin/pantogloss" in finder, (
        "any process on the port would be adopted, and killed")


def test_starting_twice_does_not_start_two():
    body = OODT.read_text()
    start_body = body[body.index("start_pantogloss() {"):body.index("stop_pantogloss() {")]
    assert "already running" in start_body


def test_metal_gets_one_inference_slot_whatever_the_pool_says():
    """Eight simultaneous translate() calls share one Keras model and one
    Metal execution context, and MPSGraph asserts on the mismatched shapes --
    "Placeholder shape mismatches" -- which aborts the process mid-run.

    The workers still submit concurrently; they queue inside the service. On
    CPU and CUDA there is no such limit, so concurrency follows the pool: one
    slot there would serialise every worker behind it for no reason.
    """
    body = OODT.read_text()
    fn = body[body.index("pantogloss_concurrency()"):body.index("start_pantogloss()")]
    assert "arm64" in fn, "the Metal case is not distinguished"
    # Asked of TensorFlow rather than of the import system: tensorflow-metal
    # is a PluggableDevice, not a module, so "import tensorflow_metal" fails
    # on a machine where the GPU is present and working -- which silently
    # started the service with eight slots, the setting that crashes it.
    assert "list_physical_devices" in fn, (
        "Metal is detected by importing a module that does not exist")
    # The executed form, not the phrase: the comment above the check explains
    # this failure and would otherwise trip the test that guards it.
    executed = [line for line in fn.splitlines()
                if "import tensorflow_metal" in line
                and not line.strip().startswith("#")]
    assert executed == [], (
        "tensorflow-metal is a PluggableDevice; importing it always fails: %s"
        % executed)
    assert "minPoolSize" in fn, "the non-Metal case does not follow the pool"
    assert "echo 1" in fn, "Metal is not held to a single inference slot"


def test_the_concurrency_can_still_be_overridden():
    body = OODT.read_text()
    fn = body[body.index("pantogloss_concurrency()"):body.index("start_pantogloss()")]
    assert "PANTOGLOSS_CONCURRENCY" in fn


def test_the_device_default_stays_auto():
    """Not cpu. Metal is healthy; it was the concurrency that was wrong, and
    defaulting to the CPU would throw the GPU away to dodge a bug that only
    appears with simultaneous inference."""
    setenv = (REPO / "distribution" / "src" / "main" / "resources"
              / "bin" / "setenv.sh").read_text()
    assert "PANTOGLOSS_DEVICE:-auto}" in setenv


def test_start_creates_the_directories_the_services_need():
    """Empty directories do not survive the tarball.

    A freshly unpacked distribution has no tomcat/logs, and Tomcat does not
    report that in any log -- catalina.sh fails at "touch .../catalina.out:
    No such file or directory" and exits, leaving nothing listening and no
    catalina.out to read. The first sign is a webapp that is simply absent.
    """
    body = OODT.read_text()
    assert "ensure_working_dirs" in body
    fn = body[body.index("ensure_working_dirs() {"):body.index("start_oodt() {")]
    for needed in ("tomcat/logs", "tomcat/work", "data/jobs"):
        assert needed in fn, "%s is not created before start" % needed
    start_body = body[body.index("start_oodt() {"):body.index("stop_oodt() {")]
    assert "ensure_working_dirs" in start_body, "start does not call it"


def test_the_log_gloss_shows_says_what_is_happening():
    """It used to hold nothing but pushd and popd output.

    Gloss shows the tail of this file under "In progress", so a reader
    watching a forty minute run saw two lines of shell bookkeeping --
    "~/bt-w1/crawler/bin ~/bt-w1" -- and nothing about the run.
    """
    text = DRIVER.read_text()
    assert "say()" in text, "there is no way to write progress to the log"

    # The directory stack is no longer redirected into it.
    polluting = [line for line in text.splitlines()
                 if ("pushd" in line or "popd" in line)
                 and "bigtranslate.log" in line
                 and not line.strip().startswith("#")]
    assert polluting == [], (
        "pushd/popd still write the directory stack into the log: %s"
        % polluting)

    for milestone in ("Crawling", "Crawl finished", "Translating:"):
        assert milestone in text, "the log never says %r" % milestone


def test_progress_is_not_written_on_every_poll():
    """The pane shows a tail; a line every fifteen seconds pushes everything
    else off it."""
    text = DRIVER.read_text()
    assert "waited % 120" in text, "progress is logged every poll"
