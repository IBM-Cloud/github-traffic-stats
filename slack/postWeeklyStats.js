// Compile weekly GitHub statistics and post them to Slack channel
//
// Parameters (can be bound):
// emailid: email for stats database user (see tutorial)
// webhook: Slack URI of incoming webhook
// channel: the channel to post into
//
// Written by Henrik Loeser


// require packages, packages are part of IBM Cloud Functions nodejs:8 environment
var ibmdb = require('ibm_db');
var rp = require('request-promise');
var moment = require('moment');



// fetch the weekly stats from previous work week
function fetchWeeklyStats(dsn, emailid, webhook, channel) {
  // predefined SQL statements
  const weeklySql=`select r.rid,orgname,reponame,
                         sum(viewcount) as viewcount, sum(vuniques) as vuniques,
                         sum(clonecount) as clonecount, sum(cuniques) as cuniques
                  from v_repostats r, v_adminuserrepos v
                  where r.rid=v.rid
                  and tdate between this_week(current date - 7 days)+1 and (this_week(current date))
                  and v.email=?
                  group by r.rid, orgname, reponame
                  order by vuniques desc
                  fetch first 25 rows only`;
  const repoCountSql=`select count(rid) as repocount
                      from v_adminuserrepos
                      where email=?`;
 
  
try {
  // connect to database
  var conn=ibmdb.openSync(dsn);
   
  // retrieve weekly stats
  var data=conn.querySync(weeklySql,[emailid]);
  // retrieve repository count
  var repoCount=conn.querySync(repoCountSql,[emailid]);
  // close the connection
  conn.closeSync();

  // Compose the strings for the message and attachment
  //
  // We need the work week string for the previous week
  var workweek=moment().subtract(7, 'days').format("YYYY-WW");

  // the repository count
  var resString="*Total repositories*: "+repoCount[0]['REPOCOUNT'];
      resString+="\nSee more at https://cps-github-stats.mybluemix.net/";
  // format the data for the attachment
  var dataString="```REPONAME/ORGNAME,VIEWCOUNT,VUNIQUES,CLONECOUNT,CUNIQUES:\n";
  // add each result row (if any)
  for (var i=0;i<data.length;i++) {
      dataString+=data[i]['ORGNAME']+"/"+data[i]['REPONAME']+","
                 +data[i]['VIEWCOUNT']+","+data[i]['VUNIQUES']
                 +","+data[i]['CLONECOUNT']+","+data[i]['CUNIQUES']+"\n";
    }
    dataString+="```";
    
 } catch (e) {
     return { dberror : e }
 }

 // now compose the payload and post it to Slack
 var payload= {
    text : resString,
    channel : channel,
    attachments: [
       {
         fallback: "Weekly top 25 repositories",
         title: "Top 25 repositories by unique views ("+workweek+")",
         mrkdwn_in: ["text"],
         text : dataString
        }
        ]
      };
 
 var options = {
  method: 'POST',
  uri: webhook,
  body: payload,
  json: true // Automatically stringifies the body to JSON
};

rp(options)
  .then(function (parsedBody) {
      return {message : "ok, message posted"};
  })
  .catch(function (err) {
      return {message : "Failed to post to Slack"};
  });
}

function main({emailid, webhook, channel, __bx_creds: {dashDB:{dsn}}}) {
	return fetchWeeklyStats(dsn,emailid, webhook, channel);
}
