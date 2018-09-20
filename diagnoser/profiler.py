#!/usr/bin/env python3


import collections
import collections.abc
import contextlib
import datetime
import functools
import itertools
import json
import operator
import os
import pickle
import pickletools

import numpy as np

import scipy as sp
import scipy.stats

import pandas as pd

import lz4

import torch

import diagnoser.cassandra


# TODO? make this configurable?

AUTOENCODER_PARAMETERS = [
            {
                'sizes': sizes,
                'activation': activation,
                'seed': seed,
                'lr': lr,
            }
            for seed in [0, 1, 2]
            for sizes in [
                [2],
                [3],
                [4],
                [6],
                [8],
                #[3, 2, 3],
                [4, 2, 4],
                [4, 3, 4],
                #[6, 2, 6],
                #[6, 3, 6],
                #[6, 4, 6],
                [8, 2, 8],
                #[8, 3, 8],
                [8, 4, 8],
                [8, 6, 8],
                #[4, 3, 2, 3, 4],
                #[6, 3, 2, 3, 6],
                #[6, 4, 2, 4, 6],
                #[6, 4, 3, 4, 6],
                #[8, 3, 2, 3, 8],
                [8, 4, 2, 4, 8],
                #[8, 4, 3, 4, 8],
                #[8, 6, 2, 6, 8],
                #[8, 6, 3, 6, 8],
                [8, 6, 4, 6, 8],
            ]
            for activation in ['tanh', 'relu']
            for lr in [2**-n for n in [8, 10, 12]]
        ]


def cuda(x):
    #return x.cuda()
    return x


@contextlib.contextmanager
def no_gradient(module):
    requires_grads = [p.requires_grad for p in module.parameters()]
    for p in module.parameters():
        p.requires_grad = False
    yield
    for p, requires_grad in zip(module.parameters(), requires_grads):
        p.requires_grad = requires_grad


def pickle_lz4(data, filename):
    data = pickle.dumps(data)
    data = pickletools.optimize(data)
    data = lz4.block.compress(data, 'high_compression')
    with open(filename, 'wb') as out:
        out.write(data)


def unlz4_unpickle(filename):
    with open(filename, 'rb') as inp:
        data = inp.read()
    data = lz4.block.decompress(data)
    data = pickle.loads(data)
    return data


class Autoencoder(torch.nn.Module):

    def __init__(
            self, n_features, sizes=None, activation='tanh', seed=None,
            lr=2**-10):
        super().__init__()
        if seed is not None:
            torch.manual_seed(seed)
        self.n_features = n_features
        self.sizes = [n_features] if sizes is None else list(sizes)
        self.activation = getattr(torch.nn.functional, activation)
        sizes = [n_features] + self.sizes + [n_features]
        self.layers = [torch.nn.Linear(in_features=s0, out_features=s1)
                for s0, s1 in zip(sizes, sizes[1:])]
        for i, l in enumerate(self.layers):
            self.add_module('layer{}'.format(i), l)
        #self.reset()
        self.optim = torch.optim.Adam(self.parameters(), lr)
        if seed is not None:
            torch.manual_seed(seed)
        for p in self.parameters():
            if p.ndimension() >= 2:
                torch.nn.init.xavier_normal_(p.data)
            else:
                torch.nn.init.normal_(p.data, 0, (p.size()[0])**(-1/2))

    def forward(self, x):
        for l in self.layers[:-1]:
            x = l(x)
            x = self.activation(x)
        x = self.layers[-1](x)
        return x

    def eval_train(self, batch, train=False):
        with contextlib.ExitStack() as stack:
            if not train:
                stack.enter_context(no_gradient(self))
            encoded = self(batch)
            all_losses = (encoded - batch) ** 2
            loss = all_losses.mean()
            if train:
                self.optim.zero_grad()
                loss.backward()
                self.optim.step()
            return (encoded.data.cpu().numpy(), all_losses.data.cpu().numpy(),
                    loss.data.cpu().numpy())

    def to_serializable(self):
        return collections.OrderedDict([
                    ('n_features', self.n_features),
                    ('sizes', self.sizes),
                    ('activation', self.activation.__name__),
                    ('lr', self.optim.defaults['lr']),
                    ('parameters', [collections.OrderedDict([
                            ('weight', l.weight.detach().cpu().numpy().tolist()),
                            ('bias', l.bias.detach().cpu().numpy().tolist()),
                        ]) for l in self.layers]),
                ])

    @classmethod
    def from_serializable(cls, serializable):
        result = cls(serializable['n_features'], serializable['sizes'], serializable['activation'], lr=serializable['lr'])
        for l, p in zip(result.layers, serializable['parameters']):
            l.weight.detach().numpy()[:] = p['weight']
            l.bias.detach().numpy()[:] = p['bias']
        return result


class AutoencoderEnsemble:

    def __init__(self, n_features, parameters, init=True):
        if init:
            self.encs = [cuda(Autoencoder(n_features=n_features, **p))
                    for p in parameters]

    def __iter__(self):
        return iter(self.encs)

    def __len__(self):
        return len(self.encs)

    def train_epoch(self, batches, other_data):
        results = {}
        losses_only = {}
        if batches is not None:
            np_permutation = np.random.permutation(len(batches))
            results['batch_order'] = np_permutation
            losses_only['batch_order'] = np_permutation
            permutation = cuda(torch.from_numpy(np_permutation))
            epoch_encodings = []
            epoch_all_losses = []
            epoch_losses = []
            for i, j in enumerate(permutation):
                #print('epoch {:4}, step {:4}'.format(epoch, i))
                batch = batches[j]
                batch_encodings = []
                batch_all_losses = []
                batch_losses = []
                for ind_enc, enc in enumerate(self):
                    encoded, all_losses, loss = enc.eval_train(batch, True)
                    batch_encodings.append(encoded)
                    batch_all_losses.append(all_losses)
                    batch_losses.append(loss)
                print('  step {:4}, loss {}'.format(i, np.mean(loss)))
                epoch_encodings.append(batch_encodings)
                epoch_all_losses.append(batch_all_losses)
                epoch_losses.append(batch_losses)
            epoch_encodings = np.array(epoch_encodings)
            epoch_all_losses = np.array(epoch_all_losses)
            epoch_losses = np.array(epoch_losses)
            results['training'] = {
                        'encodings': epoch_encodings.swapaxes(1, 2),
                        'all_losses': epoch_all_losses.swapaxes(1, 2),
                        'losses': epoch_losses,
                    }
            losses_only['training'] = epoch_losses
        for k, batch in other_data.items():
            #print('epoch {:4}, {}'.format(epoch, k))
            batch_encodings = []
            batch_all_losses = []
            batch_losses = []
            for ind_enc, enc in enumerate(self):
                encoded, all_losses, loss = enc.eval_train(batch)
                batch_encodings.append(encoded)
                batch_all_losses.append(all_losses)
                batch_losses.append(loss)
            batch_encodings = np.array(batch_encodings)
            batch_all_losses = np.array(batch_all_losses)
            batch_losses = np.array(batch_losses)
            print('  {}, loss {}'.format(k, np.mean(loss)))
            results[k] = {
                        'encodings': batch_encodings.swapaxes(0, 1),
                        'all_losses': batch_all_losses.swapaxes(0, 1),
                        'losses': batch_losses,
                    }
            losses_only[k] = batch_losses
        return results

    def evaluate(self, data):
        return self.train_epoch(None, data)

    def to_serializable(self):
        return [e.to_serializable() for e in self]

    @classmethod
    def from_serializable(cls, serializable):
        result = cls(None, None, init=False)
        result.encs = [Autoencoder.from_serializable(e) for e in serializable]
        return result 


def preprocess(data, columns):
    print('preprocessing')
    training_data = data['training']
    #columns = [name for name, series in training_data.items()
    #        #if name != 'reporterEpochTime' and
    #        if pd.api.types.is_numeric_dtype(series.dtype) and
    #        series.std() >= 2**-16]
    # FIXME: make this configurable or automatic again
    print('number of features: {}'.format(len(columns)))
    print('selected columns: {}'.format(
            ', '.join(repr(name) for name in columns)))
    # TODO: compute std only once
    other_columns = set(training_data.columns) - set(columns)
    for k, d in data.items():
        for c in other_columns:
            del d[c]
    means = -training_data.mean()
    stds = 1 / np.maximum(training_data.std(), 2**-8)
    for k, d in data.items():
        d += means
        d *= stds
    return data


def get_data_range(data, filters):
    return data[functools.reduce(
            operator.and_,
            ((data[k] >= v[0]) & (data[k] < v[1]) if
                    isinstance(v, collections.abc.Sequence) and len(v) == 2
                    else data[k] == v
                for k, v in filters.items()),
            pd.Series(data=True, index=data.index))].copy()


def process_data(data, ranges, collectns):
    ##data.set_index(pd.to_datetime(dataset['timestamp']), inplace=True)
    data = collections.OrderedDict(
            (k, get_data_range(data, filters)) for k, filters in ranges.items())
    # XXX: enable first differences again?
    #for k, ds in data.items():
    #    for c in ds.select_dtypes(np.number).columns:
    #        ds['{}.diff'.format(c)] = ds[c].diff()
    #    data[k] = ds.iloc[1:]
    data = collections.OrderedDict((k, pd.concat(data[v] for v in vs))
            for k, vs in collectns.items())
    return data


def load_data(cassandra_client, resource_types, raw_data_columns, service_id, ranges, collectns, timestamp=None):
    raw_data_columns = [c.split('/') for c in raw_data_columns]
    if ranges is None:
        if timestamp is None:
            timestamp = pd.to_datetime(datetime.datetime.now(datetime.timezone.utc).timestamp()*1000 // 1, unit='ms')
        if isinstance(timestamp, str):
            timestamp = pd.to_datetime(timestamp)
        else:
            timestamp = pd.to_datetime(timestamp, unit='ms')
        timestamp = timestamp.replace(second=0, microsecond=0, nanosecond=0)
        ranges = {
                    'main': {
                        'timestamp': [
                            (timestamp - pd.Timedelta(10, unit='m')).isoformat(),
                            timestamp.isoformat()
                        ]
                    }
                }
    min_time = pd.to_datetime([r['timestamp'][0] for r in ranges.values()]).min().to_pydatetime()
    max_time = pd.to_datetime([r['timestamp'][1] for r in ranges.values()]).max().to_pydatetime()
    #delta = (max_time - min_time).total_seconds()
    #data = cassandra_client.get_data(
    #        min_time, raw_data_columns, time_limit=delta, row_limit=2**16)
    data = cassandra_client.get_data(
                'selfnet_counters',
                {
                    'timepartition': diagnoser.cassandra.minute_range(
                        min_time, max_time),
                    'resourcetype': resource_types,
                },
                raw_data_columns,
                row_limit=2**16)
    data = data[data['resourcedescription.serviceID'] == service_id]
    #del data['resourcedescription.serviceID']
    #data.set_index('timestamp', inplace=True)
    #data = data.resample('S').last().fillna(method='pad')
    #data.reset_index(inplace=True)
    return process_data(data, ranges, collectns)


def make_batches(data, batch_size=2**10, label='data'):
    n_batches, n_discard = divmod(len(data), batch_size)
    print('{}: number of batches: {}, discarded data: {}'.format(
            label, n_batches, n_discard))
    if n_batches == 0:
        bd = data.values[np.newaxis, ...]
    else:
        bd = np.reshape(
                data.values[n_discard:], (n_batches, batch_size, -1))
    bd = np.arcsinh(bd)
    return bd


def analyze(data, output_directory, store_results=False):

    training_data = data['training']
    columns = list(training_data.columns)
    print(columns)
    batches = make_batches(data['training'], label='training data')

    if store_results:
        all_data = data.copy()
        all_data['columns'] = columns
        all_data['batches'] = batches
        pickle_lz4(all_data, os.path.join(
                output_directory, 'data{s}pickle{s}lz4'.format(s=os.path.extsep)))

    batches = cuda(torch.autograd.Variable(
            torch.from_numpy(batches.astype(np.float32))))
    other_data = collections.OrderedDict([
            (k, cuda(torch.autograd.Variable(
                    torch.from_numpy(data[k].values.astype(np.float32)))))
                for k in ['validation', 'test0', 'test1']])

    # TODO: store the normalizations
    encs = AutoencoderEnsemble(len(columns), AUTOENCODER_PARAMETERS)
    thresholds = np.zeros(len(encs))

    np.random.seed(0)

    try:
        for epoch in itertools.count():
            print('epoch {:4}'.format(epoch))
            results = encs.train_epoch(batches, other_data)
            results['epoch'] = epoch
            if store_results:
                if epoch % 64 == 0:
                    pickle_lz4(results, os.path.join(
                            output_directory, '{:04}{s}pickle{s}lz4'.format(
                                epoch, s=os.path.extsep)))
                pickle_lz4(losses_only, os.path.join(
                        output_directory, 'loss{:04}{s}pickle{s}lz4'.format(
                            epoch, s=os.path.extsep)))
            thresholds[:] = np.array(results['validation']['losses'])
    except KeyboardInterrupt:
        pass

    #import json
    #print(json.dumps(encs.to_serializable(), indent=4))

    return encs.to_serializable(), thresholds.tolist()


def evaluate(encs, data, reference=None, thresholds=None):
    encs = AutoencoderEnsemble.from_serializable(encs)
    data = collections.OrderedDict([
            (k, cuda(torch.autograd.Variable(
                    torch.from_numpy(d.values.astype(np.float32)))))
                for k, d in [('data', data)] + ([] if reference is None else [('reference', reference)])])
    results = encs.evaluate(data)
    if thresholds is None:
        thresholds = np.mean(results['reference']['all_losses'], axis=-1)
    else:
        thresholds = np.array(thresholds)
    data_losses = np.mean(results['data']['all_losses'], axis=-1)
    result = np.mean(np.mean(data_losses >= thresholds * 1.5, axis=-1) >= .75)
    #print(results['reference']['all_losses'])
    #print(results['data']['all_losses'])
    print('Profiler: anomaly rating: {}'.format(result))
    return result


def profile(data, columns, output_directory):
    data = preprocess(data, columns)
    encoders, thresholds = analyze(data, output_directory)
    with open('tests/sh/sh_encoders_out.json', 'w') as out:
        out.write(json.dumps(collections.OrderedDict([('encoders', encoders), ('thresholds', thresholds)])))
    return data, encoders


def evaluate_from_file(data):
    with open('tests/sh/sh_encoders_in.json') as inp:
        prf = json.loads(inp.read())
    return evaluate(prf['encoders'], data, thresholds=prf['thresholds'])


