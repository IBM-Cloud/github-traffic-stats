# Define the service names used across the scripts.
# When updating here, please also update in backend/manifest.yml

AppID_service=ghstatsAppID
DB_service=ghstatsDB
DDE_service=ghstatsDDE

# Initial name of service keys
DB_service_key=ghstatskey

# Cloud Foundry application name - needed to rotate the credentials
CFApp_name=github-traffic-stats

# Data center into which to deploy Db2
Datacenter="eu-de:frankfurt"