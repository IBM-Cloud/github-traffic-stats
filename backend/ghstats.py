# Manage repositories to automatically collect GitHub traffic statistics.
# Traffic data can be displayed, repositories added or deleted.
#
# Most actions are protected by using IBM Cloud App ID as an OpenID Connect
# authorization provider. Data is stored in a Db2 Warehouse on Cloud database.
# The app is designed to be ready for multi-tenant use, but not all functionality
# has been implemented yet. Right now, single-tenant operations are assumed.
#
# For the database schema see the file database.sql
#
# Written by Henrik Loeser (data-henrik), hloeser@de.ibm.com
# (C) 2018-2021 by IBM

import flask, os, json, datetime, decimal, re, requests, time
from functools import wraps

# for loading .env
from dotenv import load_dotenv

# Needed for decoding / encoding credentials
from base64 import b64encode

# githubpy module to access GitHub
import github

# everything Flask for this app
from flask import (Flask, jsonify, make_response, redirect,request,
		   render_template, url_for, Response, stream_with_context)
from flask_pyoidc.flask_pyoidc import OIDCAuthentication
from flask_pyoidc.provider_configuration import ProviderConfiguration, ClientMetadata, ProviderMetadata

# Database access using SQLAlchemy
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.pool import NullPool

# Advanced security
from flask_talisman import Talisman, ALLOW_FROM

# load environment
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
# Set up content security policy, so that resources can be loaded and executed
# Could be slightly optimized for further security, e.g., by making scripts
# local and be more specific about script execution.
csp = {
    'default-src': [
        '\'self\'',
        '\'unsafe-inline\'',
        'use.fontawesome.com',
        'cdn.jsdelivr.net',
        'cdn.datatables.net',
        '*.ibm.com'
    ],
    'img-src': '*',
    'script-src': [
        '\'self\'',
        '\'unsafe-inline\'',
        'use.fontawesome.com',
        'cdn.datatables.net',
        'cdn.jsdelivr.net',
        'cdnjs.cloudflare.com',
        '*.ibm.com'
    ]
}
#talisman=Talisman(app, content_security_policy=csp)

# Read the configuration and possible environment variables
# There are from local .env, provided through K8s secrets or
# through service bindings.
DB2_URI=None
APPID_CLIENT_ID=None
APPID_OAUTH_SERVER_URL=None
APPID_SECRET=None
FULL_HOSTNAME=None
EVENT_TOKEN=None
ALL_CONFIGURED=False


# First, check for any service bindings
if 'VCAP_SERVICES' in os.environ:
    vcapEnv=json.loads(os.environ['VCAP_SERVICES'])

    # Db2, either Db2 Warehouse or Db2 (lite plan)
    if 'dashdb' in vcapEnv:
        DB2_URI=vcapEnv['dashdb'][0]['credentials']['uri']
    elif 'dashdb-for-transactions' in vcapEnv:
        DB2_URI=vcapEnv['dashdb-for-transactions'][0]['credentials']['uri']
    
    # AppID
    if 'appid' in vcapEnv:
       appIDInfo = vcapEnv['appid'][0]['credentials']
       APPID_CLIENT_ID=appIDInfo['clientId']
       APPID_OAUTH_SERVER_URL=appIDInfo['oauthServerUrl']
       APPID_SECRET=appIDInfo['secret']
    
# Now, check for any overwritten environment settings. 
# Obtain configuration for Db2 Warehouse database
DB2_URI=os.getenv("DB2_URI", DB2_URI)

# AppID settings
APPID_CLIENT_ID=os.getenv("APPID_CLIENT_ID", APPID_CLIENT_ID)
APPID_OAUTH_SERVER_URL=os.getenv("APPID_OAUTH_SERVER_URL", APPID_OAUTH_SERVER_URL)
APPID_SECRET=os.getenv("APPID_SECRET", APPID_SECRET)

# Event settings
EVENT_TOKEN=os.getenv("EVENT_TOKEN","CE_rulez")

# Full hostname
FULL_HOSTNAME=os.getenv("FULL_HOSTNAME")

# is everything configured?
if (DB2_URI and APPID_CLIENT_ID and APPID_OAUTH_SERVER_URL and APPID_SECRET and FULL_HOSTNAME):
    ALL_CONFIGURED=True

    # Update Flask configuration
    #'SERVER_NAME': os.getenv("HOSTNAME"),
    app.config.update({'OIDC_REDIRECT_URI': os.getenv('FULL_HOSTNAME')+'/redirect_uri',
                       'SECRET_KEY': 'my_not_so_dirty_secret_key',
                       'PERMANENT_SESSION_LIFETIME': 1800, # session time in second (30 minutes)
                       'DEBUG': os.getenv("FLASK_DEBUG", False)})

    # General setup based on the obtained configuration
    # Configure database access
    
    app.config['SQLALCHEMY_DATABASE_URI']=DB2_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=False
    app.config['SQLALCHEMY_ECHO']=False

    # Configure access to App ID service for the OpenID Connect client
    appID_clientinfo=ClientMetadata(client_id=APPID_CLIENT_ID,client_secret=APPID_SECRET)
    appID_config = ProviderConfiguration(issuer=APPID_OAUTH_SERVER_URL,client_metadata=appID_clientinfo)

    # Initialize OpenID Connect client
    auth=OIDCAuthentication({'default': appID_config}, app)

    # Initialize SQLAlchemy for our database
    db = SQLAlchemy(app, session_options={'autocommit': True})


    # Three (3) decorators that wrap the auth decorators. See the comments
    # in the ELSE for the background
    def security_decorator_auth(f):        
        @wraps(f)
        @auth.oidc_auth('default')
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated_function

    def security_decorator_logout(f):        
        @wraps(f)
        @auth.oidc_logout
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated_function

    def security_decorator_error(f):        
        @wraps(f)
        @auth.error_view
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated_function


    # end of skipped
    # initial configuration
    #
else:
    # We are not initialized yet, but try to provide some minimal app to the user
    #
    # Some heavy lifting required...
    #
    # Define 3 pseudo decorators that just do nothing.
    # This way we can have an up and running app if no services are
    # bound to / passed into the app yet. This allows to have a 
    # successful deployment even without all the tutorial steps
    # performed.
    def security_decorator_auth(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated_function

    def security_decorator_logout(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated_function

    def security_decorator_error(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated_function



# Encoder to handle some raw data correctly
def alchemyencoder(obj):
    """JSON encoder function for SQLAlchemy special classes."""
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    elif isinstance(obj, decimal.Decimal):
        return float(obj)

# Set the role for the current session user
def setuserrole(email=None):
    flask.session['userrole']=0
    try:
        result = db.engine.execute("select role from adminroles ar, adminusers au where ar.aid=au.aid and au.email=?",email)
        for row in result:
            # there should be exactly one matching row
            flask.session['userrole']=row[0]
    except:
        app.logger.error("Db2 error")
        raise
    return flask.session['userrole']

# Check for userrole
def checkUserrole(checkbit=0):
    if "userrole" in flask.session:
        return (flask.session['userrole'] & checkbit)
    else:
        return False

# Has the user the role of administrator?
def isAdministrator():
    return checkUserrole(checkbit=1)

# Has the user the role of system maintainer?
def isSysMaintainer():
    return checkUserrole(checkbit=2)

# Has the user the role of tenant?
def isTenant():
    return checkUserrole(checkbit=4)

# Has the user the role of tenant stats viewer?
def isTenantViewer():
    return checkUserrole(checkbit=8)

# Has the user the role of tenant stats viewer?
def isRepoViewer():
    return checkUserrole(checkbit=16)

# Index page, unprotected to display some general information
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', startpage=True, configured=ALL_CONFIGURED)


# have "unprotected" page with instructions
# from there go to protected page, grab email and other info
# to populate db after creating the SQLALCHEMY_DATABASE_URI

# could split string by semicolon and execute each stmt individually

@app.route('/admin/initialize-app', methods=['GET'])
def initializeApp():
    return render_template('initializeapp.html')

# Show page for entering user information for first system user and tenant
@app.route('/admin/firststep', methods=['GET'])
@security_decorator_auth
def firststep():
    return render_template('firststep.html')


# Read the database schema file, create tables and then insert the data
# for the first system user. That user becomes system administrator and
# tenant.
# Called from firststep
@app.route('/admin/secondstep', methods=['POST'])
@security_decorator_auth
def secondstep():
    username=request.form['username']
    ghuser=request.form['ghuser']
    ghtoken=request.form['ghtoken']
    sqlfile = open('database.sql', 'r')  # read the file line by line into array
    sqlcode = ''
    for line in sqlfile:
        sqlcode += re.sub(r'--.*', '', line.rstrip() )  # remove the in-line comments

    dbstatements = sqlcode.split(';') # split the text into commands

    connection = db.engine.connect()
    trans = connection.begin()
    try:
        # We are going to execute each of the DB schema-related statements,
        # thereby creating the database structures and some configuration data.
        # If there is an error, it means that the required setup has not between
        # done or the environment has been already set up.
        for stmt in dbstatements:
            connection.execute(stmt)
        connection.execute("insert into adminusers (aid, auser, email) values(?,?,?)", 100, username, flask.session['id_token']['email'])
        connection.execute("insert into tenants (tid, ghuser, ghtoken) values(?,?,?)", 100, ghuser, ghtoken)
        connection.execute("insert into adminroles (aid, role) values(?,?)", 100, 5)
        # Adminuser has tentant role for the tenant (user)
        connection.execute("insert into admintenantreporoles (aid, tid, role) values(?,?,?)", 100, 100, 4)
        trans.commit()
    except:
        trans.rollback()
        # for now ignore error and return to index page, but ideally report error and return to welcome page
        return redirect(url_for('index'))
    # Have to set userrole because now the data is ready
    setuserrole(flask.session['id_token']['email'])
    return redirect(url_for('listrepos'))

# Official login URI, redirects to repo stats after processing
@app.route('/login')
@security_decorator_auth
def login():
    if setuserrole(flask.session['id_token']['email'])>0:
        return redirect(url_for('repostatistics'))
    else:
        return redirect(url_for('logout'))

# Show a user profile
@app.route('/user')
@app.route('/user/profile')
@security_decorator_auth
def profile():
    return render_template('profile.html',id=flask.session['id_token'], role=flask.session['userrole'])

# End the session by logging off
@app.route('/logout')
@security_decorator_logout
def logout():
    flask.session['userrole']=None
    return redirect(url_for('index'))

# Form to enter new tenant data
@app.route('/admin/newtenant')
@security_decorator_auth
def newtenant():
    if isAdministrator():
        return render_template('newuser.html')
    else:
        return render_template('notavailable.html', message="You are not authorized.") # should go to error or info page


# Show table with system logs
@app.route('/admin/systemlog')
@security_decorator_auth
def systemlog():
    if isSysMaintainer() or isAdministrator():
        return render_template('systemlog.html',)
    else:
        return render_template('notavailable.html', message="You are not authorized.") # should go to error or info page

# return page with the repository stats
@app.route('/repos/stats')
@security_decorator_auth
def repostatistics():
    if isTenant() or isTenantViewer() or isRepoViewer():
        # IDEA: expand to limit number of selected days, e.g., past 30 days
        return render_template('repostats.html')
    else:
        return render_template('notavailable.html', message="You are not authorized.") # should go to error or info page

# return page with the repository stats
@app.route('/repos/statsweekly')
@security_decorator_auth
def repostatistics_weekly():
    if isTenant() or isTenantViewer() or isRepoViewer():
        # IDEA: expand to limit number of selected days, e.g., past 30 days
        return render_template('repostatsweek.html')
    else:
        return render_template('notavailable.html', message="You are not authorized.") # should go to error or info page



# Show list of managed repositories
@app.route('/repos')
@app.route('/repos/list')
@security_decorator_auth
def listrepos():
    if isTenant():
        return render_template('repolist.html')
    else:
        return render_template('notavailable.html', message="You are not authorized.") # should go to error or info page

# Process the request to add a new repository
@app.route('/api/newrepo', methods=['POST'])
@security_decorator_auth
def newrepo():
    if isTenant():
        # Access form data from app
        orgname=request.form['orgname']
        reponame=request.form['reponame']

        # could check if repo exists
        # but skipping to reduce complexity

        connection = db.engine.connect()
        trans = connection.begin()
        try:
            tid=None
            rid=None
            orgid=None
            ghstmt="""select atrr.tid, au.aid,t.ghuser,t.ghtoken
                      from  admintenantreporoles atrr, adminusers au, adminroles ar, tenants t
                      where ar.aid=au.aid
                      and atrr.aid=au.aid
                      and t.tid=atrr.tid
                      and bitand(atrr.role,4)>0
                      and au.email=?   """
            githubinfo = connection.execute(ghstmt,flask.session['id_token']['email'])
            for row in githubinfo:
                tid=row['tid']
            orgidinfo = connection.execute("select oid from ghorgusers where username=?",orgname)
            for row in orgidinfo:
                orgid=row['oid']
            if orgid is None:
                neworgidinfo = connection.execute("select oid from new table (insert into ghorgusers(username) values(?))",orgname)
                for row in neworgidinfo:
                        orgid=row['oid']
            repoid = connection.execute("select rid from new table (insert into repos(rname,ghserverid,oid,schedule) values(?,?,?,?))",reponame,1,orgid,0)
            for row in repoid:
                rid=row['rid']
            repoid = connection.execute("insert into tenantrepos values(?,?)",tid,rid)
            trans.commit()
        except:
            trans.rollback()
            raise
        # Log to stdout stream
        print("Created repo with id "+str(rid))
        return jsonify(message="Your new repo ID: "+str(rid), repoid=rid)
    else:
        return jsonify(message="Error: no repository added") # should go to error or info page

# Process the request to delete a repository
@app.route('/api/deleterepo', methods=['POST'])
@security_decorator_auth
def deleterepo():
    if isTenant():
        # Access form data from app
        repoid=request.form['repoid']
        # Log to stdout stream
        print("Deleted repo with id "+str(repoid))

        # could check if repo exists
        # but skipping to reduce complexity

        # delete from repos, tenantrepos and every row in adminuserreporoles

        connection = db.engine.connect()
        trans = connection.begin()
        try:
            # delete the repo record
            connection.execute("delete from repos where rid=?",repoid)
            # delete the relationship information
            connection.execute("delete from tenantrepos where rid=?",repoid)
            # delete the role information
            connection.execute("delete from admintenantreporoles where rid=?",repoid)
            # delete related traffic data
            # IDEA: This app could be extended to ask whether to keep this data.
            connection.execute("delete from repotraffic where rid=?",repoid)

            trans.commit()
        except:
            trans.rollback()
            raise
        return jsonify(message="Deleted repository: "+str(repoid), repoid=repoid)
    else:
        return jsonify(message="Error: no repository deleted") # should go to error or info page

# return the currently active user as csv file
@app.route('/data/user.csv')
@security_decorator_auth
def generate_user():
    def generate(email):
        yield "user" + '\n'
        yield email + '\n'
    return Response(generate(flask.session['id_token']['email']), mimetype='text/csv')


# Common statement to generate statistics
statstmt="""select r.rid,r.tdate,r.viewcount,r.vuniques,r.clonecount,r.cuniques
            from v_repostats r, v_adminuserrepos v
            where r.rid=v.rid
            and v.email=? """

statsFullOrgStmt="""select r.rid,r.orgname,r.reponame,r.tdate,r.viewcount,r.vuniques,r.clonecount,r.cuniques
                    from v_repostats r, v_adminuserrepos v
                    where r.rid=v.rid
                    and v.email=? """

logstmt="""select tid, completed, numrepos, state
           from systemlog where completed >(current date - ? days)
           order by completed desc, tid asc
           """
# Common statement to generate list of repositories
repolist_stmt="""select rid,orgname, reponame
                 from v_adminrepolist
                 where email=? order by rid asc"""

# Traffic by work week
statsWorkWeek="""select r.rid,orgname,reponame,varchar_format(tdate,'YYYY-IW') as workweek,
                 sum(viewcount) as viewcount, sum(vuniques) as vuniques, sum(clonecount) as clonecount, sum(cuniques) as cuniques
                 from v_repostats r, v_adminuserrepos v
                 where r.rid=v.rid
                 and v.email=?
                 group by r.rid, varchar_format(tdate,'YYYY-IW'), orgname, reponame"""



# return the repository statistics for the web page, dynamically loaded
@app.route('/data/repostats.txt')
@security_decorator_auth
def generate_data_repostats_txt():
    def generate():
        yield '{ "data": [\n'
        if isTenant() or isTenantViewer() or isRepoViewer():
            result = db.engine.execute(statsFullOrgStmt,flask.session['id_token']['email'])
            first=True
            for row in result:
                if not first:
                    yield ',\n'
                else:
                    first=False
                yield '["'+'","'.join(map(str,row)) + '"]'
        yield ']}'
    return Response(stream_with_context(generate()), mimetype='text/utf-8')

# return the repository statistics for the web page, dynamically loaded
@app.route('/data/repostatsWorkWeek.txt')
@security_decorator_auth
def generate_data_repostatsWorkWeek_txt():
    def generate():
        yield '{ "data": [\n'
        if isTenant() or isTenantViewer() or isRepoViewer():
            result = db.engine.execute(statsWorkWeek,flask.session['id_token']['email'])
            first=True
            for row in result:
                if not first:
                    yield ',\n'
                else:
                    first=False
                yield '["'+'","'.join(map(str,row)) + '"]'
        yield ']}'
    return Response(stream_with_context(generate()), mimetype='text/utf-8')


# return the system logs for the web page, dynamically loaded
@app.route('/data/systemlogs.txt')
@security_decorator_auth
def generate_data_systemlogs_txt():
    if isAdministrator() or isSysMaintainer():
        def generate():
            result = db.engine.execute(logstmt,30)
            first=True
            yield '{ "data": [\n'
            for row in result:
                if not first:
                    yield ',\n'
                else:
                    first=False
                yield '["'+'","'.join(map(str,row)) + '"]'
            yield ']}'
        return Response(stream_with_context(generate()), mimetype='text/utf-8')
    else:
        return render_template('notavailable.html', message="You are not authorized.")

# return the repository statistics for the current user as csv file
@app.route('/data/repostats.csv')
@security_decorator_auth
def generate_repostats():
    def generate():
        yield "RID,TDATE,VIEWCOUNT,VUNIQUES,CLONECOUNT,CUNIQUES\n"
        if isTenant() or isTenantViewer() or isRepoViewer():
            result = db.engine.execute(statstmt,flask.session['id_token']['email'])
            for row in result:
                yield ','.join(map(str,row)) + '\n'
    return Response(stream_with_context(generate()), mimetype='text/csv')

# Generate list of repositories for web page, dynamically loaded
@app.route('/data/repositories.txt')
@security_decorator_auth
def generate_data_repolist_txt():
    def generate():
        result = db.engine.execute(repolist_stmt,flask.session['id_token']['email'])
        first=True
        yield '{ "data": [\n'
        for row in result:
            if not first:
                yield ',\n'
            else:
                first=False
            yield '["'+'","'.join(map(str,row)) + '"]'
        yield ']}'
    return Response(stream_with_context(generate()), mimetype='text/utf-8')

# Export repositories as CSV file
@app.route('/data/repositories.csv')
@security_decorator_auth
def generate_repolist():
    def generate():
        result = db.engine.execute(repolist_stmt,flask.session['id_token']['email'])
        yield "RID,ORGNAME,REPONAME\n"
        for row in result:
            yield ','.join(map(str,row)) + '\n'
    return Response(stream_with_context(generate()), mimetype='text/csv')

# handle images correctly, some are expected at /images
@app.route('/images/<path:path>')
def static_file(path):
    return app.send_static_file("images/"+path)

# Some functionality is not available yet
@app.route('/admin')
@app.route('/repos')
@app.route('/data')
@security_decorator_auth
def not_available():
    return render_template('notavailable.html')

# error function for auth module
@security_decorator_error
def error(error=None, error_description=None):
    return jsonify({'error': error, 'message': error_description})



# New section with previously Cloud Functions / serverless functionality
# Collect statistics from GitHub
#
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
def mergeViewData(viewStats, rid, conn):
    # convert traffic data into SQL values
    data=""
    for vday in viewStats['views']:
        data+="("+str(rid)+",'"+vday['timestamp'][:10]+"',"+str(vday['count'])+","+str(vday['uniques'])+"),"
    mergeStatement=mergeViews1+data[:-1]+mergeViews2
    conn.execute(mergeStatement)


# Merge clone data into the traffic table
def mergeCloneData(cloneStats, rid, conn):
    # convert traffic data into SQL values
    data=""
    for cday in cloneStats['clones']:
        data+="("+str(rid)+",'"+cday['timestamp'][:10]+"',"+str(cday['count'])+","+str(cday['uniques'])+"),"
    mergeStatement=mergeClones1+data[:-1]+mergeClones2
    # execute MERGE statement
    conn.execute(mergeStatement)


# Overall flow:
# - loop over users
#   - log in to GitHub as that current user
#   - retrieve repos for that current user, loop the repos
#     - for each repo fetch stats
#     - merge traffic data into table
#  update last run info

def collectStatistics(logPrefix="collectStats"):
    repoCount=0
    processedRepos=0
    logtext=logPrefix+" ("
    errortext=""
    connection = db.engine.connect()
    trans = connection.begin()
    try:
        # go over all system users
        allTenants=connection.execute(allTenantsStatement)
        for row in allTenants:

            # prepare statement for logging
            #logStmt = ibm_db.prepare(conn, insertLogEntry)
        
            # go over all repos managed by that user and fetch traffic data
            # first, login to GitHub as that user
            tid=row["tid"]
            
            gh = github.GitHub(username=row["ghuser"],  access_token=row["ghtoken"])

            userRepoCount=0
            # prepare and execute statement to fetch related repositories
            repos=connection.execute(allReposStatement,tid)
            for row in repos:
                repoCount=repoCount+1
                # fetch view and clone traffic
                try:
                    viewStats=gh.repos(row["username"], row["rname"]).traffic.views.get()
                    cloneStats=gh.repos(row["username"], row["rname"]).traffic.clones.get()
                    if viewStats['views']:
                        mergeViewData(viewStats,row["rid"], connection)
                    if cloneStats['clones']:
                        mergeCloneData(cloneStats,row["rid"], connection)
                    userRepoCount=userRepoCount+1
                    # For debugging:
                    # print repo["USERNAME"]+" "+ repo["RNAME"]

                    # update global repo counter
                    processedRepos=processedRepos+1
                    # fetch next repository
                except:
                    errortext=errortext+str(row["rid"])+" "
                
            # insert log entry
            ts = time.gmtime()
            logtext=logtext+str(processedRepos)+"/"+str(repoCount)+")"
            if errortext !="":
                logtext=logtext+", repo errors: "+errortext
            connection.execute(insertLogEntry,(tid,time.strftime("%Y-%m-%d %H:%M:%S", ts),userRepoCount,logtext))
        trans.commit()
    except:
        trans.rollback()
        raise
    return {"repoCount": repoCount}

@app.route('/admin/collectStats')
@security_decorator_auth
def collectStats():
    res=collectStatistics(logPrefix='collectStats')
    return render_template('collect.html',repoCount=res["repoCount"])

# Ping subscription in Code Engine
# Check for secret token
@app.route('/collectStats', methods=['POST'])
def eventCollectStats():
    mydata=request.json
    if mydata['token']==EVENT_TOKEN:
        res=collectStatistics(logPrefix='CEping')
        return jsonify(message="success - stats collected", repoCount=res["repoCount"]),200
    else:
        return "no success",403


# return the repository statistics for the web page, dynamically loaded
@app.route('/data/repostats.json')
@security_decorator_auth
def generate_data_repostats_json():
    values=[]
    datasets=[]
    if isTenant() or isTenantViewer() or isRepoViewer():
        fetchStmt="""select r.rid, r.tdate, r.viewcount
                     from repotraffic r, v_adminuserrepos v
                     where r.rid=v.rid
                     and v.email=?
                     and r.tdate between (current date - 1 month) and (current date)
                     order by r.rid, r.tdate asc"""

        repoStmt="""select r.rid, r.rname from repos r, v_adminuserrepos v
                    where r.rid=v.rid
                    and v.email=?
                    order by rid asc"""
        result = db.engine.execute(fetchStmt,flask.session['id_token']['email'])
        for row in result:
            values.append({'x':row['tdate'].isoformat(),'y':row['viewcount'], 'id':row['rid']})

        repos = db.engine.execute(repoStmt,flask.session['id_token']['email']).fetchall()
        for row in repos:
            rdict=[d for d in values if d['id'] == row['rid']]
            datasets.append({'data': rdict, 'label': row['rname']})

    return jsonify(labels=[], data=datasets)


@app.route('/repos/linechart')
@security_decorator_auth
def linechart():
    return render_template('chart.html')


# Start the actual app
# Get the PORT from environment
port = os.getenv('PORT', '5000')
if __name__ == "__main__":
	app.run(host='0.0.0.0',port=int(port))
