
# PagerDuty export Opsgenie
A simple python script to export data from PagerDuty with compatibility to use in OpsGenie Configuration Backup. It exports all users, teams, escalation policies, schedules, and services in a PagerDuty account.

### Usage

 - Update line 8 with your PagerDuty API key.

    apiKey = 'YOUR_PAGERDUTY_API_KEY_GOES_HERE'

 - Remove or add any PagerDuty objects on line 11. You'll generate a CSV report for any object listed.

    reports = ['users', 'teams', 'escalation_policies', 'schedules', 'services']

***Note: Only 'users', 'teams', 'escalation_policies', 'schedules', and 'services' have been tested.***

***Disclaimer: Script is adjusted to adapt with certain use cases according to our PagerDuty settings. Use at your own risk.***
