#!/bin/bash

. ./../servicenames.sh

# create package to bind parameters to it
ibmcloud fn package create Stats4Slack

# create action within package
ibmcloud fn action update Stats4Slack/postWeeklyStats postWeeklyStats.js  --kind nodejs:8

# bind the Db2 credentials to action
ibmcloud fn service bind dashDB Stats4Slack/postWeeklyStats --instance $DB_service --keyname $DB_service_key

# bin webhook, channel name, emailid to it
ibmcloud fn package bind Stats4Slack \
 --param url "https://hooks.slack.com/services/T0000000000/0000000000000/00000000" \
 --param channel "#ibm-cloud-github-stats" \
 --param emailid "user@example.com"

# Create a trigger for firing off daily at 6am
ibmcloud fn trigger create myMondayWeekly --feed /whisk.system/alarms/alarm --param cron "0 12 * * 1" --param startDate "2018-10-21T00:00:00.000Z" --param stopDate "2019-12-31T00:00:00.000Z"

# Create a rule to connect the trigger with the action
ibmcloud fn rule create myStats4SlackRule myMondayWeekly Stats4Slack/postWeeklyStats
