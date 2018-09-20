#!/usr/bin/env python3


import collections.abc
import datetime
import functools
import itertools
import operator
import traceback
import requests
import json
import pandas as pd

def getitemitem(obj, keys, *default):
    if len(default) >= 2:
        raise TypeError(
                'getitemitem expected at most 3 arguments, got {}'.format(
                    len(default) + 2))
    if default:
        try:
            return functools.reduce(operator.getitem, keys, obj)
        except (LookupError, TypeError):
            return default[0]
    else:
        return functools.reduce(operator.getitem, keys, obj)

def to_table(iterable, keys):
    for x in iterable:
        try:
            yield [getitemitem(x, k) for k in keys]
        except (LookupError, TypeError):
            #traceback.print_exc()
            pass

def groupby(iterable, key=None):
    return ((k, list(g)) for k, g in
            itertools.groupby(sorted(iterable, key=key), key=key))

def groupby_dict(iterable, key=None):
    return collections.OrderedDict(groupby(iterable, key))

def _convert_recursive(obj, filt):
    for k, v in obj.items() if isinstance(
            obj, collections.abc.MutableMapping) else enumerate(obj):
        if isinstance(v, (collections.abc.MutableMapping,
                collections.abc.MutableSequence)):
            _convert_recursive(v, filt)
        else:
            obj[k] = filt(v)
    return obj

def convert_recursive(obj, filt):
    if isinstance(obj,
            (collections.abc.MutableMapping, collections.abc.MutableSequence)):
        return _convert_recursive(obj, filt)
    else:
        return filt(obj)

def convert_datetime(obj):
    if isinstance(obj, datetime.datetime):
        return obj.replace(tzinfo=datetime.timezone.utc).timestamp()
    else:
        return obj

def version_string_to_int(version_string):
    a, b, c, d = map(int, itertools.islice(itertools.chain(version_string.split('.'), itertools.repeat(0)), 4))
    a *= 100000000000000
    b *=     10000000000
    c *=         1000000
    d *=               1
    return a+b+c+d


def getHigherVersionID(appIDs):
    task_url = 'http://192.168.89.129:18081/app-catalogue/app-packages/'
    nID = []
    for id in appIDs:
        r = requests.get(task_url+id)
        print("Requested App-Catalogue for App-ID:{}. Response Code: {}".format(id,r.status_code))
        json_data = json.loads(r.text)
        if(json_data['metadata']['app-version']):
            nID.append([id, version_string_to_int(json_data['metadata']['app-version'])])
    df = pd.DataFrame(nID, columns=['app_id', 'app_version'])
    df.set_index('app_id', inplace=True)
    return df['app_version'].idxmax()


