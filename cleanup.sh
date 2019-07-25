#!/bin/bash
# Cleanup resources


# service names
. ./servicenames.sh

# Delete AppID
ibmcloud resource service-instance-delete $AppID_service
# Delete DDE
ibmcloud resource service-instance-delete $DDE_service
# Delete Db2 Warehouse
ibmcloud cf delete-service $DB_service
# Finally remove the app
ibmcloud cf delete github-traffic-stats
