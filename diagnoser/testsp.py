#!/usr/bin/env python3


import collections
import datetime
import itertools
import json
import math
import operator
import os
import re
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
import diagnoser.talcom
import diagnoser.taskman
import diagnoser.tools


PRINT_EVERY_N_REPORTS = 2**4


def run(config, kafka_consumer, cassandra_client):

    print('SPTest: running Self-Protection test')

    c_and_c_ip = None
    zombie_ips = []

    print('SPTest: listening to CEP output on Kafka')

    if not config.test_configurations.sp.disable_kafka:
        try:
            c = 0
            for data in kafka_consumer:
                c += 1
                if PRINT_EVERY_N_REPORTS != 0 and c % PRINT_EVERY_N_REPORTS == 0:
                    print('TestSP: received {} reports from Kafka'.format(c))
                if diagnoser.tools.getitemitem(
                            data,
                            ['dataDefinition', 'metadata', 'sensor'],
                            None,
                        ) == 'SNORT':
                    new_ip_received = False
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
                        print('TestSP: received c&c label: {}'.format(dstIp))
                    for ip in srcIpList:
                        if ip[0] not in zombie_ips:
                            new_ip_received = True
                            zombie_ips.append(ip[0])
                            print('TestSP: received zombie label: {}'.format(ip[0]))
                    if len(zombie_ips) >= config.test_configurations.sp.max_zombie_ips:
                        break
        except KeyboardInterrupt:
            pass

    # The list of botnet IPs can be overridden via the test configuration.
    if config.test_configurations.sp.c_and_c_ip is not None:
        c_and_c_ip = config.test_configurations.sp.c_and_c_ip
    if config.test_configurations.sp.zombie_ips is not None:
        zombie_ips = config.test_configurations.sp.zombie_ips.copy()
    if c_and_c_ip is None:
        print('TestSP: error: unable to determine c&c ip')
    if not zombie_ips:
        print('TestSP: error: unable to determine zombie ips')

    print('TestSP: c&c ip: {}'.format(c_and_c_ip))
    print('TestSP: known zombie ips: {}'.format(', '.join(zombie_ips)))
    print('TestSP: running NEAT')

    diagnoser.neattools.run_sp_neat(config, cassandra_client, c_and_c_ip, zombie_ips)


