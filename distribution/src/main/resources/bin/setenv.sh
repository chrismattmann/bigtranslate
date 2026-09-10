########  setenv.sh ########
#
# Set project specific configuration in setenv.sh
#
# Example:
# 		- Change filemgr URL to http://locatlhost:1234
#			FILEMGR_URL=http://locatlhost:1234
#
#		- Set custom job directory
#			PROJECT_JOB_DIR=/usr/local/project/data/jobs
#
############################

# Where this deployment is, worked out from where this file is rather than
# assumed. The default used to be /usr/local/bigtranslate, so a deployment
# unpacked anywhere else worked only if the caller had exported
# BIGTRANSLATE_HOME first. The servers are always started through bin/oodt,
# which does that, so the gap showed up only in the client scripts:
#
#   ./filemgr-client --url ... --operation --getNumProducts
#   cd: /usr/local/bigtranslate/filemgr/bin: No such file or directory
#   ClassNotFoundException: ...FileManagerClientMain
#
# which reads like a broken install rather than an unset variable.
if [ -z "${BIGTRANSLATE_HOME:-}" ]; then
  # ${BASH_SOURCE[0]} when sourced under bash, $0 otherwise. Written without
  # the subscript because that is array syntax, and a POSIX shell does not
  # parse it: dash rejects ${BASH_SOURCE[0]} outright with
  #
  #   ./bin/oodt: 27: bin/setenv.sh: Bad substitution
  #
  # which killed every /bin/sh script that sourced this file. Invisible on
  # macOS, where /bin/sh is bash, and fatal on Linux, where it is dash -- so
  # bin/oodt worked on the manager and failed on the compute nodes. Bare
  # $BASH_SOURCE is element zero under bash and an ordinary unset variable
  # anywhere else, which is exactly the fallback wanted.
  if [ -n "${BASH_SOURCE:-}" ]; then
    _bt_setenv="$BASH_SOURCE"
  else
    _bt_setenv="$0"
  fi
  _bt_bin=$(cd "$(dirname "$_bt_setenv")" 2>/dev/null && pwd)
  if [ -n "$_bt_bin" ]; then
    BIGTRANSLATE_HOME=$(cd "$_bt_bin/.." 2>/dev/null && pwd)
  fi
  unset _bt_setenv _bt_bin
fi
export BIGTRANSLATE_HOME=${BIGTRANSLATE_HOME:-/usr/local/bigtranslate}

# What differs between one install and the next.
#
# Ports, and the address other machines reach the managers at, are
# properties of a deployment and have no business being edited into a file
# the distribution ships. Editing this one is how the deployment on the
# manager came to differ from the repository by thirty six lines: it had
# gained a block setting the ports and rewriting the service urls, and lost
# the POSIX $BASH_SOURCE fix above -- invisible on macOS, fatal on a Linux
# compute node. Nothing reported the difference, because a hand edited copy
# of a tracked file is not something any check was looking for.
#
# Read before the defaults below, every one of which is ${VAR:-...}, so a
# value set here wins without the file having to repeat anything. Setting
# the ports and BIGTRANSLATE_HOST is enough: the urls are worked out from
# them once, here, rather than in two places that can disagree. They did
# disagree, and the copy that was not this one pointed SOLR_URL somewhere
# Solr does not listen.
if [ -f "$BIGTRANSLATE_HOME/conf/site.sh" ]; then
  . "$BIGTRANSLATE_HOME/conf/site.sh"
fi

# Ports first, urls derived from them. The launchers bind FILEMGR_PORT and its
# siblings while everything else looks up the urls, so setting only the urls
# left each service listening on the default and every client looking
# elsewhere. Setting a port here moves both.
#
# A machine running more than one OODT stack needs these to differ: the
# defaults below are what DRAT and a stock RADiX deployment also use, and two
# stacks on the same port do not fail loudly -- the second one's clients talk
# to the first one's services.
export FILEMGR_PORT=${FILEMGR_PORT:-9000}
export WORKFLOW_PORT=${WORKFLOW_PORT:-9001}
export RESMGR_PORT=${RESMGR_PORT:-9002}
export SOLR_PORT=${SOLR_PORT:-8983}
export TOMCAT_PORT=${TOMCAT_PORT:-8080}

# The address the managers are reached at. Loopback is right for a single
# machine install and wrong the moment a task runs anywhere else: the
# Workflow Manager substitutes these urls into task metadata, and on a
# compute node "localhost" is that node's own machine --
#
#   ConnectionException: Exception connecting to filemgr: [http://localhost:9200]
#
# on a task that ran perfectly on the manager. The managers bind *:port, so
# the manager's own LAN address works locally too, which is why one value
# serves both machines.
export BIGTRANSLATE_HOST=${BIGTRANSLATE_HOST:-localhost}

export FILEMGR_URL=http://$BIGTRANSLATE_HOST:$FILEMGR_PORT
export WORKFLOW_URL=http://$BIGTRANSLATE_HOST:$WORKFLOW_PORT
export RESMGR_URL=http://$BIGTRANSLATE_HOST:$RESMGR_PORT

# The core url rather than the base. Gloss reads SOLR_URL as the collection it
# queries and derives the base from it, so a base url here sends every Gloss
# query to /solr/select and it reports no documents while Solr fills up.
#
# Localhost even when the managers are on a LAN address, which is the one
# exception and needs saying because the obvious edit is to make it match
# its neighbours. Solr binds loopback unless told otherwise, and nothing
# off this machine reads it: the join runs on the managers queue, which
# only the manager's own node serves, and Gloss runs in the manager's
# Tomcat. Pointed at the LAN address it left Solr up, its core healthy and
# every page green, with the join three hours away from failing on
# connection refused.
export SOLR_URL=http://localhost:$SOLR_PORT/solr/bigtranslate

# The translation service. One resident model for the whole deployment
# instead of a fresh load in every split's process -- about thirty seconds
# each, and a ten-file run does it dozens of times.
#
# 8765 is Pantogloss's own default and is an ordinary enough port to be
# somebody else's; move it here if it is.
export PANTOGLOSS_PORT=${PANTOGLOSS_PORT:-8765}
export PANTOGLOSS_URL=${PANTOGLOSS_URL:-http://127.0.0.1:$PANTOGLOSS_PORT}

# How many translations the service will do at once.
#
# This has to match the number of splits the workflow engine runs at once,
# and it is not a free choice: pantogloss serve defaults to one, so eight
# workers sharing it queue behind a single translation. Measured on the ten
# file corpus that spent 1,885 seconds queued against 347 seconds actually
# translating -- slower than loading the model separately in every worker,
# which is the thing the service exists to avoid.
#
# Left unset it is read from the engine's own pool size below, so the two
# cannot drift apart.
export PANTOGLOSS_CONCURRENCY=${PANTOGLOSS_CONCURRENCY:-}

# Which device the model runs on. "auto" prefers the GPU -- Metal here, CUDA
# on Linux -- and falls back to the CPU when there is none. Set "cpu" to keep
# the GPU free for something else.
export PANTOGLOSS_DEVICE=${PANTOGLOSS_DEVICE:-auto}

# How long a translation may wait for an inference slot. Empty takes the
# deployment's own default, which allows for a full queue draining through a
# single slot; the service's thirty second default assumes a slot per caller.
export PANTOGLOSS_QUEUE_TIMEOUT=${PANTOGLOSS_QUEUE_TIMEOUT:-}

# How long the server collects arriving translations before running them
# through the model together, and how large the combined call may get.
#
# Ten milliseconds is Pantogloss's own default and costs a lightly loaded
# caller almost nothing. It buys less than it looks like it should here: the
# PGE already sends thirty-two strings per request and a combined call holds
# sixty-four, so at most two of our requests ever merge. A longer window
# fills those pairs more reliably at the price of latency on a quiet queue.
# Ignored by servers older than 0.19, which have no such flag.
# The corpus, read in place. The extract and join stages are pointed at
# this; nothing copies it, because a single pass over 38GB takes minutes
# and copying it takes a volume.
export BIGTRANSLATE_CORPUS=${BIGTRANSLATE_CORPUS:-$BIGTRANSLATE_HOME/data/corpus}

# Running the translate stage across more than one machine.
#
# "resource" hands each task to the resource manager, which gives it to a
# node with capacity in the task's queue; "local" runs it in a thread here
# and needs none of the rest of this. Local is the default because a single
# machine install should not have to know what a batch stub is.
export WORKFLOW_RUNNER=${WORKFLOW_RUNNER:-local}

# The nodes, as the resource manager addresses them. Each runs bin/bt-node,
# which is a batch stub plus the translation service that stub's tasks will
# use. The stub instantiates the workflow task itself, so a node needs the
# same deployment as this machine, not just the stub.
export BIGTRANSLATE_NODE_PORT=${BIGTRANSLATE_NODE_PORT:-2001}
export BIGTRANSLATE_NODE_URL=${BIGTRANSLATE_NODE_URL:-http://localhost:$BIGTRANSLATE_NODE_PORT}
export BIGTRANSLATE_NODE2_URL=${BIGTRANSLATE_NODE2_URL:-$BIGTRANSLATE_NODE_URL}

# How much heap Solr gets.
#
# Solr's own default is 512m, which is ample for the tens of thousands of
# documents a test run posts and is not what this corpus asks for: the
# employment set indexes 119,453,210 documents into an 88GB index, and the
# merging that goes with it is where a small heap stops being survivable.
# Two gigabytes carried a two million document benchmark comfortably; four
# is the number to start a full run with.
export SOLR_HEAP=${SOLR_HEAP:-4g}

# Where the index goes, if not under the deployment. An 88GB index does
# not have to live beside the code.
#
# This is a data *root*, not the index directory: Solr is told through
# solr.data.home, and the security policy it runs under grants that path
# and its children by name. Naming a subdirectory of the volume instead
# fails, because Solr reads the parent on the way in and the parent is not
# what was granted -- "access denied (FilePermission /Volumes/X read)"
# while pointed at /Volumes/X/something. Give it the root.
#
# The volume needs real filesystem semantics. exFAT has no hard links, no
# journalling and is case-insensitive; Lucene wants all three, and the
# failure mode is a corrupt index after a crash rather than an error at
# startup. A disk image formatted APFS or HFS+ on that volume is fine.
export SOLR_DATA_DIR=${SOLR_DATA_DIR:-}

export PANTOGLOSS_BATCH_WAIT_MS=${PANTOGLOSS_BATCH_WAIT_MS:-10}
export PANTOGLOSS_COALESCED_BATCH=${PANTOGLOSS_COALESCED_BATCH:-64}
export PANTOGLOSS_COALESCED_CHARS=${PANTOGLOSS_COALESCED_CHARS:-200000}
export FILEMGR_HOME=$BIGTRANSLATE_HOME/filemgr
export PGE_HOME=$BIGTRANSLATE_HOME/pge
export PCS_HOME=$BIGTRANSLATE_HOME/pcs
export FMPROD_HOME=$BIGTRANSLATE_HOME/tomcat/webapps/fmprod/WEB-INF/classes/

# Crawler precondition beans reference this placeholder, so it must be set
# even when it is empty. The bigtranslate wrapper exports it per run;
# without a default here, invoking crawler_launcher directly (as the build
# docs describe) fails Spring context creation.
export BIGTRANSLATE_EXCLUDE=${BIGTRANSLATE_EXCLUDE:-}
# Translation runs locally through Pantogloss; the Tika translation server
# and its API credentials are no longer part of this pipeline.

# Bound every Avro client call (Mnemosyne #197). Ten minutes is the code
# default; 0 waits forever. JDK_JAVA_OPTIONS reaches File Manager, Workflow
# Manager, Resource Manager, and Tomcat.
#
# It has to outlive the longest task, because the Resource Manager dispatches
# a job by making a blocking call that does not return until the job is done.
# At the ten minute default a translation that takes forty minutes on CPU
# produced, every ten minutes, for every running job:
#
#   SEVERE: Job execution failed for jobId '...' : No response to executeJob
#   within 600000ms; abandoning the call.
#
# and abandoning the call is not abandoning the work. The job kept running on
# the node; the batch manager recorded it as failed and, in the same finally
# block, gave the node's capacity back. The scheduler then started another job
# on a node it believed was free. Repeating every ten minutes, one machine
# reached thirty concurrent translations against a capacity of eight, while
# the GPU node -- which finishes inside ten minutes and so never timed out --
# sat at exactly eight. Jobs that completed perfectly were recorded as
# failures, which is why instance state and actual output disagreed.
#
# Four hours covers a CPU chunk and a join with room to spare. The timeout is
# a backstop against a node that has genuinely gone away, not a task deadline,
# so it should be far longer than any task rather than close to one.
AVRO_CLIENT_TIMEOUT_MS=${AVRO_CLIENT_TIMEOUT_MS:-14400000}
export JDK_JAVA_OPTIONS="${JDK_JAVA_OPTIONS:+$JDK_JAVA_OPTIONS }-Dorg.apache.oodt.avro.client.requestTimeoutMillis=${AVRO_CLIENT_TIMEOUT_MS}"
