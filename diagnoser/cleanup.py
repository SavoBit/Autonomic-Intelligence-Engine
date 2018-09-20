#!/usr/bin/env python3

# Prototype impl. for monasca connector to load RAW.metrics

import json
import os
import sys
import time
import traceback

from monascaclient import client
from monascaclient.common import utils
from osc_lib import exceptions as osc_exc
from keystoneauth1.exceptions.http import Conflict
import requests


#api_version = '2_0'
# Keystone authentication
#user = utils.env('OS_USERNAME')
#passw = utils.env('OS_PASSWORD')
#proj_name = utils.env('OS_PROJECT_NAME')
#auth_url = utils.env('OS_AUTH_URL')
#monasca_url = utils.env('MONASCA_API_URL')
#region_name = utils.env('OS_REGION_NAME')

api_version = '2_0'
user = 'mini-mon'
passw = 'password'
proj_name = 'mini-mon'
auth_url = 'http://192.168.89.224:5000/v3'
monasca_url = 'http://192.168.89.224:8070/v2.0'
region_name = 'RegionOne'

auth_kwargs = {'username': user,
		'password': passw,
		'project_name': proj_name,
		'auth_url': auth_url,
                'user_domain_name': 'Default',
                'project_domain_name': 'Default'}

# Monasca Client constructor
monasca_client = client.Client(api_version, monasca_url, **auth_kwargs)



def delete_alarm(alarm_id):
    fields = {}
    fields['alarm_id'] = alarm_id
    try:
        body = monasca_client.alarm_definitions.delete(**fields)
    except osc_exc.ClientException as he:
        print('HTTPException code=%s message=%s' % (he.code, he.message))
    else:
        #Returns 204
        print(body)


def get_alarm_id(name):
    fields = {}
    fields['name'] = name
    id_ = None
    try:
        body = monasca_client.alarm_definitions.list(**fields)
        if len(body) is not 0:
            id_ = body[0]['id']
        print('Cleanup: get_alarm_id retreived id: {!r}'.format(id_))
    except:
        traceback.print_exc()

    return id_

def remove_task(name):
    headers = {'Content-type' : 'application/xml','Accept' : 'application/json'}
    task_url = 'http://192.168.89.225:9001/altaia/api/task/manager/tasks/'+name
    r = requests.delete(task_url, headers=headers)
    print (r.status_code)


def remove_tal(rulename, tenant="talhero"):
    headers = {'Content-type' : 'application/xml','Accept' : 'application/json'}
    task_url = 'http://192.168.89.128:18183/tal/engine/'+tenant+"/"+rulename
    r = requests.delete(task_url, headers=headers)
    print (r.status_code)


def enable_oldscripts(script, tenant="alksd"):
    headers = {'Content-type' : 'application/xml','Accept' : 'application/json'}
    task_url = 'http://192.168.89.128:18183/tal/engine/'+tenant
    r = requests.put(task_url+"/"+script+"/enable", headers=headers)
    print(task_url+"/"+script+"/enable")
    print(r.status_code)


def clean_after_loop(task_name, alarm_name, tal_name):
    print('Cleanup: beginning cleanup')
    id_ = get_alarm_id(alarm_name)
    if id_ is None:
        print('warning: Cleanup: unable to obtain alarm ID')
    else:
        print('Cleanup: removing alarm')
        delete_alarm(id_)
    print('Cleanup: removing Task')
    remove_task(task_name)
    print('Cleanup: removing Tal-Script')
    remove_tal(tal_name)
    print('Cleanup: done')


def check_script(name, tenant="alksd"):
    headers = {'Content-type' : 'application/xml','Accept' : 'application/json'}
    task_url = 'http://192.168.89.128:18184/tal/engine/'+tenant
    r = requests.get(task_url, headers=headers)
    if r.status_code  == 200:
        data = r.json()
        if data.get(name) == "enabled":
            return True 
        else:
            return False
    else:
        return False

if __name__ == '__main__':
    sys.path[0] = os.path.abspath(
            os.path.join(os.path.dirname(__file__), os.path.pardir))
    import diagnoser.config
    config = diagnoser.config.Config()
    sp = config.test_configurations.sp
    #metric_name = sp.metric_name
    clean_after_loop(sp.task_name, sp.alarm_name, sp.rule_name)


