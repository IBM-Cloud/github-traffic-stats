# Github Traffic Analytics: Combining serverless web app and eventing
This repository contains code based on this [IBM Cloud solution tutorial](https://cloud.ibm.com/docs/solution-tutorials?topic=solution-tutorials-serverless-github-traffic-analytics). In the tutorial, we create an application to automatically collect Github traffic statistics for repositories and provide the foundation for traffic analytics. Github only provides access to the traffic data for the last 14 days. If you want to analyze statistics over a longer period of time, you need to download and store that data yourself. The app and the serverless action discussed in the tutorial implement a multi-tenant-ready solution to manage repositories, automatically collect traffic data on a daily or weekly schedule, and to view and analyze the collected data.

The [original solution was based on Cloud Foundry for the web app and Cloud Functions for the automatic](https://github.com/IBM-Cloud/github-traffic-stats/tree/cloudfoundry), serverless collection of traffic data. The code has been modified into a single Python app. It runs as dockerized container within IBM Cloud Code Engine. The app can be accessed via its web interface as regular web app. Moreover, utilizing eventing, the app receives signals (time events) to automatically collect GitHub traffic data. If not active, IBM Cloud Code Engine automatically scales down the app.

![Architecture diagram](serverless-github-traffic-stats.png)

Flow:
1. User accesses the Python (web) app running in IBM Cloud Code Engine. This is to set up the managed GitHub repositories or to access the collected traffic data.
2. The app interacts with the IBM AppID service for authentication and user management and Db2 as database for user and GitHub traffic data.
3. A Code Engine ping subscription based contacts the Python app to signal a time event.
4. Based on the signaled event (3) or directed by an administrator (user), the Python app retrieves GitHub traffic data.


## Highlights
The app utilizes IBM Cloud AppID for authentication. It is based on OpenID Connect 2.0. The authenticated users are matched against profiles in the backend database for authorization. This allows partial data view and multi-tenancy.

Daily and weekly data view in tables and some basic charting are fed asynchronously using AJAX callbacks to the app and implemented data APIs.

![charting](screenshots/Charting.png)

## Database schema
The database schema, defined in [database.sql](backend/database.sql), can be graphically represented as (source in [Graphviz DOT notation](https://www.graphviz.org/documentation/) in [dbschema.gv.txt](dbschema.gv.txt)):

![](dbschema.png)


# License
See [LICENSE](LICENSE) for license information.


# Contribute / Contact Information
If you have found errors or some instructions are not working anymore, then please open an GitHub issue or, better, create a pull request with your desired changes.

You can find more tutorials and sample code at:
https://cloud.ibm.com/docs/solution-tutorials?topic=solution-tutorials-tutorials
