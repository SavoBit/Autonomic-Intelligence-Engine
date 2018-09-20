#!/usr/bin/env python3


import json
import pickle
import pickletools
import sys

import lz4

import pandas as pd


def log(message):
    sys.stderr.write(message)
    sys.stderr.flush()

def compress(data, label):
    log(' size is {} bytes\n'.format(len(data)))
    log('lz4 compressing {}...'.format(label))
    data = lz4.block.compress(data, mode='high_compression')
    log(' size is {} bytes\n'.format(len(data)))
    return data

def pickle_optimize_compress(data, label):
    log('pickling {}...'.format(label))
    data = pickle.dumps(data)
    compress(data, 'pickled data')
    log('optimizing pickled data...')
    data = pickletools.optimize(data)
    return compress(data, 'optimized pickled data')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        log('usage: {} INPUT OUTPUT\n'.format(sys.argv[0]))
    log('reading raw JSON data...')
    with open(sys.argv[1], 'rb') as inp:
        compress(inp.read(), 'raw JSON data')
    log('decoding JSON data...')
    with open(sys.argv[1]) as inp:
        data = [json.loads(line) for line in inp]
        log(' read {} bytes, {} records\n'.format(inp.tell(), len(data)))
    log('normalizing data...')
    data = pd.io.json.json_normalize(data)
    log(' done\n')
    data = pickle_optimize_compress(data, 'normalized data')
    log('writing to file...')
    with open(sys.argv[2], 'wb') as out:
        out.write(data)
    log(' done\n')


