#!/usr/bin/env python3


import collections
import datetime
import itertools
import json
import math
import operator
import os
import re
import threading
import time
import traceback
import uuid
import xml.dom.minidom
import xml.etree.cElementTree

import pandas as pd

import diagnoser.aggregation
import diagnoser.cleanup
import diagnoser.kafka
import diagnoser.modeldb
import diagnoser.monasca
import diagnoser.neatmodeltrans
import diagnoser.neattools
import diagnoser.profiler
import diagnoser.talcom
import diagnoser.taskman
import diagnoser.tools


PRINT_EVERY_N_REPORTS = 2**4


def start(config, kafka_consumer, cassandra_client):

    print('Diagnoser: initializing')

    c_and_c_ip = None
    zombie_ips = []
    last_neat_run = datetime.datetime(1, 1, 1)
    neat_thread = threading.Thread()
    profiling_thread = threading.Thread()
    interface_lock = threading.Lock()

    print('Diagnoser: listening to topics {!r} on Kafka'.format(config.kafka.topics))

    c = 0
    for data in kafka_consumer:
        c += 1
        if PRINT_EVERY_N_REPORTS != 0 and c % PRINT_EVERY_N_REPORTS == 0:
            print('Diagnoser: received {} reports from Kafka'.format(c))
        if diagnoser.tools.getitemitem(
                    data,
                    ['dataDefinition', 'metadata', 'sensor'],
                    None,
                ) == 'SNORT':
            new_ip_received = False
            timestamp = diagnoser.tools.getitemitem(
                        data,
                        ['timestamp'],
                        None,
                    )
            srcIpList = diagnoser.tools.getitemitem(
                        data,
                        ['dataDefinition', 'listSrcIP'],
                        [],
                    )
            dstIp = diagnoser.tools.getitemitem(
                        data,
                        ['dataDefinition', 'ccServerIP'],
                        None,
                    )
            if dstIp is not None and c_and_c_ip is None:
                new_ip_received = True
                c_and_c_ip = dstIp
                print('Diagnoser: received c&c label: {}'.format(dstIp))
            for ip in srcIpList:
                if ip[0] not in zombie_ips:
                    new_ip_received = True
                    zombie_ips.append(ip[0])
                    print('Diagnoser: received zombie label: {}'.format(ip[0]))
            if (c_and_c_ip is not None and
                    len(zombie_ips) >= config.test_configurations.sp.max_zombie_ips and
                    not neat_thread.is_alive() and
                    datetime.datetime.utcnow() - last_neat_run >= datetime.timedelta(minutes=5)):
                # The list of botnet IPs can be overridden via the test
                # configuration.
                if config.test_configurations.sp.c_and_c_ip is not None:
                    c_and_c_ip = config.test_configurations.sp.c_and_c_ip
                if config.test_configurations.sp.zombie_ips is not None:
                    zombie_ips = config.test_configurations.sp.zombie_ips.copy()
                print('Diagnoser: c&c ip for SP: {}'.format(c_and_c_ip))
                print('Diagnoser: known zombie ips for SP: {}'.format(
                        ', '.join(zombie_ips)))
                print('Diagnoser: running NEAT for SP')
                # the default arguments capture the current values of the local variables
                neat_thread = threading.Thread(target=lambda config=config, cassandra_client=cassandra_client, c_and_c_ip=c_and_c_ip, zombie_ips=zombie_ips, timestamp=timestamp, interface_lock=interface_lock: diagnoser.neattools.run_sp_neat(config, cassandra_client, c_and_c_ip, zombie_ips, timestamp, interface_lock))
                neat_thread.start()
                c_and_c_ip = None
                zombie_ips = []
        if not profiling_thread.is_alive() and diagnoser.tools.getitemitem(
                    data,
                    ['dataDefinition', 'alarmDescription'],
                    None,
                ) == 'QoS Degradation' and diagnoser.tools.getitemitem(
                    data,
                    ['dataDefinition', 'newState'],
                    None,
                ) == 'OK':
            timestamp = diagnoser.tools.getitemitem(
                        data,
                        ['timestamp'],
                        None,
                    )
            service_id = diagnoser.tools.getitemitem(
                        data,
                        ['dataDefinition', 'metrics', 0, 'dimensions', 'serviceID'],
                        None,
                    )
            def sh_data_monitor(config=config, interface_lock=interface_lock, cassandra_client=cassandra_client, timestamp=timestamp, service_id=service_id):
                max_iterations = 10
                sleep_time = 30
                min_data = 60
                anomaly_threshold = .25
                for i in range(max_iterations):
                    if i != 0:
                        time.sleep(sleep_time)
                    with interface_lock:
                        data = diagnoser.profiler.load_data(
                                    cassandra_client,
                                    config.test_configurations.sh.resource_types,
                                    config.test_configurations.sh.raw_data_columns,
                                    service_id,
                                    config.test_configurations.sh.data_ranges,
                                    config.test_configurations.sh.data_collections,
                                    timestamp=timestamp,
                                )['test0']
                    data_by_app_id = data.groupby('resourcedescription.app_id')
                    app_ids = list(data_by_app_id.groups)
                    if len(app_ids) < 2:
                        print('Not enough appIDs: {}'.format(app_ids))
                        continue
                    with interface_lock:
                        app_id = diagnoser.tools.getHigherVersionID(app_ids)
                    data = data_by_app_id.get_group(app_id)
                    data.set_index('timestamp', inplace=True)
                    data = data.resample('S').last().fillna(method='pad')
                    data.reset_index(inplace=True)
                    print(data)
                    print('APP ID IS: {!r}'.format(app_id))
                    if len(data) < min_data:
                        continue
                    alarm_id = "dd062e1f-f0a4-45c6-809b-a9071e9f2dbb"
                    anomaly_rating = diagnoser.profiler.evaluate_from_file(
                            data[config.test_configurations.sh.learning_columns])
                    if anomaly_rating >= anomaly_threshold:
                        with interface_lock:
                            diagnoser.talcom.trigger_script("SH_LOOP_II", {
                                        'Degradation':'dummy',
                                        'ServiceID':service_id,
                                        'AlarmID':alarm_id,
                                        'appId': app_id,
                                    })
                    return
                print('SHDataMonitor: error: not enough VM metrics available from Cassandra')
            profiling_thread = threading.Thread(target=sh_data_monitor)
            profiling_thread.start()
            #ip = diagnoser.tools.getitemitem(
            #            data,
            #            ['dataDefinition', 'metrics', 0, 'dimensions', 'ipAddress'],
            #            None,
            #        )
            # TODO: collect test data only for the particular firewall, run profile
            # get data by service id, pull app id for disabling


