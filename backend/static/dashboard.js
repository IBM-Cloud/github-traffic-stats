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

  createDDEDisplaySession().then(function(sessionInfo) {
    sessionCode = sessionInfo.sessionData.sessionCode;
    dbSpec=sessionInfo.dashboard;
    // if debugging is needed:
    // console.log(JSON.stringify(dbSpec));
    return sessionCode, dbSpec;
  }, function(err) {
    sessionObj = null;
    containerDiv.innerHTML = '<h2>Failed to create session</h2>Please check your application credentials.';
  }).then(function() {
    window.myapi = new CognosApi({
      // initialize Cognos API, static DDE URL for now
      cognosRootURL: 'https://dde-us-south.analytics.ibm.com/daas/',
      sessionCode: sessionCode,
      node: containerDiv
    });
    window.myapi.initialize().then(function() {
      console.log('API created successfully.');
    }, function(err) {
      console.log('Failed to create API. ' + err.message);
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

    })
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

  // retrieve session code and table definition
  createDDESession().then(function(sessionInfo) {
    sessionCode = sessionInfo.sessionData.sessionCode;
    csvStats= sessionInfo.csvStats;
    return sessionCode, csvStats;
  }, function(err) {
    sessionObj = null;
    containerDiv.innerHTML = '<h2>Failed to create session</h2>Please check your application credentials.';
  }).then(function() {
    // initialize Cognos API (DDE)
    window.myapi = new CognosApi({
      cognosRootURL: 'https://dde-us-south.analytics.ibm.com/daas/',
      sessionCode: sessionCode,
      node: document.getElementById('ddeDashboard')
    });
    window.myapi.initialize().then(function() {
      console.log('API created successfully.');
    }, function(err) {
      console.log('Failed to create API. ' + err.message);
    }).then(function() {
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
    });
  }
