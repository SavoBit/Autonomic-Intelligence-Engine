#!/usr/bin/env python3


"""
Connector for interfacing to Monasca.

"""


import collections
import json
import sys
import traceback
import uuid

import keystoneauth1.exceptions
import keystoneauth1.identity
import keystoneauth1.session

import monascaclient
import monascaclient.client

import osc_lib.exceptions


class RealMonascaClient:

    def __init__(self, config):
        self.auth = keystoneauth1.identity.Password(
                    auth_url=config.monasca.auth_url,
                    username=config.monasca.username,
                    password=config.monasca.password,
                    project_name=config.monasca.project_name,
                    user_domain_id=config.monasca.user_domain_id,
                    project_domain_id=config.monasca.project_domain_id,
                )
        self.session = keystoneauth1.session.Session(auth=self.auth)
        self.client = monascaclient.client.Client(
                    api_version='2_0',
                    endpoint=config.monasca.endpoint,
                    session=self.session,
                    #auth_url=config.monasca.auth_url,
                    #username=config.monasca.username,
                    #password=config.monasca.password,
                    #project_name=config.monasca.project_name,
                    #user_domain_id=config.monasca.user_domain_id,
                    #project_domain_id=config.monasca.project_domain_id,
                )

    def close(self):
        pass

    def get_notification_id(self):
        try:
            body = self.client.notifications.list()
            return body[0]['id']
        except:
            print('error: MonascaClient: acquiring notification ID failed')
            traceback.print_exc()

    def create_alarm(self, name, severity, description, dimensions, expression):
        try:
            body = self.client.alarm_definitions.create(
                        name=name,
                        severity=severity,
                        description=description,
                        alarm_actions=[self.get_notification_id()],
                        expression=expression,
                        match_by=dimensions,
                    )
            print('MonascaClient: alarm {!r} created:'.format(body['id']))
            print(json.dumps(body, indent=4))
            return body['id']
        except keystoneauth1.exceptions.http.Conflict as e:
            print('warning: MonascaClient:')
            traceback.print_exc()
            #name = name+"_2"
            #print('Changing name to: {}'.format(name))
            #create_alarm(name, dimensions,expression)
        #except:
        #    print('error: MonascaClient: unable to create alarm {!r}'.format(name))
        #    traceback.print_exc()

    def delete_alarm(self, alarm_id):
        try:
            body = self.client.alarm_definitions.delete(alarm_id=alarm_id)
            print('MonascaClient: alarm {!r} deleted:'.format(alarm_id))
            # returns 204
            print(json.dumps(body, indent=4))
        except osc_lib.exceptions.ClientException as e:
            print('error: MonascaClient: unable to delete alarm {!r}, received ClientException: code={!r}, message={!r}'.format(alarm_id, e.code, e.message))
            traceback.print_exc()


class FakeMonascaClient:

    def __init__(self, config):
        if config.monasca.to_file == '-':
            self.output = sys.stdout
            self.closing = False
        else:
            self.output = open(config.monasca.to_file, 'w')
            self.closing = True
        self.notification_id = str(uuid.uuid4())
        self.alarms = {}

    def close(self):
        if self.closing:
            self.output.close()

    def get_notification_id(self):
        return self.notification_id

    def create_alarm(
            self, name, severity, description, dimensions, expression):
        alarm_id = str(uuid.uuid4())
        definition = collections.OrderedDict([
                    ('name', name),
                    ('severity', severity),
                    ('description', description),
                    ('alarm_actions', [self.get_notification_id()]),
                    ('expression', expression),
                    ('match_by', dimensions),
                ])
        self.alarms[alarm_id] = definition
        self.output.write(
                'MonascaClient: alarm {!r} created:\n'.format(alarm_id))
        self.output.write('{}\n'.format(json.dumps(definition, indent=4)))
        return alarm_id

    def delete_alarm(self, alarm_id):
        if alarm_id in self.alarms:
            del self.alarms[alarm_id]
            self.output.write(
                    'MonascaClient: alarm {!r} deleted\n'.format(alarm_id))
        else:
            self.output.write('error: MonascaClient: unable to delete alarm '
                    '{!r}\n'.format(alarm_id))


def MonascaClient(config):
    if config.monasca.to_file is None:
        return RealMonascaClient(config)
    else:
        return FakeMonascaClient(config)


