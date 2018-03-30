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
allUsersStatement="select uid, ghuser, ghtoken from users"
# fetch all repos for a given userID
allReposStatement="select r.rid, ghu.username, r.rname from userrepos ur,repos r, ghusers ghu where ur.rid=r.rid and r.ownerid=ghu.uid and ur.uid=?"

# merge the view traffic data
mergeViews1="merge into repotraffic rt using (values"
mergeViews2=") as nv(rid,viewdate,viewcount,uniques) on rt.rid=nv.rid and rt.tdate=nv.viewdate when matched then update set viewcount=nv.viewcount, vuniques=nv.uniques when not matched then insert (rid,tdate,viewcount, vuniques) values(nv.rid,nv.viewdate,nv.viewcount,nv.uniques)"

# merge the clone traffic data
mergeClones1="merge into repotraffic rt using (values"
mergeClones2=") as nc(rid,clonedate,clonecount,uniques) on rt.rid=nc.rid and rt.tdate=nc.clonedate when matched then update set clonecount=nc.clonecount, cuniques=nc.uniques when not matched then insert (rid,tdate,clonecount,cuniques) values(nc.rid,nc.clonedate,nc.clonecount,nc.uniques)"

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
    logtext="cloudfunction ()"
    errortext=None

    ssldsn = args["__bx_creds"]["dashDB"]["ssldsn"]
    #ssldsn = args["ssldsn"]
    if globals().get("conn") is None:
        conn = ibm_db.connect(ssldsn, "", "")

    # go over all system users
    allUsers=ibm_db.exec_immediate(conn,allUsersStatement)
    if (allUsers):

        # prepare statement for logging
        logStmt = ibm_db.prepare(conn, insertLogEntry)

        # fetch first user
        sysuser=ibm_db.fetch_assoc(allUsers)
        while sysuser != False:
            # go over all repos managed by that user and fetch traffic data
            # first, login to Github as that user
            gh = github.GitHub(username=sysuser["GHUSER"],  access_token=sysuser["GHTOKEN"])

            userRepoCount=0
            # prepare and execute statement to fetch related repositories
            reposStmt = ibm_db.prepare(conn, allReposStatement)
            if (ibm_db.execute(reposStmt,(sysuser["UID"],))):
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
            if errortext:
                logtext=logtext+", repo errors: "+errortext
            res=ibm_db.execute(logStmt,(sysuser["UID"],time.strftime("%Y-%m-%d %H:%M:%S", ts),userRepoCount,logtext))
            # fetch next system user
            sysuser=ibm_db.fetch_assoc(allUsers)
    return {"repoCount": repoCount}

if __name__ == "__main__":
    main(json.loads(sys.argv[1]))
