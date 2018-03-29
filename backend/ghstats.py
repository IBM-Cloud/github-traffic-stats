import flask, os, json, datetime
import github
from flask import Flask, jsonify,redirect,request,render_template, url_for, Response, stream_with_context

from flask_pyoidc.flask_pyoidc import OIDCAuthentication

from sqlalchemy import Column, Table, Integer, String, select, ForeignKey
from sqlalchemy.orm import relationship, backref
#from sqlalchemy.ext.declarative import declarative_base
from flask_sqlalchemy import SQLAlchemy


app = Flask(__name__)

if 'VCAP_SERVICES' in os.environ:
   dbInfo = json.loads(os.environ['VCAP_SERVICES'])['dashDB'][0]
   dbURI = dbInfo["credentials"]["uri"]
   app.config['SQLALCHEMY_DATABASE_URI']=dbURI
   app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=False

# we are local, so load info from a file
else:
   app.config.from_pyfile('server.cfg')
   # Credentials are read from a file
   with open('config.json') as confFile:
       appIDconfig=json.load(confFile)
       provider_config=appIDconfig['provider']
       client_info=appIDconfig['client']



# See http://flask.pocoo.org/docs/0.12/config/
app.config.update({'SERVER_NAME': '0.0.0.0:5000',
                   'SECRET_KEY': 'my_secret_key',
                   'PREFERRED_URL_SCHEME': 'http',
                   #'SESSION_PERMANENT': True, # turn on flask session support
                   'PERMANENT_SESSION_LIFETIME': 2592000, # session time in seconds (30 days)
                   'DEBUG': True})

auth = OIDCAuthentication(app, provider_configuration_info=provider_config, client_registration_info=client_info,userinfo_endpoint_method=None)


db = SQLAlchemy(app, session_options={'autocommit': True})


class User(db.Model):
    __tablename__ = 'users'
    uid = Column(Integer, primary_key=True)
    fname = Column(String)
    lname = Column(String)
    email = Column(String)
    ghuser = Column(String)
    ghtoken = Column(String)

class Repo(db.Model):
    __tablename__ = 'repos'
    rid = Column(Integer, primary_key=True)
    rname = Column(String)
    ghserverid = Column(Integer)
    ownerid = Column(Integer)
    schedule = Column(Integer)

    @property
    def serialize(self):
        return {
           'id'         : self.rid,
           'rname'      : self.rname,
           'ownerid'    : self.ownerid
           }

class AdminUser(db.Model):
    __tablename__ = 'adminusers'
    aid = Column(Integer, primary_key=True)
    auser = Column(String)
    email = Column(String)



def alchemyencoder(obj):
    """JSON encoder function for SQLAlchemy special classes."""
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    elif isinstance(obj, decimal.Decimal):
        return float(obj)

def setuserrole(email=None):
    result = db.engine.execute("select role from adminroles ar, adminusers au where ar.aid=au.aid and au.email=?",email)
    for row in result:
        flask.session['userrole']=row[0]
        # there should be exactly one matching row
        return row[0]
    # or no row at all
    flask.session['userrole']=None
    return None


# Has the user the role of administrator?
def isAdministrator():
    return bool(flask.session['userrole'] & 1)

# Has the user the role of system maintainer?
def isSysMaintainer():
    return bool(flask.session['userrole'] & 1 + flask.session['userrole'] & 2)

# Has the user the role of tenant?
def isTenant():
    return bool(flask.session['userrole'] & 4)

# Has the user the role of tenant stats viewer?
def isTenantViewer():
    return bool(flask.session['userrole'] & 8)


@app.route('/')
def index():
    return render_template('index.html')


# have "unprotected" page with instructions
# from there go to protected page, grab email and other info
# to populate db after creating the SQLALCHEMY_DATABASE_URI

# could split string by semicolon and execute each stmt individually

@app.route('/admin/initialize-app')
def initializeApp():
    return render_template('initializeapp.html')

@app.route('/admin/initialize-app')
@auth.oidc_auth
def firststep():
    return render_template('firststep.html')


@app.route('/admin/secondstep', methods=['POST'])
@auth.oidc_auth
def secondstep():
    print "hello"
    print flask.session['id_token']['email']
    username=request.form['username']
    ghuser=request.form['ghuser']
    ghtoken=request.form['ghtoken']
    dbstmtstring=None
    with open('database.sql') as dbfile:
        dbstmtstring=dbfile.read()
        dbfile.close()
    dbstatements=dbstmtstring.replace('\n', ' ').split('@@')
    # connection = db.engine.connect()
    # trans = connection.begin()
    # try:
    #     for stmt in dbstatements:
    #         connection.execute(stmt)
    #connection.execute("insert into adminusers (aid, auser, email) values(?,?,?)", 100, username, flask.session['id_token']['email'])
    #connection.execute("insert into users (uid, ghuser, ghtoken) values(?,?,?)", 100, ghuser, ghtoken)
    #connection.execute("insert into adminroles (aid, role) values(?,?)", 100, 5)
    # Adminuser has tentant role for the tenant (user)
    #connection.execute("insert into adminuserreporoles (aid, uid, role) values(?,?,?)", 100, 100, 4)
    #     trans.commit()
    # except:
    #     trans.rollback()
    #     raise
    return jsonify(stmts=dbstatements)

@app.route('/repos/dashboard')
@auth.oidc_auth
def dashboard():
    return render_template('dashboard.html')



@app.route('/login')
@auth.oidc_auth
def login():
    setuserrole(flask.session['id_token']['email'])
    return render_template('welcome.html',id=flask.session['id_token'], role=flask.session['userrole'])

@app.route('/welcome')
@auth.oidc_auth
def index2():
    return "Welcome, "+flask.session['id_token']['email']


@app.route('/logout')
@auth.oidc_logout
def logout():
    flask.session['userrole']=None
    return redirect(url_for('index'))

@app.route('/admin/newuser')
@auth.oidc_auth
def newuser():
    return render_template('newuser.html')




@app.route('/admin/systemlog')
@auth.oidc_auth
def systemlog():
    if isSysMaintainer() or isAdministrator():
        result = db.engine.execute("select uid, completed, numrepos, state from systemlog where completed >(current date - 21 days) order by completed desc, uid asc")
        return render_template('systemlog.html',logs=result)
    else:
        return "no logs" # should go to error or info page


@app.route('/repos/list')
@auth.oidc_auth
def listrepos():
    if isTenant():
        result = db.engine.execute("select rid,orgname, reponame from v_adminrepolist where email=? order by rid asc",flask.session['id_token']['email'])
        return render_template('repolist.html',repos=result)
    else:
        return "no repos" # should go to error or info page

@app.route('/repos/newrepo', methods=['POST'])
@auth.oidc_auth
def newrepo():
    if isTenant():
        # Access form data from app
        orgname=request.form['orgname']
        reponame=request.form['reponame']
        # Log to stdout stream
        print orgname

        # could check if repo exists
        # but skipping to reduce complexity

        connection = db.engine.connect()
        trans = connection.begin()
        try:
            uid=None
            aid=None
            rid=None
            orgid=None
            ghstmt="""select aurr.uid, au.aid,u.ghuser,u.ghtoken
                      from  adminuserreporoles aurr, adminusers au, adminroles ar, users u where ar.aid=au.aid
                      and aurr.aid=au.aid
                      and u.uid=aurr.uid
                      and bitand(aurr.role,4)>0
                      and au.email=?"""
            githubinfo = connection.execute(ghstmt,flask.session['id_token']['email'])
            for row in githubinfo:
                uid=row['uid']
                aid=row['aid']
            orgidinfo = connection.execute("select uid from ghusers where username=?",orgname)
            for row in orgidinfo:
                orgid=row['uid']
            if orgid is None:
                neworgidinfo = connection.execute("select uid from new table (insert into ghusers(username) values(?))",orgname)
                for row in neworgidinfo:
                        orgid=row['uid']
            repoid = connection.execute("select rid from new table (insert into repos(rname,ghserverid,ownerid,schedule) values(?,?,?,?))",reponame,1,orgid,0)
            for row in repoid:
                rid=row['rid']
            repoid = connection.execute("insert into userrepos values(?,?)",uid,rid)
            trans.commit()
        except:
            trans.rollback()
            raise

        # need to check if org exists
        # need to insert userrepos: uid, rid

        return jsonify(message="Your new repo ID: "+str(rid))
    else:
        return jsonify(message="Error: no repository added") # should go to error or info page



@app.route('/datatest')
@auth.oidc_auth
def datatest():
    return render_template('data.html',
    	   items=User.query.all() )

@app.route('/datatest2')
@auth.oidc_auth
def datatest2():
    return render_template('data2.html',
    	   reposs=Repo.query.all() )

@app.route('/datatest3')
@auth.oidc_auth
def datatest3():
    return jsonify(json_list=[i.serialize for i in Repo.query.all()])

@app.route('/repos/stats')
@auth.oidc_auth
def repostatistics():
    result = db.engine.execute("select r.rid,r.orgname,r.reponame,r.tdate,r.viewcount,r.vuniques,r.clonecount,r.cuniques from repostats r, v_adminuserrepos v where v.email=? and r.rid=v.rid",flask.session['id_token']['email'])
    #result = db.engine.execute("select username, rname, r.rid, tdate, viewcount, vuniques, clonecount, cuniques from repotraffic rt, ghusers gu, repos r where r.ownerid=gu.uid and rt.rid=r.rid order by tdate desc, 3 asc")
    return render_template('repostats.html',stats=result)

@app.route('/datatest5')
@auth.oidc_auth
def datatest5():
    result = db.engine.execute("select r.rid,r.orgname,r.reponame,r.tdate,r.viewcount from repostats r, v_adminuserrepos v where v.email=? and r.rid=v.rid",flask.session['id_token']['email'])
    return json.dumps([dict(r) for r in result],default=alchemyencoder)


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
    def generate():
        result = db.engine.execute("select r.rid,r.orgname,r.tdate,r.viewcount from repostats r, v_adminuserrepos v where v.email=? and r.rid=v.rid",flask.session['id_token']['email'])
        for row in result:
            yield ','.join(map(str,row)) + '\n'
    return Response(stream_with_context(generate()), mimetype='text/csv')

@auth.error_view
def error(error=None, error_description=None):
    return jsonify({'error': error, 'message': error_description})


port = os.getenv('PORT', '5000')
if __name__ == "__main__":
	app.run(host='0.0.0.0', port=int(port))
