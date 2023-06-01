#!/usr/bin/env python3

import requests
import datetime
import csv
import json
import uuid
import os
import math

# add your PagerDuty api key below (read-only is all that is needed)
apiKey = 'YOUR_PAGERDUTY_API_KEY_GOES_HERE'

# this list holds all the reports that will run, remove any that you do not want
reports = ['users', 'teams', 'escalation_policies', 'schedules', 'services']

# To fix an error at Opsgenie import
# Error: "There is already one Team with same name"
# Opsgenie does not allow import of Escalation or Schedule with the same name of a Team
TEAMS = []

# function to build a report based on report type
def build_report(apiKey, reportType):

    offset = 0
    more = True
    data = []

    headers = {
        'Authorization': 'Token token=' + apiKey,
        'Accept': 'application/vnd.pagerduty+json;version=2',
        'Content-Type': 'application/json'
    }

    while (more == True):
        url = 'https://api.pagerduty.com/' + reportType + '?limit=100&offset=' + str(offset)

        response = requests.request('GET', url, headers=headers)

        data = data + response.json()[reportType]

        if (more == True):
            offset = offset + 100

        more = response.json()['more']
        #more = False

    """details = []
    for x in data:

            details.append({'id': x['id'],
                        'name': x['name']
                        })

    fileName = 'backup/pagerduty_' + reportType + datetime.datetime.now().strftime('_%Y-%m-%d') + '.csv'
    fields = list(details[0].keys())

    with open(fileName, 'w') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        writer.writeheader()
        writer.writerows(details)"""
    
    if reportType == 'users':
        for x in data:
            contact_methods = collect_user_contacts(apiKey, x['id'])
            x['contact_methods'] = contact_methods
    
    if reportType == 'schedules':
        for x in data:
            schedule_layers = collect_schedule_layers(apiKey, x['id'])
            x.update(schedule_layers)

    # adapt to Opsgenie compatible format
    data = opsgenie_compat_format(apiKey, reportType, data)

    for record in data:
        if (reportType == "escalation_policies"):
            path = 'backup/escalations/'
        else:
            path = 'backup/' + reportType + '/'
        fileName = str(uuid.uuid4()) + '.json'
        if not os.path.exists(path):
            os.makedirs(path)
        with open(path + fileName, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=4)

def collect_user_contacts(apiKey, user):
    
    headers = {
        'Authorization': 'Token token=' + apiKey,
        'Accept': 'application/vnd.pagerduty+json;version=2',
        'Content-Type': 'application/json'
    }

    url = 'https://api.pagerduty.com/users/' + user + '/contact_methods'
    
    response = requests.request('GET', url, headers=headers)

    return response.json()['contact_methods']

def collect_schedule_layers(apiKey, schedule):

    headers = {
        'Authorization': 'Token token=' + apiKey,
        'Accept': 'application/vnd.pagerduty+json;version=2',
        'Content-Type': 'application/json'
    }

    url = 'https://api.pagerduty.com/schedules/' + schedule

    response = requests.request('GET', url, headers=headers)

    return response.json()['schedule']

def opsgenie_compat_format(apiKey, reportType, data):

    global TEAMS

    match reportType:
        case 'users':
            users = []
            for x in data:
                userSet = {}
                userSet['username'] = x['email']
                userSet['fullName'] = x['name']
                if (x['role'] == 'limited_user'):
                    role = 'User'
                elif (x['role'] == 'user'):
                    role = 'Admin'
                elif (x['role'] == 'admin'):
                    #role = 'Owner'
                    #Owner role is not available for update through API
                    #Update it manually from the console afterwards
                    role = 'Admin'
                elif (x['role'] == 'restricted_access'):
                    role == 'limited_user'
                userSet['role'] = {
                    "name": role
                }
                userSet['timeZone'] = x['time_zone']
                userSet['blocked'] = False
                userSet['verified'] = False
                userContacts = []
                for y in x['contact_methods']:
                    type = y['type'].removesuffix('_contact_method')
                    if (type == 'phone'):
                        type = 'voice'
                    if (type == 'phone' or type == 'voice' or type == 'sms'):
                        toAddress = str(y['country_code']) + '-' + str(y['address'])
                    else:
                        toAddress = y['address']
                    contact_method = {
                        "to": toAddress,
                        "contactMethod": type,
                        "enabled": False
                    }
                    if (type in ['sms', 'phone', 'voice', 'email']):
                        userContacts.append(contact_method)
                userSet['userContacts'] = userContacts
                userRuleSet = []
                """users.append({
                    "user": userSet,
                    "notificationRuleList": userRuleSet
                })"""
                users.append({
                    "user": userSet
                })
            return users
        case 'teams':
            teams = []
            for x in data:
                teamSet = {}
                teamSet['name'] = x['name'].strip()
                teamSet['description'] = x['description'] or ""
                teams.append({"team": teamSet})
                # update global variable for future use in the function
                TEAMS.append(teamSet['name'])
            return teams
        case 'escalation_policies':
            escalationPolicies = []
            for x in data:
                escalationPolicySet = {}
                escalationPolicySet['name'] = x['name'].strip()
                # Resolve similar name conflict with team name
                if (TEAMS and escalationPolicySet['name'] in TEAMS):
                    escalationPolicySet['name'] = escalationPolicySet['name'] + ' EP'
                escalationPolicySet['description'] = x['description'] or ""
                # Watch out: escalation policies without teams
                if x['teams']:
                    escalationPolicySet['ownerTeam'] = {
                        # Hard coding to fetch the first team
                        # Watch out: if the same escalation policy is being used by more 
                        # than one team
                        "name": x['teams'][0]['summary'].strip()
                    }
                escalationDelay = 0
                escalationPolicySet['rules'] = []
                for index, value in enumerate(x['escalation_rules']):
                    if "deleted_at" in value['targets'][0]:
                        continue
                    escalationDelay = escalationDelay + value['escalation_delay_in_minutes']
                    recipientType = value['targets'][0]['type'].removesuffix('_reference')
                    if (recipientType == 'user'):
                        headers = {
                            'Authorization': 'Token token=' + apiKey,
                            'Accept': 'application/vnd.pagerduty+json;version=2',
                            'Content-Type': 'application/json'
                        }
                        url = 'https://api.pagerduty.com/users/' + value['targets'][0]['id']
                        response = requests.request('GET', url, headers=headers)
                        if not "user" in response.json():
                            raise ValueError("User does not exist.")
                        recipient = {
                            "type": recipientType,
                            # Watch out: using index to fetch from list
                            "username": response.json()['user']['email']
                        }
                    else:
                        # Resolve similar name conflict with team name
                        # expected recipientType == 'schedule'
                        scheduleName = value['targets'][0]['summary'].strip()
                        if (TEAMS and scheduleName in TEAMS):
                            scheduleName = scheduleName + ' SCHD'
                        recipient = {
                            "type": recipientType,
                            # Watch out: using index to fetch from list
                            "name": scheduleName
                        }
                    escalationPolicySet['rules'].append({
                        "condition": "if-not-acked",
                        "notifyType": "default",
                        "delay": {
                            "timeAmount": escalationDelay,
                            "timeUnit": "minutes"
                        },
                        "recipient": recipient
                    })
                escalationPolicies.append(escalationPolicySet)
            return escalationPolicies
        case 'schedules':
            schedules = []
            for x in data:
                scheduleSet = {}
                scheduleSet['name'] = x['name'].strip()
                # Resolve similar name conflict with team name
                if (TEAMS and scheduleSet['name'] in TEAMS):
                    scheduleSet['name'] = scheduleSet['name'] + ' SCHD'
                scheduleSet['description'] = x['description'] or ""
                scheduleSet['timezone'] = x['time_zone']
                scheduleSet['enabled'] = True
                # Watch out: schedules without teams
                if x['teams']:
                    scheduleSet['ownerTeam'] = {
                        # Hard coding to fetch the first team
                        # Watch out: if the same schedule is being used by more 
                        # than one team
                        "name": x['teams'][0]['summary'].strip()
                    }
                scheduleSet['rotations'] = []
                scheduleSetParticipants = []
                # Make sure to select "Layer 1", probably at the end
                if (x['schedule_layers'] and x['schedule_layers'][-1]['users']):
                    for index, value in enumerate(x['schedule_layers'][-1]['users']):
                        if "deleted_at" in value['user']:
                            continue
                        headers = {
                            'Authorization': 'Token token=' + apiKey,
                            'Accept': 'application/vnd.pagerduty+json;version=2',
                            'Content-Type': 'application/json'
                        }
                        url = 'https://api.pagerduty.com/users/' + value['user']['id']
                        response = requests.request('GET', url, headers=headers)
                        if not "user" in response.json():
                            raise ValueError("User does not exist.")
                        scheduleSetParticipants.append({
                            "type": "user",
                            "username": response.json()['user']['email']
                        })
                # Convert seconds into number of days (counting hours)
                # Determine rotation schedule: weekly/daily/hourly/error
                rotationLengthSecs = x['schedule_layers'][-1]['rotation_turn_length_seconds']
                if rotationLengthSecs >= 3600:
                    rotationHours =  rotationLengthSecs / 3600
                else:
                    rotationHours =  1 # defaults to 1
                
                if (rotationHours/24) % 7 == 0:
                    rotationType = "weekly"
                    rotationLength = int((rotationHours/24)/7)
                elif rotationHours % 24 == 0:
                    rotationType = "daily"
                    rotationLength = int(rotationHours/24)
                else:
                    rotationType = "hourly"
                    rotationLength = int(rotationHours)

                startDate = x['schedule_layers'][-1]['rotation_virtual_start']
                startDate = datetime.datetime.fromisoformat(startDate)
                # Watch out: convert datetime to UTC if necessary
                # Incoming PagerDuty datetime format: "2023-03-22T15:00:00-04:00"
                # Opsgenie documented datetime format:"2017-02-06T05:00:00Z"
                scheduleSet['rotations'].append({
                    "name": x['schedule_layers'][-1]['name'].strip(),
                    "startDate": x['schedule_layers'][-1]['rotation_virtual_start'],
                    "type": rotationType,
                    "length": rotationLength,
                    "participants": scheduleSetParticipants
                })
                schedules.append({"schedule": scheduleSet})
            return schedules
        case 'services':
            services = []
            for x in data:
                serviceSet = {}
                serviceSet['name'] = x['name'].strip()
                serviceSet['description'] = x['description'] or ""
                services.append(serviceSet)
            return services
        case default:
            data = data
            return data

def pluck(lst, key):
  return [x.get(key) for x in lst]

#  build report for each report type
for report in reports:
    build_report(apiKey, report)
