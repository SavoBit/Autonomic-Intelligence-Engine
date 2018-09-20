#!/usr/bin/env python3


import argparse
import contextlib
import functools
import os
import sys

import kafka

import diagnoser.cassandra
import diagnoser.config
import diagnoser.diagnoser
import diagnoser.kafka
import diagnoser.tests


def main(argv):

    with contextlib.ExitStack() as es:

        config = diagnoser.config.Config(
                    argv=argv,
                    environ=os.environ,
                    description='Demonstration version of SELFNET diagnoser',
                )

        kafka_consumer = diagnoser.kafka.KafkaConsumer(config)
        es.enter_context(contextlib.closing(kafka_consumer))

        cassandra_client = diagnoser.cassandra.CassandraClient(config)
        es.enter_context(contextlib.closing(cassandra_client))

        # TODO: the other interfaces should be initialized here as well

        start = {
                    None: diagnoser.diagnoser.start,
                    'sp': diagnoser.tests.run_sp_test,
                    'sh': diagnoser.tests.run_sh_test,
                }[config.test_configurations.active_test]
        start(
                    config=config,
                    kafka_consumer=kafka_consumer,
                    cassandra_client=cassandra_client,
                )

    return 0


