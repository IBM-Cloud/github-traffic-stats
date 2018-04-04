#######
####### Github traffic statistics
#######
# Program or IBM Cloud Function to collect Github view and clone traffic
# and store that data in a relational database, namely Db2.
#
# (C) 2018 IBM
# Written by Henrik Loeser, hloeser@de.ibm.com ("data-henrik")

import github, json, ibm_db, sys, time

#######
# SQL statements
#
# fetch all users
allTenantsStatement="select tid, ghuser, ghtoken from tenants"
# fetch all repos for a given userID
allReposStatement="select r.rid, ghu.username, r.rname from tenantrepos tr,repos r, ghorgusers ghu where tr.rid=r.rid and r.oid=ghu.oid and tr.tid=?"

# merge the view traffic data
mergeViews1="merge into repotraffic rt using (values"
mergeViews2=""") as nv(rid,viewdate,viewcount,uniques) on rt.rid=nv.rid and rt.tdate=nv.viewdate
            when matched and nv.viewcount>rt.viewcount then update set viewcount=nv.viewcount, vuniques=coalesce(nv.uniques,0)
            when not matched then insert (rid,tdate,viewcount, vuniques) values(nv.rid,nv.viewdate,coalesce(nv.viewcount,0),coalesce(nv.uniques,0))
            else ignore"""

# merge the clone traffic data
mergeClones1="merge into repotraffic rt using (values"
mergeClones2=""") as nc(rid,clonedate,clonecount,uniques) on rt.rid=nc.rid and rt.tdate=nc.clonedate
             when matched and nc.clonecount>rt.clonecount then update set clonecount=nc.clonecount, cuniques=coalesce(nc.uniques,0)
             when not matched then insert (rid,tdate,clonecount,cuniques) values(nc.rid,nc.clonedate,coalesce(nc.clonecount,0),coalesce(nc.uniques,0))
             else ignore"""

# new syslog record
insertLogEntry="insert into systemlog values(?,?,?,?)"

# Merge view data into the traffic table
def mergeViewData(viewStats, rid):
    # convert traffic data into SQL values
    data=""
    for vday in viewStats['views']:
        data+="("+str(rid)+",'"+vday['timestamp'][:10]+"',"+str(vday['count'])+","+str(vday['uniques'])+"),"
    mergeStatement=mergeViews1+data[:-1]+mergeViews2
    # execute MERGE statement
    res=ibm_db.exec_immediate(conn,mergeStatement)

# Merge clone data into the traffic table
def mergeCloneData(cloneStats, rid):
    # convert traffic data into SQL values
    data=""
    for cday in cloneStats['clones']:
        data+="("+str(rid)+",'"+cday['timestamp'][:10]+"',"+str(cday['count'])+","+str(cday['uniques'])+"),"
    mergeStatement=mergeClones1+data[:-1]+mergeClones2
    # execute MERGE statement
    res=ibm_db.exec_immediate(conn,mergeStatement)


# Overall flow:
# - loop over users
#   - log in to Github as that current user
#   - retrieve repos for that current user, loop the repos
#     - for each repo fetch stats
#     - merge traffic data into table
#  update last run info

def main(args):
    global conn
    repoCount=0
    processedRepos=0
    logtext="cloudfunction ("
    errortext=""

    ssldsn = args["__bx_creds"]["dashDB"]["ssldsn"]
    #ssldsn = args["ssldsn"]
    if globals().get("conn") is None:
        conn = ibm_db.connect(ssldsn, "", "")

    # go over all system users
    allTenants=ibm_db.exec_immediate(conn,allTenantsStatement)
    if (allTenants):

        # prepare statement for logging
        logStmt = ibm_db.prepare(conn, insertLogEntry)

        # fetch first user
        tenant=ibm_db.fetch_assoc(allTenants)
        while tenant != False:
            # go over all repos managed by that user and fetch traffic data
            # first, login to Github as that user
            gh = github.GitHub(username=tenant["GHUSER"],  access_token=tenant["GHTOKEN"])

            userRepoCount=0
            # prepare and execute statement to fetch related repositories
            reposStmt = ibm_db.prepare(conn, allReposStatement)
            if (ibm_db.execute(reposStmt,(tenant["TID"],))):
                repo=ibm_db.fetch_assoc(reposStmt)
                while repo != False:
                    repoCount=repoCount+1
                    # fetch view and clone traffic
                    try:
                        viewStats=gh.repos(repo["USERNAME"], repo["RNAME"]).traffic.views.get()
                        cloneStats=gh.repos(repo["USERNAME"], repo["RNAME"]).traffic.clones.get()
                        if viewStats['views']:
                            mergeViewData(viewStats,repo["RID"])
                        if cloneStats['clones']:
                            mergeCloneData(cloneStats,repo["RID"])
                        userRepoCount=userRepoCount+1
                        # For debugging:
                        # print repo["USERNAME"]+" "+ repo["RNAME"]

                        # update global repo counter
                        processedRepos=processedRepos+1
                        # fetch next repository
                        repo=ibm_db.fetch_assoc(reposStmt)
                    except:
                        errortext=errortext+str(repo["RID"])+" "
                        # fetch next repository
                        repo=ibm_db.fetch_assoc(reposStmt)
            # insert log entry
            ts = time.gmtime()
            logtext=logtext+str(processedRepos)+"/"+str(repoCount)+")"
            if errortext !="":
                logtext=logtext+", repo errors: "+errortext
            res=ibm_db.execute(logStmt,(tenant["TID"],time.strftime("%Y-%m-%d %H:%M:%S", ts),userRepoCount,logtext))
            # fetch next system user
            tenant=ibm_db.fetch_assoc(allTenants)
    return {"repoCount": repoCount}

if __name__ == "__main__":
    main(json.loads(sys.argv[1]))
