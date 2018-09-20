#!/usr/bin/env python3


# TODO: some identifiers such as "selfnet_counters" should be configurable


import collections
import datetime
import itertools
import pickle

import pandas as pd

import cassandra.auth
import cassandra.cluster
import cassandra.query
import cassandra.util

import lz4
import lz4.block

# hack for interoperability of cassandra with newer versions of the lz4 package
lz4.compress = lz4.block.compress
lz4.decompress = lz4.block.decompress

import diagnoser.tools


class RealCassandraClient:

    def __init__(self, config):
        self.config = config

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        pass

    def get_data(
                self,
                table,
                partition_keys,
                keys,
                row_limit=None,
            ):

        if row_limit is None:
            row_limit = self.config.cassandra.row_limit

        auth_provider=cassandra.auth.PlainTextAuthProvider(
                username=self.config.cassandra.username,
                password=self.config.cassandra.password)
        cluster = cassandra.cluster.Cluster(
                [self.config.cassandra.host], auth_provider=auth_provider)
        session = cluster.connect()
        session.set_keyspace(self.config.cassandra.keyspace)
        session.row_factory = cassandra.query.ordered_dict_factory

        data = []
        offset = datetime.timedelta()
        partition_key_names, partition_key_value_lists = zip(
                *partition_keys.items())
        try:
            for vs in itertools.product(*partition_key_value_lists):
                if len(data) >= row_limit:
                    print('CassandraClient: row limit hit')
                    break
                statement_string = 'SELECT * FROM {}{}{}'.format(
                            table,
                            ' WHERE ' if partition_keys else '',
                            ' and '.join("{}='{}'".format(k, v)
                                for k, v in zip(partition_key_names, vs)),
                        )
                statement = cassandra.query.SimpleStatement(
                            statement_string,
                            fetch_size=self.config.cassandra.fetch_size,
                        )
                print('CassandraClient: executing statement {!r}...'.format(
                        statement_string), end='', flush=True)
                dt_begin = datetime.datetime.now(tz=datetime.timezone.utc)
                for row in session.execute(statement):
                    #print('{}: {}'.format(row.get('countertype', None), ', '.join(row.get('datadefinition', {}).keys())))
                    data.append([diagnoser.tools.getitemitem(row, key, None)
                            for key in keys])
                dt_end = datetime.datetime.now(tz=datetime.timezone.utc)
                print(
                        ' time for last request: {:.4f} seconds, '
                        'retrieved {} records so far'.format(
                            (dt_end - dt_begin).total_seconds(), len(data)))
        except KeyboardInterrupt:
            print('cassandra_data_manager: request aborted, returning '
                    'partial data')

        return pd.DataFrame(data, columns=['.'.join(k) for k in keys])


def convert_cassandra_stuff(obj):
    if isinstance(obj, datetime.datetime):
        return obj.timestamp()
    elif isinstance(obj, cassandra.util.OrderedMap):
        return collections.OrderedDict(obj)
    else:
        return obj


def convert_cassandra_stuff_recursive(obj):
    return diagnoser.tools.convert_recursive(obj, convert_cassandra_stuff)


# TODO: the new request format needs to be implemented here
class FakeCassandraClient:

    def __init__(self, config):
        self.config = config
        with open(config.cassandra.from_file, 'rb') as df:
            self.data = pickle.loads(lz4.block.decompress(df.read()))
        self.data['timepartition'] = pd.to_datetime(self.data['timepartition'])
        self.data['timestamp'] = pd.to_datetime(self.data['timestamp'])

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        pass

    def get_data(self, timestamp, keys, time_limit=None, row_limit=None):
        if time_limit is None:
            time_limit = self.config.cassandra.time_limit
        #time_limit = datetime.timedelta(seconds=time_limit)

        if row_limit is None:
            row_limit = self.config.cassandra.row_limit

        # TODO: multiple timestamps, limits
        print(keys)
        print(['.'.join(k) for k in keys])
        print(self.data.columns)
        begin, end = (pd.to_datetime(datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc)) for t in (timestamp, timestamp + time_limit))
        print('BEGIN, END: {}, min, max: {}'.format((begin, end), (self.data['timepartition'].min(), self.data['timepartition'].max())))
        return self.data[(self.data['timepartition'] >= begin) & (self.data['timepartition'] < end)][['.'.join(k) for k in keys]]

        #dt = datetime.datetime.fromtimestamp(
        #        timestamp, tz=datetime.timezone.utc)
        #data = []
        #offset = datetime.timedelta()
        #count = 0
        #try:
        #    while offset < time_limit and count < row_limit:
        #        timepartition = (dt - offset).strftime('%Y-%m-%dT%H:%M:00Z')
        #        print('CassandraClient: requesting data at {}...'.format(
        #                timepartition), end='', flush=True)
        #        statement = cassandra.query.SimpleStatement(
        #                "SELECT * FROM selfnet_counters "
        #                "WHERE resourcetype='FLOW_SAMPLE' and timepartition='{}'".
        #                    format(timepartition),
        #                fetch_size=self.config.cassandra.fetch_size)
        #        dt_begin = datetime.datetime.now(tz=datetime.timezone.utc)
        #        for row in session.execute(statement):
        #            data.append([diagnoser.tools.getitemitem(row, key, None)
        #                    for key in keys])
        #            count += 1
        #        dt_end = datetime.datetime.now(tz=datetime.timezone.utc)
        #        print(
        #                ' time for last request: {:.4f} seconds, '
        #                'retrieved batch of {} records'.format(
        #                    (dt_end - dt_begin).total_seconds(), len(data)))
        #        offset += datetime.timedelta(minutes=1)
        #except KeyboardInterrupt:
        #    print('cassandra_data_manager: request aborted, returning '
        #            'partial data')
        #return data


def CassandraClient(config):
    if config.cassandra.from_file is None:
        return RealCassandraClient(config)
    else:
        return FakeCassandraClient(config)


def date_range(start, end, freq):
    return pd.date_range(
                start=start,
                end=end,
                freq=freq,
                tz='UTC',
                closed='left',
            ).strftime('%Y-%m-%dT%H:%M:%SZ')


def minute_range(start, end):
    return date_range(start=start, end=end, freq='T')


