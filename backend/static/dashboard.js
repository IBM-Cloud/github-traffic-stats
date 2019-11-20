// Functions to deal with embedding DDE dashboards
// Written by Henrik Loeser, hloeser@de.ibm.com

// Call server to set up a session for displaying a canned dashboard
function createDDEDisplaySession() {
  var xhttp = new XMLHttpRequest();
  xhttp.open("POST", "/api/v1/dashboard_display_session", true);
  return new Promise(function(resolve, reject) {
    xhttp.onreadystatechange = function() {
      if (this.readyState == 4) {
        if (this.status == 201) {
          resolve(JSON.parse(this.responseText));
        } else {
          reject(new Error(this.statusText));
        }
      }
    };
    xhttp.send();
  });
}


// Perform steps to initialize and bring up canned dashboard
function cannedDDESession() {
  var containerDiv = document.getElementById('ddeDashboard');
  var sessionCode;
  var dbSpec;
  var cognosRootURL;

  createDDEDisplaySession().then(function(sessionInfo) {
    sessionCode = sessionInfo.sessionData.sessionCode;
    dbSpec=sessionInfo.dashboard;
    cognosRootURL=sessionInfo.ddeAPIUrl;
    // if debugging is needed:
    // console.log(JSON.stringify(dbSpec));
    return sessionCode, dbSpec,cognosRootURL;
  }, function(err) {
    sessionObj = null;
    containerDiv.innerHTML = '<h2>Failed to create session</h2>Please check your application credentials.';
  }).then(function() {
    window.myapi = new CognosApi({
      // initialize Cognos API
      cognosRootURL: cognosRootURL,
      sessionCode: sessionCode,
      node: containerDiv
    });
    window.myapi.initialize().then(function() {
      console.log('API created successfully.');
    }).then(function() {
      // open an existing dashboard
      // the spec was obtained from the app server
      window.myapi.dashboard.openDashboard({
        dashboardSpec: dbSpec
      }).then(
        function(dashboardAPI) {
          console.log('Dashboard created successfully.');
          window.dashboardAPI = dashboardAPI;
        }
      ).catch(
        function(err) {
          console.log(err);
        }
      );
    }).catch(function(err) {
      console.log('Failed to create API. ' + err.message);
    });
  });
}

// Call server to set up a session for creating a new dashboard
function createDDESession() {
  var xhttp = new XMLHttpRequest();
  xhttp.open("POST", "/api/v1/dashboard_edit_session", true);
  return new Promise(function(resolve, reject) {
    xhttp.onreadystatechange = function() {
      if (this.readyState == 4) {
        if (this.status == 201) {
          resolve(JSON.parse(this.responseText));
        } else {
          reject(new Error(this.statusText));
        }
      }
    };
    xhttp.send();
  });
}

// Perform steps to initialize and create a new dashboard
function newDDESession() {
  var containerDiv = document.getElementById('ddeDashboard');
  var sessionCode;
  var csvStats;
  var cognosRootURL;

  // retrieve session code and table definition
  createDDESession().then(function(sessionInfo) {
    sessionCode = sessionInfo.sessionData.sessionCode;
    csvStats= sessionInfo.csvStats;
    cognosRootURL= sessionInfo.ddeAPIUrl;
    return sessionCode, csvStats, cognosRootURL;
  }, function(err) {
    sessionObj = null;
    containerDiv.innerHTML = '<h2>Failed to create session</h2>Please check your application credentials.';
  }).then(function() {
    // initialize Cognos API (DDE)
    window.myapi = new CognosApi({
      cognosRootURL: cognosRootURL,
      sessionCode: sessionCode,
      node: document.getElementById('ddeDashboard')
    });
    window.myapi.initialize().then(function() {
      console.log('API created successfully.');
    })
    .then(function() {
      // create new dashboard and add table as source
      window.myapi.dashboard.createNew().then(
        function(dashboardAPI) {
          console.log('Dashboard created successfully.');
          window.dashboardAPI = dashboardAPI;
          // GitHub traffic data as CSV-based source
          // the definition was retrieved from our app server
          window.dashboardAPI.addSources([{
            module: csvStats,
            name: 'Traffic CSV',
            id: 'Repostats'
          }]);
        }
      ).catch(
        function(err) {
          console.log('User hit cancel on the template picker page.');
        }
      );})
    })
    .catch(function(err) {
      console.log('Failed to create API. ' + err.message);
    });
  }
