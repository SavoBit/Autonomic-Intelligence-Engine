#!/usr/bin/env python3


import copy
import json
import pickle

from collections import OrderedDict as OD

import neat

import requests

feature_labels = [
                    ##'time',
                    ##'type',
                    ##'key.flowHash',
                    ##'key.srcIP',
                    ##'key.dstIP',
                    ##'key.srcPort',
                    ##'key.dstPort',
                    #'value.totalFMAReports',
                    #'value.totalpktCount.first',
                    #'value.totalBits.first',
                    #'value.totalpktCount.max',
                    'value.totalBits.max',
                    'value.totalpktCount.min',
                    'value.totalBits.min',
                    #'value.totalpktCount.last',
                    'value.totalBits.last',
                    #'value.totalpktCount.avg',
                    'value.totalBits.avg',
                    #'value.totalpktCount.variance',
                    'value.totalBits.variance',
                    #'value.botnet',
                ]

#TODO: map more activation functions?
activation_formats = {
            # neat python uses a sigmoid with a slope of 1.25 at 0
            'sigmoid': '(tanh(greatest(-12.,least(12.,({})))*2.5)+1.)*.5',
            'sin': 'sin({})',
            #'log': 'log({})',
            'log': 'log(greatest(({}),0.0000001))',
            'inv': 'coalesce(1./({}),0.)',
            # another normalization for the gaussian
            'gauss': 'exp(-pow(greatest(-3.4,least(3.4,({}))),2)*5.)',
            'square': 'pow(({}),2)',
            'exp': 'exp(greatest(-60.,least(60.,({}))))',
        }


#----PARAMETERS DEFINING AGGREGATION AND INVOLVED METRIC----
def write_parameters(inputs, node_names):
    parameters = []
    for i in inputs:
        nodename = node_names.get(i, str(i))
        counter, aggr = nodename.split('.')[1:]
        name = "_{}_{}".format(counter,aggr)
        #groupByAttributes = []
        groupBy = [
                    OD([("name","srcIP"),("label",None),("attributeType","DESCRIPTION")]),
                    OD([("name","dstIP"),("label",None),("attributeType","DESCRIPTION")]),
                    OD([("name","dstPort"),("label",None),("attributeType","DESCRIPTION")]),
                    OD([("name","flowHash"),("label",None),("attributeType","DESCRIPTION")])
                ]
        pmetric = OD([
                    ("name",name),
                    ("counter",counter),
                    ("aggregation",aggr),
                    ("type","COUNTER"),
                    ("groupByAttributes",groupBy)
                ])
        parameters.append(pmetric)
    return parameters


#Create Metrics entry for JSON
def create_Metrics(metricname, parameters, expression):
    formula = OD()
    formula['expression'] = expression
    formula['parameters'] = parameters
    #Option to define filters as list of OrderedDicts (column, value[], operation)
    filters = [
                OD([("column","srcIP"), ("value",None), ("operation","NOT_NULL")]),
                OD([("column","srcIP"), ("value",["8.8.8.8"]), ("operation","NOT_EQUALS")]),
                OD([("column","dstPort"), ("value",None), ("operation","NOT_NULL")]),
                OD([("column","dstIP"), ("value",["8.8.8.8"]), ("operation","NOT_EQUALS")]),
            ]
    metrics = [OD([
                ("name", metricname),
                ("formula", formula),
                ("filters", filters),
                ("metadata", None),
            ])]
    return metrics


#Stitch JSON together
def create_Task_JSON(body, task_name, period=10000, delay=10000, metadata=None):
    start = "2017-02-21T12:08:45.159+0000"
    end = "2100-12-31T23:59:59.999+0000"
    data = OD()
    data['name'] = task_name
    data['timeout'] = None
    data['priority'] = 50000
    data['group'] = "altaia"
    data['type'] = "selfnet"
    data['body'] = body
    data['state'] = "ACTIVE"
    data['schedule'] = OD([
                ("start", start),
                ("end", end),
                ("period", period),
                ("delay", delay),
            ])
    return data


#Create Body for JSON
def create_Body(metrics):
    entityType = "SP1"
    resourceType = "FLOW_SAMPLE"
    utc = True
    dimension = OD()
    dimension['name'] = "SrcDest"
    dimension['dimensionAttributes'] = [
                OD([("name","srcIP"),("label","SourceIP"),("attributeType","DESCRIPTION")]),
                OD([("name","srcPort"),("label","SourcePort"),("attributeType","DESCRIPTION")]),
                OD([("name","dstIP"),("label","DestinationIP"),('attributeType',"DESCRIPTION")]),
                OD([("name","dstPort"),("label","DestinationPort"),("attributeType","DESCRIPTION")]),
                OD([("name","flowHash"),("label","FlowID"),("attributeType","DESCRIPTION")]),
                OD([("name","serviceID"),("label","serviceID"),("attributeType","DESCRIPTION")]),

    #            OD([("name","flowState"),("label","FlowState"),("attributeType","EVENT")]),
            ]
    consumer = OD([
                ("name","monasca"),
                ("consumerClass", "pt.ptinovacao.selfnet.aggregation.executor.consumer.MonascaRestResultConsumer"),
                ("type", "PARTITION"),
                ("configurations",{}),
            ])
    #----Build-Body------------
    body = OD()
    body['bodyClassType'] = "pt.ptinovacao.selfnet.aggregation.collector.spark.api.SparkBody"
    body['start'] = 1490291340000
    body['end'] = 1490291370000
    body['bulk'] = 500
    body['entityType'] = entityType
    body['resourceType'] = resourceType
    body['dimension'] = dimension
    body['metrics'] = metrics
    body['consumer'] = consumer
    body['utc'] = True
    return body


def remove_unused(outputs, connections, inputs):
    #remove unused inputs, nodes, connections
    used_inputs = set()
    used_nodes = copy.copy(outputs)
    used_connections = set()
    pending = copy.copy(outputs)
    while pending:
        #print(pending, used_nodes)
        new_pending = set()
        for a, b in connections:
            if b in pending and a not in used_nodes:
                new_pending.add(a)
                used_connections.add((a,b))
                used_nodes.add(a)
                if a in inputs:
                    used_inputs.add(a)
        pending = new_pending
    used_connections.add((0,999))
    return used_inputs, used_nodes, used_connections


#def translate_model(config, genome, metric_name, task_name, node_names=None):
def translate_model(config, genome, metric_name, task_name, node_names):

    if node_names is None:
        node_names = {-i: label for i, label in
                #enumerate(['value.botnet.estimate'] + feature_labels)}
                enumerate(['value.botnet.estimate'])}

    inputs = set()
    for k in config.genome_config.input_keys:
        inputs.add(k)

    outputs = set()
    for k in config.genome_config.output_keys:
        outputs.add(k)

    #Expecting one output at this time to allow mapping into expression
    assert(len(outputs) == 1)

    connections = set()
    for cg in genome.connections.values():
        if cg.enabled:
            connections.add(cg.key)

    used_inputs, used_nodes, used_connections = remove_unused(
            outputs, connections, inputs)

    pending = copy.copy(used_inputs)
    parsed_nodes = set()
    final_expression = ""
    while pending:
        #print(pending, used_nodes)
        new_pending = set()
        for a, b in used_connections:
            if a in pending and b not in parsed_nodes:
                #print("addding node {} to parsed nodes.".format(a))
                if a in used_inputs:
                    name, aggr = node_names.get(a, str(a)).split('.')[1:]
                    #node is an input, only naming needed time connection weight
                    expression = "_{}_{} * {}".format(
                            name, aggr, genome.connections[a, b].weight)
                else:
                    np = vars(genome.nodes[a])
                    expression = ""
                    if np['aggregation'] == "product":
                        for c in parsed_nodes:
                            if c[0][1] == a:
                                if expression == "":
                                    expression = "({})".format(c[1])
                                else:
                                    expression = "{} * ({})".format(
                                            expression, c[1])
                    elif np['aggregation'] == "sum":
                        for c in parsed_nodes:
                            if c[0][1] == a:
                                if expression == "":
                                    expression = "({})".format(c[1])
                                else:
                                    expression = "{} + ({})".format(
                                            expression, c[1])
                    elif np['aggregation'] == "max":
                        for c in parsed_nodes:
                            if c[0][1] == a:
                                if expression == "":
                                    expression = "({})".format(c[1])
                                else:
                                    expression = "(greatest(({}), + ({})))".format(
                                            expression, c[1])
                    elif np['aggregation'] == "min":
                        for c in parsed_nodes:
                            if c[0][1] == a:
                                if expression == "":
                                    expression = "({})".format(c[1])
                                else:
                                    expression = "(least(({}), + ({})))".format(
                                            expression, c[1])
                    else:
                        for c in parsed_nodes:
                            if c[0][1] == a:
                                if expression == "":
                                    expression = str(c[1])
                                else:
                                    expression = "{}, {}".format(
                                            expression, c[1])
                        expression = "{}({})".format(
                                np['aggregation'],expression)
                    expression = "((({}) * {}) + ({}))".format(
                            expression, np['response'], np['bias'])
                    expression = activation_formats[np['activation']].format(
                            expression)
                new_pending.add(b)
                parsed_nodes.add(((a,b),expression))
                if a == 0:
                    final_expression = 'coalesce(signum(signum(({}) - .5) + 1), 0)'.format(expression)
        pending = new_pending

    parameters = write_parameters(used_inputs, node_names)
    metrics = create_Metrics(metric_name, parameters, final_expression)
    body = create_Body(metrics)
    jsonfile = create_Task_JSON(body, task_name)

    return jsonfile


if __name__ == '__main__':
    # load configuration
    config = neat.Config(
                neat.DefaultGenome,
                neat.DefaultReproduction,
                neat.DefaultSpeciesSet,
                neat.DefaultStagnation,
                'tests/sp/config-feedforward',
            )
    with open('tests/sp/winner', 'rb') as f:
        c = pickle.load(f)

    metric_name = "newMetricName"
    task_name = "newTaskName"

    task_json = translate_model(config, c, metric_name, task_name)
    print(json.dumps(task_json, indent=4))


