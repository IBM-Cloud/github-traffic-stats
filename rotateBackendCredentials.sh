#!/bin/bash

# Script to rotate credentials for the backend app by
# unbinding and binding the services, then performing a
# zero-downtime restart of the app.

# service names
. ./servicenames.sh

# Unbind the services
ibmcloud cf unbind-service $CFApp_name $AppID_service
ibmcloud cf unbind-service $CFApp_name $DB_service
ibmcloud cf unbind-service $CFApp_name $DDE_service

# Now bind them again to regenerate credentials
ibmcloud cf bind-service $CFApp_name $AppID_service
ibmcloud cf bind-service $CFApp_name $DB_service
ibmcloud cf bind-service $CFApp_name $DDE_service

# Restart the app with zero-downtime command
ibmcloud cf v3-zdt-restart $CFApp_name

### As alternative use the "restage" command
# ibmcloud cf restage $CFApp_name