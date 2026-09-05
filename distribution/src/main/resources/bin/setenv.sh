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
