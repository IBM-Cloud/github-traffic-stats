# Cleanup resources

# Delete AppID
ibmcloud resource service-instance-delete ghstatsAppID
# Delete DDE
ibmcloud resource service-instance-delete ghstatsDDE
# Delete Db2 Warehouse
ibmcloud cf delete-service ghstatsDB
# Finally remove the app
ibmcloud cf delete github-traffic-stats
