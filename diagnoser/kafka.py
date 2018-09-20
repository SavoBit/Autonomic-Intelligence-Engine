#!/usr/bin/env python3


import collections
import json
import traceback

import kafka


# TODO: make this work with file input again, possibly wrap entries in files with object specifying topic
def wrap_kafka_consumer(kafka_consumer, get_value=True):
    for record in kafka_consumer:
        print('DEBUG: got data from kafka on topic {!r}:'.format(record.topic if get_value else '<file>'))
        print(record.value.decode() if get_value else record)
        print()
        try:
            val = record.value.decode() if get_value else record
            if record.topic == 'cep_output':
                if not record.value:
                    continue
                yield from json.loads(
                        val, object_pairs_hook=collections.OrderedDict)['Data']
            elif record.topic == 'monasca-notifications':
                yield from json.loads(
                        val, object_pairs_hook=collections.OrderedDict)
        except (UnicodeDecodeError, json.decoder.JSONDecodeError, KeyError):
            traceback.print_exc()


class KafkaConsumer:

    def __init__(self, config):
        if config.kafka.from_file is None:
            self.kafka_consumer = wrap_kafka_consumer(kafka.KafkaConsumer(
                        *config.kafka.topics,
                        bootstrap_servers=config.kafka.bootstrap_servers,
                    ))
        else:
            self.kafka_consumer = wrap_kafka_consumer(
                    open(config.kafka.from_file), get_value=False)

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.kafka_consumer)

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        pass


