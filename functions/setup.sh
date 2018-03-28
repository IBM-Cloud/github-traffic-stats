# Automatically set up services and actions for tutorial on
# regular Github statistics
#
# Written by Henrik Loeser

# create Db2 Warehouse service and service credentials
# bx service create dashDB entry eventDB
# bx service key-create dashDB-p ghstatskey


bx wsk action create collectStats --kind python-jessie:3 ghstats.zip
# bind service credentials
bx wsk service bind dashDB collectStats --instance ghdb2
# trigger for firing off daily
bx wsk trigger create mydaily --feed /whisk.system/alarms/alarm --param cron "0 9 * * *" --param startDate "2018-03-21T00:00:00.000Z" --param stopDate "2018-03-31T00:00:00.000Z"
# rule
bx wsk rule create myStatsRule myDaily collectStats
