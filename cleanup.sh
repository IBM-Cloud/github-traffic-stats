# Cleanup resources

# Delete AppID
bx resource service-instance-delete ghstatsAppID
# Delete DDE
bx resource service-instance-delete ghstatsDDE
# Delete Db2 Warehouse
bx service delete ghstatsDB
# Finally remove the app
bx cf delete github-traffic-stats
