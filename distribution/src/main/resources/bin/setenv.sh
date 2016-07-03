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

export BIGTRANSLATE_HOME=/usr/local/bigtranslate
export FILEMGR_URL=http://localhost:9000
export WORKFLOW_URL=http://localhost:9001
export RESMGR_URL=http://localhost:9002
export FILEMGR_HOME=$BIGTRANSLATE_HOME/filemgr
export PGE_HOME=$BIGTRANSLATE_HOME/pge
export PCS_HOME=$BIGTRANSLATE_HOME/pcs

