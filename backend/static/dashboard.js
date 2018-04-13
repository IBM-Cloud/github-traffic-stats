// Functions to deal with DDE embedding

function iniDashboard(node) {

  myCognosApi = new CognosApi( {
            cognosRootURL: "https://dde-us-south.analytics.ibm.com/daas/",
            node: node,
            sessionCode: sessioncode
           });


 myCognosApi.initialize().then(() => {
	// create a new dashboard through the dashboard factory
	myCognosApi.dashboard.createNew();
})

}


function createDDESession() {
  var xhttp = new XMLHttpRequest();
    xhttp.open("POST", "/api/v1/dashboard_session", true);
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


function newDDESession() {
    			var containerDiv = document.getElementById('ddeDashboard');
          var sessionCode;
          var csvStats;
          var csvRepos;


    			createDDESession().then(function(sessionInfo) {
            sessionCode = sessionInfo.sessionData.sessionCode;
            csvStats= sessionInfo.csvStats;
            csvRepos= sessionInfo.csvRepos;
            return sessionCode, csvStats, csvRepos;
    			}, function(err) {
    				sessionObj = null;
    				containerDiv.innerHTML = '<h2>Failed to create session</h2>Please check your application credentials.';
    			}).then(function() {
            myapi = new CognosApi({
              cognosRootURL: 'https://dde-us-south.analytics.ibm.com/daas/',
              sessionCode: sessionCode,
              node: document.getElementById('ddeDashboard')
            });
            myapi.initialize().then(function() {
              console.log('API created successfully.');
              }, function(err) {
                console.log('Failed to create API. ' + err.message);
              }).then(function() {

              myapi.dashboard.createNew().then(
                function(dashboardAPI) {
                  console.log('Dashboard created successfully.');
                window.dashboardAPI = dashboardAPI;
                window.dashboardAPI.addSources([{
                  module: csvStats,
                  name: 'Traffic CSV',
                  id: 'Repostats'
                }]);
                window.dashboardAPI.addSources([{
                  module: csvRepos,
                  name: 'Repo CSV',
                  id: 'Repolist'
                }]);
              }
            ).catch(
              function(err) {
                console.log('User hit cancel on the template picker page.');
              }
            );})
            });


/*
          window.api = new CognosApi({
          cognosRootURL: 'https://dde-us-south.analytics.ibm.com/daas/',
          sessionCode: sessionObj.sessionCode,
          node: document.getElementById('ddeDashboard')
          });
          window.api.initialize().then(function() {
          console.log('API created successfully.');
          }, function(err) {
          console.log('Failed to create API. ' + err.message);
          });


          window.api.dashboard.createNew().then(
    function(dashboardAPI) {
        console.log('Dashboard created successfully.');
        window.dashboardAPI = dashboardAPI;
    }
).catch(
    function(err) {
        console.log('User hit cancel on the template picker page.');
    }
);
*/
    		}
