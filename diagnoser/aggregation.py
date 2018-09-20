#!/usr/bin/env python3


import collections
import math

import pandas as pd


def softmax(x, y, p):
    return math.log((math.exp(x*p) + math.exp(y*p)) / 2) / p

def first(seq):
    return seq[0] if seq else 0

def last(seq):
    return seq[-1] if seq else 0

def avg(seq):
    return sum(seq) / len(seq) if seq else 0

def stddev_pop(seq):
    return (avg([x**2 for x in seq]) - avg(seq)**2)**(1/2) if seq else 0

def min(*args, **kwargs):
    return min(*args, **kwargs)

def max(*args, **kwargs):
    return max(*args, **kwargs)


def aggregate(data, aggregation_functions):
    return collections.OrderedDict((k, [
                f(v) if callable(f) else f[0]([x[f[1]] for x in v])
                for f in aggregation_functions
            ]) for k, v in data.items())


