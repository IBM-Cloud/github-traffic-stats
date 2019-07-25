#!/bin/bash

# Automatically set up services and actions for tutorial on
# regular Github statistics
#
# Written by Henrik Loeser
# service names
. ./../servicenames.sh

# We need to pull down the githubpy file before packaging,
# then create the zip file and thereafter delete githubpy again (or leave it?).
#
# Fetch the github module:
# wget https://raw.githubusercontent.com/michaelliao/githubpy/master/github.py
#
# Pack the action code and the github module into a zip archive
# zip -r ghstats.zip  __main__.py github.py
#
# Ok, now we can deploy the objects

# Create the action to collect statistics
ibmcloud fn action create collectStats --kind python-jessie:3 ghstats.zip

# Bind the service credentials to the action
ibmcloud fn service bind dashDB collectStats --instance $DB_service --keyname $DB_service_key

# Create a trigger for firing off daily at 6am
ibmcloud fn trigger create myDaily --feed /whisk.system/alarms/alarm --param cron "0 6 * * *" --param startDate "2018-03-21T00:00:00.000Z" --param stopDate "2018-12-31T00:00:00.000Z"

# Create a rule to connect the trigger with the action
ibmcloud fn rule create myStatsRule myDaily collectStats
