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

export BIGTRANSLATE_HOME=${BIGTRANSLATE_HOME:-/usr/local/bigtranslate}
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

export FILEMGR_URL=http://localhost:$FILEMGR_PORT
export WORKFLOW_URL=http://localhost:$WORKFLOW_PORT
export RESMGR_URL=http://localhost:$RESMGR_PORT

# The core url rather than the base. Gloss reads SOLR_URL as the collection it
# queries and derives the base from it, so a base url here sends every Gloss
# query to /solr/select and it reports no documents while Solr fills up.
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
# Running the translate stage across more than one machine.
#
# "resource" hands each task to the resource manager, which gives it to a
# node with capacity in the task's queue; "local" runs it in a thread here
# and needs none of the rest of this. Local is the default because a single
# machine install should not have to know what a batch stub is.
# The corpus, read in place. The extract and join stages are pointed at
# this; nothing copies it, because a single pass over 38GB takes minutes
# and copying it takes a volume.
export BIGTRANSLATE_CORPUS=${BIGTRANSLATE_CORPUS:-$BIGTRANSLATE_HOME/data/corpus}

export WORKFLOW_RUNNER=${WORKFLOW_RUNNER:-local}

# The nodes, as the resource manager addresses them. Each runs bin/bt-node,
# which is a batch stub plus the translation service that stub's tasks will
# use. The stub instantiates the workflow task itself, so a node needs the
# same deployment as this machine, not just the stub.
export BIGTRANSLATE_NODE_PORT=${BIGTRANSLATE_NODE_PORT:-2001}
export BIGTRANSLATE_NODE_URL=${BIGTRANSLATE_NODE_URL:-http://localhost:$BIGTRANSLATE_NODE_PORT}
export BIGTRANSLATE_NODE2_URL=${BIGTRANSLATE_NODE2_URL:-$BIGTRANSLATE_NODE_URL}

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
AVRO_CLIENT_TIMEOUT_MS=${AVRO_CLIENT_TIMEOUT_MS:-600000}
export JDK_JAVA_OPTIONS="${JDK_JAVA_OPTIONS:+$JDK_JAVA_OPTIONS }-Dorg.apache.oodt.avro.client.requestTimeoutMillis=${AVRO_CLIENT_TIMEOUT_MS}"
