#!/bin/bash

# Script to rotate credentials for the functions

# service names
. ./servicenames.sh


# Obtain today's date
printf -v TODAYS_DATE '%(%Y%m%d)T' -1

# Generate new service key with the name prefixed by date
NEW_KEYNAME=${TODAYS_DATE}-${DB_service_key}

echo "######"
echo "Creating new service key"
echo "######"
ibmcloud cf create-service-key $DB_service $NEW_KEYNAME

# Bind actions to new service key, overwritig existing binding
echo "######"
echo "Binding action(s)"
echo "######"

ibmcloud fn service bind dashDB collectStats --instance $DB_service --keyname $NEW_KEYNAME

# Uncomment if using the Slack integration
#ibmcloud fn service bind dashDB Stats4Slack/postWeeklyStats --instance $DB_service --keyname $NEW_KEYNAME


# print out the existing service keys
echo "######"
echo "Showing existing keys"
echo "######"

ibmcloud cf service-keys $DB_service

echo "######"
echo "You can remove the old service key using:"
echo "ibmcloud cf delete-service-key ${DB_service} KEYNAME"
