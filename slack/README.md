# Automated reporting of GitHub statistics to Slack
This directory contains files to allow automated reporting of GitHub statistics to Slack. It utilizes IBM Cloud Functions (ICF) and its alarm package to set up weekly invocation of an ICF action. That action retrieves the relevant data for the just ended workweek from Db2, composes a mesage with attachment and posts that report to a designated Slack channel.

![](/screenshots/GitHubStatsBot.png)

### Setup
See the Slack documentation on [incoming webhooks](https://api.slack.com/incoming-webhooks) on how to set up a Slack app based on a webhook. You may need permission or authorization to install such an app into your Slack workspace. Follow the instructions until you have an URI for the webhook and have installed the app into the desired channel.

Copy the file **slackSetup.template.sh** to **slackSetup.sh**. Replace the parameter values for the incoming webhook, Slack channel, and emailid to match your environment. Now run the script to
 * create a new IBM Cloud Functions package
 * create an action within that package
 * bind the Db2 service credentials to that action
 * bind the parameters (that you changed above) to the package
 * create a weekly alarm
 * create a rule to kick off the action once the alarm has fired
  
By default, the alarm fires on Monday noon UTC. The data for the just ended, previous workweek is fetched. Only the top 25 repositories by unique view count are retrieved and posted.