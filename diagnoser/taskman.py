#!/usr/bin/env python3


import json

import requests


def send_task(config, task_name, task_json):
    """
    Send an aggregation task to the Task Manager.

    """
    print('TaskManager: creating new task {!r}'.format(task_name))
    url = config.task_manager.task_url
    if not url.endswith('/'):
        url += '/'
    headers = {'content-type': 'application/json'}
    r = requests.post(url, data=json.dumps(task_json), headers=headers)
    if r.status_code == 201:
        print('TaskManager: task created')
        return
    if r.status_code != 409:
        print('error: TaskManager: unable to send task: {}\n{}'.format(
                r.status_code, r.text))
        return
    # r.status_code == 409:
    print('TaskManager: task already exists, updating')
    r = requests.put(
                url + task_name,
                data=json.dumps(task_json),
                headers=headers,
            )
    # TODO: report potential errors here
    print('TaskManager: received status code {}'.format(r.status_code))


