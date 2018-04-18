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
# (C) 2018 by IBM

import flask, os, json, datetime, re, requests
from base64 import b64encode
import github # githubpy module
from flask import Flask, jsonify,redirect,request,render_template, url_for, Response, stream_with_context
from flask_httpauth import HTTPBasicAuth
from flask_pyoidc.flask_pyoidc import OIDCAuthentication
from sqlalchemy import Column, Table, Integer, String, select, ForeignKey
from sqlalchemy.orm import relationship, backref
from flask_sqlalchemy import SQLAlchemy
# Authentication for DDE, based on token
from itsdangerous import (TimedJSONWebSignatureSerializer
                          as Serializer, BadSignature, SignatureExpired)


# monkey patch for now, so that Flask-pyoidc works with App ID
# import the patched function and overwrite the existing one in the module
import mypatch
OIDCAuthentication._handle_authentication_response=mypatch.my_handle_authentication_response


# Initialize Flask app
app = Flask(__name__)

# Check if we are in a Cloud Foundry environment, i.e., on IBM Cloud
# If we are on IBM Cloud, obtain the credentials from the environment.
# Else, read them from file.
# Thereafter, set up the services and module with the obtained credentials.
if 'VCAP_SERVICES' in os.environ:
   vcapEnv=json.loads(os.environ['VCAP_SERVICES'])

   # Obtain configuration for Db2 Warehouse database
   dbInfo=vcapEnv['dashDB'][0]['credentials']

   # Obtain configuration for
   appIDInfo = vcapEnv['AppID'][0]['credentials']

   # Configure access to DDE service
   DDE=vcapEnv['dynamic-dashboard-embedded'][0]['credentials']

   # Update Flask configuration
   app.config.update({'SERVER_NAME': json.loads(os.environ['VCAP_APPLICATION'])['uris'][0],
                      'SECRET_KEY': 'my_not_so_dirty_secret_key',
                      'PREFERRED_URL_SCHEME': 'https',
                      'DEBUG': False})

# we are local, so load info from a file
else:
   # Credentials are read from a file
   with open('config.json') as confFile:
       # load JSON data from file
       appConfig=json.load(confFile)
       # Extract AppID configuration
       appIDInfo=appConfig['AppID']
       # Config for Db2
       dbInfo=appConfig['dashDB']
       #Config for DDE
       DDE=appConfig['DDE']
   # See http://flask.pocoo.org/docs/0.12/config/
   app.config.update({'SERVER_NAME': '0.0.0.0:5000',
                      'SECRET_KEY': 'my_secret_key',
                      'PREFERRED_URL_SCHEME': 'http',
                      'PERMANENT_SESSION_LIFETIME': 2592000, # session time in seconds (30 days)
                      'DEBUG': True})


# General setup based on the obtained configuration
# Configure database access
app.config['SQLALCHEMY_DATABASE_URI']=dbInfo['uri']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=False
app.config['SQLALCHEMY_ECHO']=False

# Configure access to App ID service for the OpenID Connect client
provider_config={
     "issuer": "appid-oauth.ng.bluemix.net",
     "authorization_endpoint": appIDInfo['oauthServerUrl']+"/authorization",
     "token_endpoint": appIDInfo['oauthServerUrl']+"/token",
     "userinfo_endpoint": appIDInfo['profilesUrl']+"/api/v1/attributes",
     "jwks_uri": appIDInfo['oauthServerUrl']+"/publickeys"
}
client_info={
    "client_id": appIDInfo['clientId'],
    "client_secret": appIDInfo['secret']
}

# Initialize OpenID Connect client
auth = OIDCAuthentication(app, provider_configuration_info=provider_config, client_registration_info=client_info,userinfo_endpoint_method=None)
# Initialize BasicAuth, needed for token access to data
basicauth = HTTPBasicAuth()

# Initialize SQLAlchemy for our database
db = SQLAlchemy(app, session_options={'autocommit': True})

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
        pass
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
    return render_template('index.html', startpage=True)


# have "unprotected" page with instructions
# from there go to protected page, grab email and other info
# to populate db after creating the SQLALCHEMY_DATABASE_URI

# could split string by semicolon and execute each stmt individually

@app.route('/admin/initialize-app', methods=['GET'])
def initializeApp():
    return render_template('initializeapp.html')

# Show page for entering user information for first system user and tenant
@app.route('/admin/firststep', methods=['GET'])
@auth.oidc_auth
def firststep():
    return render_template('firststep.html')


# Read the database schema file, create tables and then insert the data
# for the first system user. That user becomes system administrator and
# tenant.
# Called from firststep
@app.route('/admin/secondstep', methods=['POST'])
@auth.oidc_auth
def secondstep():
    username=request.form['username']
    ghuser=request.form['ghuser']
    ghtoken=request.form['ghtoken']
    dbstmtstring=None
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
@auth.oidc_auth
def login():
    setuserrole(flask.session['id_token']['email'])
    return redirect(url_for('repostatistics'))

# Show a user profile
@app.route('/user')
@app.route('/user/profile')
@auth.oidc_auth
def profile():
    return render_template('profile.html',id=flask.session['id_token'], role=flask.session['userrole'])

# End the session by logging off
@app.route('/logout')
@auth.oidc_logout
def logout():
    flask.session['userrole']=None
    return redirect(url_for('index'))

# Form to enter new tenant data
@app.route('/admin/newtenant')
@auth.oidc_auth
def newtenant():
    if isAdministrator():
        return render_template('newuser.html')
    else:
        return render_template('notavailable.html', message="You are not authorized.") # should go to error or info page


# Show table with system logs
@app.route('/admin/systemlog')
@auth.oidc_auth
def systemlog():
    if isSysMaintainer() or isAdministrator():
        return render_template('systemlog.html',)
    else:
        return render_template('notavailable.html', message="You are not authorized.") # should go to error or info page

# return page with the repository stats
@app.route('/repos/stats')
@auth.oidc_auth
def repostatistics():
    if isTenant() or isTenantViewer() or isRepoViewer():
        # IDEA: expand to limit number of selected days, e.g., past 30 days
        return render_template('repostats.html')
    else:
        return render_template('notavailable.html', message="You are not authorized.") # should go to error or info page

# return page with the repository stats
@app.route('/repos/statsweekly')
@auth.oidc_auth
def repostatistics_weekly():
    if isTenant() or isTenantViewer() or isRepoViewer():
        # IDEA: expand to limit number of selected days, e.g., past 30 days
        return render_template('repostatsweek.html')
    else:
        return render_template('notavailable.html', message="You are not authorized.") # should go to error or info page



# Show list of managed repositories
@app.route('/repos')
@app.route('/repos/list')
@auth.oidc_auth
def listrepos():
    if isTenant():
        return render_template('repolist.html')
    else:
        return render_template('notavailable.html', message="You are not authorized.") # should go to error or info page

# Process the request to add a new repository
@app.route('/api/newrepo', methods=['POST'])
@auth.oidc_auth
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
            aid=None
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
                aid=row['aid']
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
        print "Created repo with id "+str(rid)
        return jsonify(message="Your new repo ID: "+str(rid), repoid=rid)
    else:
        return jsonify(message="Error: no repository added") # should go to error or info page

# Process the request to delete a repository
@app.route('/api/deleterepo', methods=['POST'])
@auth.oidc_auth
def deleterepo():
    if isTenant():
        # Access form data from app
        repoid=request.form['repoid']
        # Log to stdout stream
        print "Deleted repo with id "+str(repoid)

        # could check if repo exists
        # but skipping to reduce complexity

        # delete from repos, tenantrepos and every row in adminuserreporoles

        connection = db.engine.connect()
        trans = connection.begin()
        try:
            # delete the repo record
            result = connection.execute("delete from repos where rid=?",repoid)
            # delete the relationship information
            result = connection.execute("delete from tenantrepos where rid=?",repoid)
            # delete the role information
            result = connection.execute("delete from admintenantreporoles where rid=?",repoid)
            # delete related traffic data
            # IDEA: This app could be extended to ask whether to keep this data.
            result = connection.execute("delete from repotraffic where rid=?",repoid)

            trans.commit()
        except:
            trans.rollback()
            raise
        return jsonify(message="Deleted repository: "+str(repoid), repoid=repoid)
    else:
        return jsonify(message="Error: no repository deleted") # should go to error or info page


# Initialize session to display a canned DDE dashboard
@app.route('/api/v1/dashboard_display_session', methods=['POST'])
@auth.oidc_auth
def dashboard_display_session():
    # For DDE-based data access we are going to use token-based Basic Auth
    # In the following, encode the session user's email into a time-limited
    # access token.

    # 1 hour expiration time for data access
    expiration=3600
    # New token generator, initialize with expiration time
    s = Serializer(app.config['SECRET_KEY'], expires_in = expiration)
    # generate a new token based on the email address
    token=s.dumps({'id': flask.session['id_token']['email']})
    # encode it for Basic Auth usage
    enctoken=b64encode(token.decode('ascii')+":Iamatoken").decode("ascii")

    # Load the dashboard specification from JSON file - this could be stored in
    # the database, too.
    with open('dashboard.json') as dashboardFile:
        # load JSON data from file, this is the dashboard spec
        dboard=json.load(dashboardFile)

    # This looks ugly and, yes,  it is... :)
    # Replace the value for Basic Auth within the dashboard specification
    [item for item in dboard['dataSources']['sources'][0]['module']['source']['srcUrl']['property']
        if item['name']=='headers'][0]['value'][0]['value']="Basic "+enctoken
    # Replace the value for sourceUrl within the dashboard specification
    dboard['dataSources']['sources'][0]['module']['source']['srcUrl']['sourceUrl']=request.url_root+"api/v1/data/repositorystats.csv"

    # For debugging - obtain the changed value for Authorization and print it:
    # vals=[item for item in dboard['dataSources']['sources'][0]['module']['source']['srcUrl']['property']
    #         if item['name']=='headers'][0]['value'][0]['value']
    # print vals
    # dboard['dataSources']['sources'][0]['module']['source']['srcUrl']['sourceUrl']


    # Configure result for DDE initialization
    body={ "expiresIn": expiration, "webDomain" : request.url_root }
    ddeUri=DDE['api_endpoint_url']+'v1/session'
    # Obtain new session code from DDE
    res = requests.post(ddeUri, data=json.dumps(body) , auth=(DDE['client_id'], DDE['client_secret']), headers={'Content-Type': 'application/json'})
    # All data in place, return it back to the client
    return jsonify(sessionData=json.loads(res.text), dashboard=dboard), 201


# Initialize session to display a canned DDE dashboard
@app.route('/api/v1/dashboard_edit_session', methods=['POST'])
@auth.oidc_auth
def dashboard_edit_session():
    # For DDE-based data access we are going to use token-based Basic Auth
    # In the following, encode the session user's email into a time-limited
    # access token.
    expiration=3600
    s = Serializer(app.config['SECRET_KEY'], expires_in = expiration)
    token=s.dumps({'id': flask.session['id_token']['email']})
    enctoken=b64encode(token.decode('ascii')+":Iamatoken").decode("ascii")

    # Define a CSV data source for DDEcsvStats
    # The sourceUrl and the authentication are dynamically generated
    DDEcsvStats = {
        "xsd": "https://ibm.com/daas/module/1.0/module.xsd",
        "source": { "id": "Repostats",
                    "srcUrl": { "sourceUrl": request.url_root+"api/v1/data/repositorystats.csv", "mimeType": "text/csv",
                                "property": [
                                        { "name": "separator", "value": ", " },
                                        { "name": "ColumnNamesLine", "value": "true" },
                                        { "name": "headers", "value": [{"name": "Authorization", "value": "Basic "+enctoken}]}
                                    ]
                                }
                  },
        "table": { "name": "repositorystats", "description": "Traffic data for repositories",
              "column": [
                    { "name": "RID", "description": "repository ID", "datatype": "INTEGER", "nullable": "false", "label": "Repository ID", "usage": "identifier", "regularAggregate": "countDistinct"},
                    { "name": "ORGNAME", "description": "Organization or user", "datatype": "VARCHAR(255)", "nullable": "false", "label": "organization or user", "usage": "identifier", "regularAggregate": "countDistinct" },
                    { "name": "REPONAME", "description": "repository name","datatype": "VARCHAR(255)", "nullable": "false", "label": "repository name", "usage": "fact", "regularAggregate": "total" },
                    { "name": "TDATE", "description": "traffic date", "datatype": "DATE", "nullable": "false", "label": "traffic date", "usage": "identifier", "regularAggregate": "countDistinct", "taxonomyFamily": "cDate" },
                    { "name": "VIEWCOUNT", "datatype": "INTEGER", "nullable": "false", "label": "count of views", "usage": "fact", "regularAggregate": "total" },
                    { "name": "VUNIQUES", "datatype": "INTEGER", "nullable": "false", "label": "unique views", "usage": "fact", "regularAggregate": "total" },
                    { "name": "CLONECOUNT", "datatype": "INTEGER", "nullable": "false", "label": "count of clones", "usage": "fact", "regularAggregate": "total" },
                    { "name": "CUNIQUES", "datatype": "INTEGER", "nullable": "false", "label": "unique counts", "usage": "fact", "regularAggregate": "total" } ]
                },
        "label": "Repository Traffic Data",
        "identifier": "Repostats" }

    # Setup request to DDE for new session code
    body={ "expiresIn": expiration, "webDomain" : request.url_root }
    ddeUri=DDE['api_endpoint_url']+'v1/session'
    # Obtain new session code from DDE
    res = requests.post(ddeUri, data=json.dumps(body) , auth=(DDE['client_id'], DDE['client_secret']), headers={'Content-Type': 'application/json'})
    # Ok, return the session code and CSV data source information as JSON
    return jsonify(sessionData=json.loads(res.text), csvStats=DDEcsvStats), 201



# Display a canned DDE dashboard
@app.route('/repos/dashboard')
@auth.oidc_auth
def dashboard():
    if isTenant() or isTenantViewer() or isRepoViewer():
        return render_template('dashboard.html')
    else:
        return render_template('notavailable.html', message="You are not authorized.")

# Create a new DDE dashboard
@app.route('/repos/newdashboard')
@auth.oidc_auth
def new_dashboard():
    if isTenant():
        return render_template('dashboardnew.html')
    else:
        return render_template('notavailable.html', message="You are not authorized.")



# return the currently active user as csv file
@app.route('/data/user.csv')
@auth.oidc_auth
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
@auth.oidc_auth
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
@auth.oidc_auth
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
@auth.oidc_auth
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
@auth.oidc_auth
def generate_repostats():
    def generate():
        yield "RID,TDATE,VIEWCOUNT,VUNIQUES,CLONECOUNT,CUNIQUES\n"
        if isTenant() or isTenantViewer() or isRepoViewer():
            result = db.engine.execute(statstmt,flask.session['id_token']['email'])
            for row in result:
                yield ','.join(map(str,row)) + '\n'
    return Response(stream_with_context(generate()), mimetype='text/csv')

# Return statistics for use in DDE
@app.route('/api/v1/data/repositorystats.csv')
@basicauth.login_required
def api_generate_repostats():
    def generate():
        yield "RID,ORGNAME,REPONAME,TDATE,VIEWCOUNT,VUNIQUES,CLONECOUNT,CUNIQUES\n"
        result = db.engine.execute(statsFullOrgStmt,flask.g.email)
        for row in result:
            yield ','.join(map(str,row)) + '\n'
    return Response(stream_with_context(generate()), mimetype='text/csv')
    resp = make_response(render_template('list.html', entries=entries))


# Handle password verification our way:
# Check that the token is valid and ignore the password
@basicauth.verify_password
def verify_password(token, nopassword):
    # Need the serializer
    s = Serializer(app.config['SECRET_KEY'])
    try:
        # Ok, check for a valid token and extract the data
        data = s.loads(token)
    except SignatureExpired:
        # valid token, but expired
        return False
    except BadSignature:
        # invalid token
        return False
    # all well, set the email for use in the csv generator functions
    flask.g.email = data['id']
    return True

# Generate list of repositories for web page, dynamically loaded
@app.route('/data/repositories.txt')
@auth.oidc_auth
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
@auth.oidc_auth
def generate_repolist():
    def generate():
        result = db.engine.execute(repolist_stmt,flask.session['id_token']['email'])
        yield "RID,ORGNAME,REPONAME\n"
        for row in result:
            yield ','.join(map(str,row)) + '\n'
    return Response(stream_with_context(generate()), mimetype='text/csv')

# Export repositories as CSV file
# CURRENTLY NOT IN USE, but could be used by DDE dashboard
@app.route('/api/v1/data/repositories.csv')
@basicauth.login_required
def api_generate_repolist():
    def generate():
        result = db.engine.execute(repolist_stmt,flask.g.email)
        yield "RID,ORGNAME,REPONAME\n"
        for row in result:
            yield ','.join(map(str,row)) + '\n'
    return Response(stream_with_context(generate()), mimetype='text/csv')

# Some functionality is not available yet
@app.route('/admin')
@app.route('/data')
@auth.oidc_auth
def not_available():
    return render_template('notavailable.html')

# error function for auth module
@auth.error_view
def error(error=None, error_description=None):
    return jsonify({'error': error, 'message': error_description})


port = os.getenv('PORT', '5000')
if __name__ == "__main__":
	app.run(host='0.0.0.0', port=int(port))
