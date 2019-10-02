#!/bin/bash
# Script for simplified setup

# service names
. ./servicenames.sh

# Create a Db2 Warehouse service and a service key
ibmcloud cf create-service dashDB "Flex One" $DB_service -c '{"datacenter" : '${Datacenter}', "oracle_compatible":"no"}'
ibmcloud cf create-service-key ghstatsDB $DB_service_key

# Create AppID service using "bx resource" command. AppID is available with
# resource groups.
ibmcloud resource service-instance-create $AppID_service appid graduated-tier us-south

# Create DDE service (dynamic dashboard embedded)
ibmcloud resource service-instance-create $DDE_service dynamic-dashboard-embedded lite us-south
