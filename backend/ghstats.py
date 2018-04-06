# Manage repositories to automatically collect Github traffic statistics.
# Traffic data can be displayed, repositories added or deleted.
#
# Most actions are protected by using IBM Cloud App ID as an openID Connect
# authorization provider. Data is stored in a Db2 Warehouse on Cloud database.
# The app is designed to be ready for multi-tenant use, but not all functionality
# has been implemented yet. Right now, single-tenant operations are assumed.
#
# For the database schema see the file database.sql
#
# Written by Henrik Loeser (data-henrik), hloeser@de.ibm.com
# (C) 2018 by IBM

import flask, os, json, datetime, re, requests
import github # githubpy module
from flask import Flask, jsonify,redirect,request,render_template, url_for, Response, stream_with_context

from flask_pyoidc.flask_pyoidc import OIDCAuthentication
from sqlalchemy import Column, Table, Integer, String, select, ForeignKey
from sqlalchemy.orm import relationship, backref
from flask_sqlalchemy import SQLAlchemy


# monkey patch for now, so that Flask-pyoidc works with App ID
import mypatch
OIDCAuthentication._handle_authentication_response=mypatch.my_handle_authentication_response

app = Flask(__name__)

# Check if we are in a Cloud Foundry environment, i.e., on IBM Cloud
if 'VCAP_SERVICES' in os.environ:
   vcapEnv=json.loads(os.environ['VCAP_SERVICES'])

   # Obtain configuration for Db2 Warehouse database
   dbInfo=vcapEnv['dashDB'][0]['credentials']

   # Obtain configuration for
   appIDInfo = vcapEnv['AppID'][0]['credentials']

   # Configure access to DDE service
   DDE=vcapEnv['dynamic-dashboard-embedded'][0]['credentials']

   # See http://flask.pocoo.org/docs/0.12/config/
   app.config.update({'SERVER_NAME': json.loads(os.environ['VCAP_APPLICATION'])['uris'][0],
                      'SECRET_KEY': 'my_secret_key',
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
#
# Configure database access
app.config['SQLALCHEMY_DATABASE_URI']=dbInfo['uri']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=False
app.config['SQLALCHEMY_ECHO']=False

# Configure access to App ID service and openID Connect client
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

# Initialize openID Connect client
auth = OIDCAuthentication(app, provider_configuration_info=provider_config, client_registration_info=client_info,userinfo_endpoint_method=None)

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
        result = db.engine.execute("select tid, completed, numrepos, state from systemlog where completed >(current date - 21 days) order by completed desc, tid asc")
        return render_template('systemlog.html',logs=result)
    else:
        return render_template('notavailable.html', message="You are not authorized.") # should go to error or info page

# return page with the repository stats
@app.route('/repos/stats')
@auth.oidc_auth
def repostatistics():
    if isTenant() or isTenantViewer() or isRepoViewer():
        statstmt="""select r.rid,r.orgname,r.reponame,r.tdate,r.viewcount,r.vuniques,r.clonecount,r.cuniques
                    from v_repostats r, v_adminuserrepos v
                    where r.rid=v.rid
                    and v.email=? """
        # IDEA: expand to limit number of selected days, e.g., past 30 days
        result = db.engine.execute(statstmt,flask.session['id_token']['email'])
        return render_template('repostats.html',stats=result)
    else:
        return render_template('notavailable.html', message="You are not authorized.") # should go to error or info page


# Show list of managed repositories
@app.route('/repos')
@app.route('/repos/list')
@auth.oidc_auth
def listrepos():
    if isTenant():
        result = db.engine.execute("select rid,orgname, reponame from v_adminrepolist where email=? order by rid asc",flask.session['id_token']['email'])
        return render_template('repolist.html',repos=result)
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



@app.route('/repos/dashboard')
@auth.oidc_auth
def dashboard():
    # print request.url_root
    #body={ "expiresIn": 3600, "webDomain" : "https://myportal.mybluemix.net" }
    body={ "expiresIn": 3600, "webDomain" : request.url_root }
    # print body
    ddeUri=DDE['api_endpoint_url']+'v1/session'
    res = requests.post(ddeUri, data=json.dumps(body) , auth=(DDE['client_id'], DDE['client_secret']), headers={'Content-Type': 'application/json'})
    # print res.text
    # print json.loads(res.text)['sessionId']
    # return render_template('dashboard.html',sessionInfo=json.loads(res.text))
    return render_template('notavailable.html')

# return the currently active user as csv file
@app.route('/data/user.csv')
@auth.oidc_auth
def generate_user():
    def generate(email):
        yield "user" + '\n'
        yield email + '\n'
    return Response(generate(flask.session['id_token']['email']), mimetype='text/csv')

# return the repository statistics for the current user as csv file
@app.route('/data/repostats.csv')
@auth.oidc_auth
def generate_repostats():
    if isTenant() or isTenantViewer():
        def generate():
            statstmt="""select r.rid,r.tdate,r.viewcount,r.vuniques,r.clonecount,r.cuniques
                        from v_repostats r, v_adminuserrepos v
                        where r.rid=v.rid
                        and v.email=? """
            result = db.engine.execute(statstmt,flask.session['id_token']['email'])
            yield "RID,TDATE,VIEWCOUNT,VUNIQUES,CLONECOUNT,CUNIQUES\n"
            for row in result:
                yield ','.join(map(str,row)) + '\n'
        return Response(stream_with_context(generate()), mimetype='text/csv')
    else:
        return render_template('notavailable.html', message="You are not authorized.")

@app.route('/data/repositories.csv')
@auth.oidc_auth
def generate_repolist():
    def generate():
        repolist_stmt="""select rid,orgname, reponame
                         from v_adminrepolist
                         where email=? order by rid asc"""
        result = db.engine.execute(repolist_stmt,flask.session['id_token']['email'])
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
