#!/usr/bin/env python3


import collections
import collections.abc
import contextlib
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
import warnings
import xml.dom.minidom
import xml.etree.cElementTree

import pandas as pd

import jinja2

import neat.reporting

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


try:
    import graphviz
except ImportError:
    graphviz = None


def run_sp_neat(config, cassandra_client, c_and_c_ip, zombie_ips, timestamp=None, lock=None):

    # replace test.sp configuration stuff by proper config entries
    if lock is None:
        lock = contextlib.ExitStack()

    ################################################################
    #### collect raw data
    ################################################################

    print('SPNEAT: Reading RAW-Sensor-Data from cassandra:')

    keys = [
        'timestamp',
        #'resourcedescription.flowHash',
        'resourcedescription.srcIP',
        #'resourcedescription.srcPort',
        'resourcedescription.dstIP',
        'resourcedescription.dstPort',
        #'!timegroup',
    ]
    values = [
        'datadefinition.totalpktCount',
        'datadefinition.totalBits',
        #'',
    ]

    #aggregations = collections.OrderedDict([
    #    ('datadefinition.totalpktCountFirst', (diagnoser.aggregation.first, 'datadefinition.totalpktCount')),
    #    ('datadefinition.totalpktCountMax',   (diagnoser.aggregation.max,   'datadefinition.totalpktCount')),
    #    ('datadefinition.totalpktCountMin',   (diagnoser.aggregation.min,   'datadefinition.totalpktCount')),
    #    ('datadefinition.totalpktCountLast',  (diagnoser.aggregation.last,  'datadefinition.totalpktCount')),
    #    ('datadefinition.totalpktCountAvg',   (diagnoser.aggregation.avg,   'datadefinition.totalpktCount')),
    #    ('datadefinition.totalpktCountStd',   (diagnoser.aggregation.std,   'datadefinition.totalpktCount')),
    #    ('datadefinition.totalOctetsFirst', (diagnoser.aggregation.first, 'datadefinition.totalOctets')),
    #    ('datadefinition.totalOctetsMax',   (diagnoser.aggregation.max,   'datadefinition.totalOctets')),
    #    ('datadefinition.totalOctetsMin',   (diagnoser.aggregation.min,   'datadefinition.totalOctets')),
    #    ('datadefinition.totalOctetsLast',  (diagnoser.aggregation.last,  'datadefinition.totalOctets')),
    #    ('datadefinition.totalOctetsAvg',   (diagnoser.aggregation.avg,   'datadefinition.totalOctets')),
    #    ('datadefinition.totalOctetsStd',   (diagnoser.aggregation.std,   'datadefinition.totalOctets')),
    #])

    aggregations = collections.OrderedDict([
        ('datadefinition.totalpktCount',
            ['first', 'max', 'min', 'last', 'mean', ('stddev_pop', lambda x: x.std(ddof=0))]),
        ('datadefinition.totalBits',
            ['first', 'max', 'min', 'last', 'mean', ('stddev_pop', lambda x: x.std(ddof=0))]),
    ])

    expanded_aggregations = [
            '{}.{}'.format(k, a[0] if isinstance(a, tuple) else a)
            for k, aggs in aggregations.items() for a in aggs]

    node_names = {-i: label for i, label in
            enumerate(['value.botnet.estimate'] + expanded_aggregations)}

    #request_keys = [tuple(k.split('.')) if k != '' else ()
    #        for k in itertools.chain(keys, values) if not k.startswith('!')]
    request_keys = [tuple(k.split('.')) if k != '' else ()
            for k in itertools.chain(keys, values)]
    #request_indices = {
    #        k: i for i, k in enumerate(itertools.chain(keys, values))}
    #aggregation_indices = {k: i for i, k in enumerate(aggregations)}

    #timestamp = datetime.datetime.now(tz=datetime.timezone.utc).timestamp()
    #timestamp = datetime.datetime(
    #        2017, 8, 30, 15, 48, tzinfo=datetime.timezone.utc).timestamp()
    ##timestamp = config.test_configurations.sp.time_window[0]
    ##timestamp = pd.to_datetime(timestamp)
    ##timestamp = timestamp.to_pydatetime()
    ##timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
    ##timestamp = timestamp.timestamp()
    ##time_limit = config.test_configurations.sp.time_window[1]
    ##time_limit = pd.to_datetime(time_limit)
    ##time_limit = time_limit.to_pydatetime()
    ##time_limit = time_limit.replace(tzinfo=datetime.timezone.utc)
    ##time_limit = time_limit.timestamp()
    ##time_limit -= timestamp
    #timestamp = datetime.datetime(
    #        #2017, 8, 31, 14, tzinfo=datetime.timezone.utc).timestamp()
    #        #2018, 1, 24, 14, tzinfo=datetime.timezone.utc).timestamp()
    #        2017, 7, 13, 15, 0, tzinfo=datetime.timezone.utc).timestamp()
    if config.test_configurations.sp.time_window is not None:
        timestamps = diagnoser.cassandra.minute_range(
                *config.test_configurations.sp.time_window)
    elif timestamp is not None:
        timestamp = pd.to_datetime(timestamp, unit='ms')
        timestamp = timestamp.replace(second=0, microsecond=0, nanosecond=0)
        timestamps = diagnoser.cassandra.minute_range(
                timestamp - pd.Timedelta(10, unit='m'),
                timestamp)
    else:
        raise Exception('SPNeat: missing timestamp')
    #data = cassandra_client.get_data(
    #        timestamp,
    #        {'resourcetype': 'FLOW_SAMPLE'},
    #        request_keys,
    #        time_limit=time_limit)
    with lock:
        data = cassandra_client.get_data(
                'selfnet_counters',
                {'timepartition': timestamps, 'resourcetype': ['FLOW_SAMPLE']},
                request_keys)

    print('received the following dataset:')
    print(data)

    print('#' * 79)

    #print('reformatting data')
    #data = diagnoser.cassandra.convert_cassandra_stuff_recursive(data)
    #data = list(diagnoser.tools.groupby(data, operator.itemgetter(0)))

    print('filtering data')
    #data = [x for x in data if None not in x[:len(keys)]]
    data = data[
                data.notna().all(axis='columns') &
                (data['resourcedescription.srcIP'] != 'null') &
                (data['resourcedescription.srcIP'] != '0.0.0.0') &
                (data['resourcedescription.dstIP'] != 'null') &
                (data['resourcedescription.dstIP'] != '0.0.0.0') &
            True]

    print('grouping data')
    data.set_index('timestamp', inplace=True)
    grouper = data.groupby([k for k in keys if k != 'timestamp'] + [pd.Grouper(freq='10S', label='left', convention='start')])

    #print('grouping data')
    #timegroup = data['timestamp'] - data['timestamp'] % datetime.timedelta(seconds=10)
    #for x in data:
    #    # aggregate over periods of 10 seconds
    #    x.insert(request_indices['!timegroup'],
    #            x[request_indices['timestamp']] - x[request_indices['timestamp']] % 10)

    ## exclude timestamp, include timegroup
    #data = diagnoser.tools.groupby_dict(data, lambda x: (x[len(keys)-1],) + tuple(x[1:len(keys)-1]))

    print('preprocessing data')
    #data = collections.OrderedDict((k, v) for k, v in data.items() if
    #        None not in v and
    #        k[request_indices['resourcedescription.srcIP']] != '8.8.8.8' or
    #        k[request_indices['resourcedescription.dstIP']] != '8.8.8.8')
    #aggregated_data = diagnoser.aggregation.aggregate(
    #        data, [(f, request_indices[k]) for f, k in aggregations.values()])
    aggregated_data = grouper.aggregate(aggregations)

    #print('formatting json of preprocessed and aggregated data')
    #data_json = collections.OrderedDict((repr(k), v) for k, v in data.items())
    #aggregated_data_json = collections.OrderedDict(
    #        (repr(k), v) for k, v in aggregated_data.items())
    #print(json.dumps(data_json, indent=4))
    #print(json.dumps(aggregated_data_json, indent=4))
    #print()

    aggregated_data.reset_index(inplace=True)
    #aggregated_data.insert(0, 'value', (aggregated_data['resourcedescription.srcIP'].isin(botnet_ips) | aggregated_data['resourcedescription.dstIP'].isin(botnet_ips)).astype('float'))
    #train_data = aggregated_data

    # XXX new dataset is smaller?
    #aggregated_data = aggregated_data.sample(2**10)

    print('running neat')
    #train_data = [v + [float(
    #        k[request_indices['resourcedescription.srcIP']] in botnet_ips and
    #        k[request_indices['resourcedescription.dstIP']] in botnet_ips
    #        )] for k, v in aggregated_data.items()]
    ##labeled_train = [list(k) + v + [1. if
    ##        k[request_indices['resourcedescription.srcIP']] in botnet_ips and
    ##        k[request_indices['resourcedescription.dstIP']] in botnet_ips
    ##        else 0.] for k, v in aggregated_data.items()]
    ##print(json.dumps(train_data[:16], indent=4))
    ##print('IS THIS EMPTY? vvv')
    ##print(json.dumps([x for x in train_data if x[-1]], indent=4))
    ##print(json.dumps([x for x in labeled_train if x[-1]], indent=4))
    ##print('IS THIS EMPTY? ^^^')
    ##input()

    import neat
    #train_data.sort(key=lambda x: (x[-1], sum(x[:-1]), x[:-1]))
    neat_inps = aggregated_data[[
                (k, a[0] if isinstance(a, tuple) else a)
                for k, aggs in aggregations.items() for a in aggs
            ]]
    #neat_outs = [(x[-1],) for x in train_data]
    #neat_outs = pd.DataFrame((aggregated_data['resourcedescription.srcIP'].isin(botnet_ips) | aggregated_data['resourcedescription.destIP'].isin(botnet_ips)).astype('float'))
    #neat_outs = pd.DataFrame(aggregated_data['resourcedescription.srcIP'].isin(zombie_ips) & (aggregated_data['resourcedescription.dstIP'] == c_and_c_ip) & (aggregated_data['resourcedescription.dstPort'] != 'null')).astype('float')
    neat_outs = pd.DataFrame(aggregated_data['resourcedescription.srcIP'].isin(zombie_ips) & (aggregated_data['resourcedescription.dstIP'] == c_and_c_ip) & (aggregated_data['resourcedescription.dstPort'] == '80')).astype('float')

    print(data['resourcedescription.srcIP'])
    print('some attacks:')
    print(neat_outs)
    print(aggregated_data[neat_outs[0].astype('bool')])


    def eval_genomes(genomes, config):
        for genome_id, genome in genomes:
            net = neat.nn.FeedForwardNetwork.create(genome, config)
            total_pos = 0
            fit_pos = 0
            total_neg = 0
            fit_neg = 0
            for xi, xo in zip(neat_inps.values, neat_outs.values):
                output = net.activate(xi)
                if xo[0]:
                    total_pos += 1
                    fit_pos += output[0]>.5
                else:
                    total_neg += 1
                    fit_neg += output[0]<.5
            fpr = 1 - fit_pos/(total_pos or 1)
            fnr = 1 - fit_neg/(total_neg or 1)
            genome.fitness = 1 - diagnoser.aggregation.softmax(fpr, fnr, 16)

    neat_config = neat.Config(
                neat.DefaultGenome,
                neat.DefaultReproduction,
                neat.DefaultSpeciesSet,
                neat.DefaultStagnation,
                config.test_configurations.sp.neat_config,
            )
    population = neat.Population(neat_config)

    # Add a stdout reporter to show progress in the terminal.
    population.add_reporter(neat.StdOutReporter(True))

    # Add graph output on each iteration.
    population.add_reporter(
            GraphReporter(node_names=node_names))

    # Run until a solution is found.
    try:
        #winner = population.run(eval_genomes, 2**16 if config.dry_run else 16)
        winner = population.run(
                eval_genomes, config.test_configurations.sp.neat_generations)
    except KeyboardInterrupt:
        winner = population.best_genome

    # Display the winning genome.
    print('\nSPNEAT: best genome:\n{!s}'.format(winner))
    draw_net(neat_config, winner, node_names=node_names)
    db_model = format_model(config, neat_config, winner, node_names=node_names)
    print(json.dumps(db_model, indent=4))

    print('SPNEAT: storing model in Model DB')
    try:
        diagnoser.modeldb.push_model(config, db_model)
    except diagnoser.modeldb.ModelDBException:
        print('error: SPNEAT: an error occurred while trying to store the '
                'model in the Model DB:')
        traceback.print_exc()

    # Show output of the fittest genome against training data.
    print('SPNEAT: evaluating model:')
    winner_net = neat.nn.FeedForwardNetwork.create(winner, neat_config)
    sample_nos = list(range(len(aggregated_data)))
    estimates = []
    errors = []
    for xi, xo in zip(neat_inps.values, neat_outs.values):
        est, = winner_net.activate(xi)
        estimates.append(max(min(est, 1.5), -.5))
        errors.append((xo[0] and est<.5) or (not xo[0] and est>=.5))
    import random
    for xi, xo, est in random.sample(
            list(zip(neat_inps.values, neat_outs.values, estimates)), min(24, len(neat_inps.values))):
        print('input {}, expected output {}, got {}'.format(
                    ', '.join('{}: {:6.4}'.format(label, inp) for label, inp in
                        zip(expanded_aggregations, xi)), xo[0], est))
    try:
        #import matplotlib.pyplot as plt
        #for i, (feature, label) in enumerate(
        #        zip(zip(*neat_inps.values), expanded_aggregations)):
        #    plt.plot(
        #            sample_nos, [math.log1p(x) for x in feature],
        #            label='{:02}: {}'.format(i+1, label))
        ##plt.plot(sample_nos, pkts, label='packets')
        ##plt.plot(sample_nos, octets, label='octets')
        #plt.plot(sample_nos, [out for out, in neat_outs.values],
        #        color='g', linewidth=4, label='classifiers')
        #plt.plot(sample_nos, estimates, color='b', linewidth=4, label='estimates')
        #plt.plot(sample_nos, errors, color='r', linewidth=4, label='errors')
        #plt.legend()
        #plt.show()
        import matplotlib
        matplotlib.use('agg')
        import matplotlib.pyplot as plt
        import matplotlib.backends.backend_pdf
        with matplotlib.backends.backend_pdf.PdfPages('plot.pdf') as pdf:
            plt.figure(figsize=(1189/25.4, 841/25.4))
            for i, (feature, label) in enumerate(
                    zip(zip(*neat_inps.values), expanded_aggregations)):
                plt.plot(
                        sample_nos, [math.log1p(x) for x in feature],
                        label='{:02}: {}'.format(i+1, label), linewidth=1/8)
            #plt.plot(sample_nos, pkts, label='packets')
            #plt.plot(sample_nos, octets, label='octets')
            plt.plot(sample_nos, [out for out, in neat_outs.values],
                    color='g', linewidth=4, label='classifiers')
            plt.plot(sample_nos, estimates, color='b', linewidth=1/2, label='estimates')
            plt.plot(sample_nos, errors, color='r', linewidth=1/4, label='errors')
            plt.legend()
            #plt.show()
            pdf.savefig()
    except (RuntimeError, ImportError):
        print('SPNEAT: unable to display plot')

    print('SPNEAT: writing task to file')
    task_json = diagnoser.neatmodeltrans.translate_model(
                neat_config,
                winner,
                config.test_configurations.sp.metric_name,
                config.test_configurations.sp.task_name,
                node_names=node_names,
            )
    with open(os.path.join(config.test_configurations.sp.test_output_directory, 'task{}json'.format(os.path.extsep)), 'w') as out:
        json.dump(task_json, out, indent=4)

    #Name of the TASK in Task-manager
    task_name = config.test_configurations.sp.task_name
    #monasca alarm-name
    alarm_name = config.test_configurations.sp.alarm_name
    #Tal-script name
    rule_name = config.test_configurations.sp.rule_name

    # enable this for dry-run
    #if config.dry_run:
    if False:
        print("The following steps were skipped (dry-run):")
        print("- create/update aggregation task:", task_name)
        print("- create monasca alarm:", alarm_name)
        print("- create TAL-script:", rule_name)
        return

    with lock:
        if config.test_configurations.sp.canned_task_file is None:
            print('SPNEAT: sending generated task:\n{}'.format(
                    json.dumps(task_json, indent=4)))
        else:
            with open(config.test_configurations.sp.canned_task_file) as task_json:
                task_json = json.load(task_json)
                task_json['name'] = task_name
                task_json.get('body', {}).get('metrics', [{'name': None}])[0][
                        'name'] = config.test_configurations.sp.metric_name
                print('SPNEAT: sending canned task:\n{}'.format(
                        json.dumps(task_json, indent=4)))
                #print(task_json)
        diagnoser.taskman.send_task(config, task_name, task_json)

        #dimensions = ("SourceIP","DestinationIP","DestinationPort")
        #alarm_expression = "avg({},deterministic,180) >= 0.5 times 3".format(
        #        config.test_configurations.sp.metric_name)
        dimensions = ("SourceIP","DestinationIP","DestinationPort","serviceID")
        alarm_expression = "avg({},deterministic,60) >= 0.6 times 3".format(
                config.test_configurations.sp.metric_name)

        print("Creating alarm: {}".format(alarm_name))
        monasca_client = diagnoser.monasca.MonascaClient(config)
        alarm_id = monasca_client.create_alarm(
                    alarm_name,
                    'CRITICAL',
                    'ai threshold alarm',
                    dimensions,
                    alarm_expression,
                )

        metric_dimensions = {("IP","SourceIP"),
                             ("IP","DestinationIP"),
                             ("Number","DestinationPort", "80")}

        symptom = diagnoser.talcom.create_TAL(
                rule_name, config.test_configurations.sp.metric_name, metric_dimensions)
        xmlstr = xml.dom.minidom.parseString(
                xml.etree.cElementTree.tostring(symptom)).toprettyxml(indent="    ")

        diagnoser.talcom.write_file(rule_name,xmlstr)
        diagnoser.talcom.send_tal(xmlstr, rule_name)
        diagnoser.talcom.disable_oldscripts("SP_LOOP_I")
        diagnoser.talcom.disable_oldscripts("SP_LOOP_II")

        print('SPNEAT: waiting for TAL rule {} to be deactivated'.format(rule_name))
        try:
            for _ in range(16):
                time.sleep(1)
                if not diagnoser.cleanup.check_script(rule_name):
                    #print('SPNEAT: TAL rule {} deactivated'.format(rule_name))
                    print('SPNEAT: Hi Rui, Diagnoser finished. Please clean {} before next call.'.format(rule_name))
                    break
            else:
                print('error: SPNEAT: deactivation of TAL rule {} timed out'.format(
                        rule_name))
        except KeyboardInterrupt:
            pass

        #diagnoser.cleanup.clean_after_loop(task_name, alarm_name, rule_name)
        # TODO: this should be done via a context manager or in a finally block
        monasca_client.close()


def format_model(
        config,
        neat_config,
        genome,
        *,
        node_names=None):
    """
    Convert a NEAT genome to a Model DB entry.

    """

    prune_unused = True
    show_disabled = False

    if node_names is None:
        node_names = {}
    assert type(node_names) is dict

    result = collections.OrderedDict()

    result['id'] = str(uuid.uuid4())

    computation = collections.OrderedDict()
    result['computation'] = computation

    meta = collections.OrderedDict()
    result['meta'] = meta

    # TODO: collect inputs along with aggregation
    outputs = set(neat_config.genome_config.output_keys)
    #name = node_names.get(k, str(k))

    if prune_unused:
        if show_disabled:
            connections = set(cg.key for cg in genome.connections.values())
        else:
            connections = set(cg.key
                    for cg in genome.connections.values() if cg.enabled)
        used_nodes = set(neat_config.genome_config.output_keys)
        pending = set(neat_config.genome_config.output_keys)
        while pending:
            #print(pending, used_nodes)
            pending = set(a for a, b in connections
                    if b in pending and a not in used_nodes)
            used_nodes.update(pending)
    else:
        used_nodes = set(genome.nodes.keys())

    oi_mapping = {n: set() for n in used_nodes}
    for a, b in connections:
        if b in used_nodes:
            oi_mapping[b].add(a)

    ids = {}

    inputs = set(k for k in neat_config.genome_config.input_keys if k in used_nodes)

    for i, inp in enumerate(reversed(sorted(inputs))):
        ids[inp] = 'i{}'.format(i)
        fragments = re.split('([A-Z])', node_names[inp])
        name = ''.join(fragments[:-2])
        aggregation = ''.join(fragments[-2:]).lower()
        computation[ids[inp]] = collections.OrderedDict([
                    ('type', 'aggregation'),
                    ('inputs', [''.join(fragments[:-2])]),
                    ('operation', ''.join(fragments[-2:]).lower()),
                    ('period', 10),
                ])

    for i, node in enumerate(sorted(used_nodes - inputs)):
        ids[node] = 'n{}'.format(i)

    n_nodes = len(used_nodes - inputs)
    n_constants = 0

    for i, node in enumerate(sorted(used_nodes - inputs)):
        inps = []
        for inp in oi_mapping[node]:
            const_id = 'p{}'.format(n_constants)
            n_constants += 1
            computation[const_id] = collections.OrderedDict([
                        ('type', 'constant'),
                        ('value', genome.connections[inp, node].weight),
                    ])
            prod_id = 'n{}'.format(n_nodes)
            n_nodes += 1
            computation[prod_id] = collections.OrderedDict([
                        ('type', 'operation'),
                        ('operation', 'product'),
                        ('inputs', [ids[inp], const_id]),
                    ])
            inps.append(prod_id)
        agg_id = 'n{}'.format(n_nodes)
        n_nodes += 1
        computation[agg_id] = collections.OrderedDict([
                    ('type', 'operation'),
                    ('operation', genome.nodes[node].aggregation),
                    ('inputs', inps),
                ])
        const_id = 'c{}'.format(n_constants)
        n_constants += 1
        computation[const_id] = collections.OrderedDict([
                    ('type', 'constant'),
                    ('value', genome.nodes[node].response),
                ])
        resp_id = 'n{}'.format(n_nodes)
        n_nodes += 1
        computation[resp_id] = collections.OrderedDict([
                    ('type', 'operation'),
                    ('operation', 'product'),
                    ('inputs', [agg_id, const_id]),
                ])
        const_id = 'c{}'.format(n_constants)
        n_constants += 1
        computation[const_id] = collections.OrderedDict([
                    ('type', 'constant'),
                    ('value', genome.nodes[node].bias),
                ])
        bias_id = 'n{}'.format(n_nodes)
        n_nodes += 1
        computation[bias_id] = collections.OrderedDict([
                    ('type', 'operation'),
                    ('operation', 'sum'),
                    ('inputs', [resp_id, const_id]),
                ])
        computation[ids[node]] = collections.OrderedDict([
                    ('type', 'operation'),
                    ('operation', genome.nodes[node].activation),
                    ('inputs', [bias_id]),
                ])
    const_id = 'p{}'.format(n_constants)
    n_constants += 1
    computation[const_id] = collections.OrderedDict([
                ('type', 'constant'),
                ('value', .5),
            ])
    for i, node in enumerate(sorted(outputs)):
        le_id = 'n{}'.format(n_nodes)
        n_nodes += 1
        computation[le_id] = collections.OrderedDict([
                    ('type', 'operation'),
                    ('operation', 'le'),
                    ('inputs', [ids[node], const_id]),
                ])
        filt_id = 'n{}'.format(n_nodes)
        n_nodes += 1
        computation[filt_id] = collections.OrderedDict([
                    ('type', 'filter'),
                    ('operation', 'avg'),
                    ('inputs', [le_id]),
                    ('period', 180),
                    ('num-periods', 3),
                ])
        out_id = 'o{}'.format(i)
        computation[out_id] = collections.OrderedDict([
                    ('type', 'output'),
                    ('inputs', [filt_id]),
                ])

    meta["active"] = True
    meta["activity-reason"] = "original instantiation"
    meta["generated-by"] = "genesis-neat"
    meta["generated-from"] = "cassandra-raw-data"
    meta["metric-name"] = config.test_configurations.sp.metric_name
    meta["agg-task-name"] = config.test_configurations.sp.task_name
    meta["alarm-name"] = config.test_configurations.sp.alarm_name
    meta["tal-script-name"] = config.test_configurations.sp.rule_name

    return result


def draw_net(
        neat_config,
        genome,
        view=False,
        filename=os.path.join('output', 'neat' + os.path.extsep + 'gv'),
        node_names=None,
        show_disabled=True,
        prune_unused=True,
        node_colors=None,
        fmt='svg'):
    """
    Draw the neural network corresponding to the given genome.

    """

    if graphviz is None:
        warnings.warn(
                'This display is not available due to a missing optional '
                'dependency (graphviz)')
        return

    if node_names is None:
        node_names = {}
    assert isinstance(node_names, collections.abc.Mapping)

    if node_colors is None:
        node_colors = {}
    assert isinstance(node_colors, collections.abc.Mapping)

    graph_attr = {
                'rankdir': 'LR',
            }

    node_attrs = {
                'shape': 'circle',
                #'fontsize': '9',
                'height': '0.2',
                'width': '0.2',
            }

    dot = graphviz.Digraph(
            format=fmt, graph_attr=graph_attr, node_attr=node_attrs)

    outputs = set()
    for k in neat_config.genome_config.output_keys:
        outputs.add(k)
        name = node_names.get(k, str(k))
        node_attrs = {'style': 'filled'}
        node_attrs['fillcolor'] = node_colors.get(k, 'lightblue')
        dot.node(name, _attributes=node_attrs)

    if prune_unused:
        connections = set()
        for cg in genome.connections.values():
            if cg.enabled or show_disabled:
                connections.add(cg.key)
        used_nodes = set(outputs)
        pending = set(outputs)
        while pending:
            #print(pending, used_nodes)
            new_pending = set()
            for a, b in connections:
                if b in pending and a not in used_nodes:
                    new_pending.add(a)
                    used_nodes.add(a)
            pending = new_pending
    else:
        used_nodes = set(genome.nodes.keys())

    inputs = set()
    for k in neat_config.genome_config.input_keys:
        if k not in used_nodes:
            continue
        inputs.add(k)
        name = node_names.get(k, str(k))
        input_attrs = {'style': 'filled', 'shape': 'box'}
        input_attrs['fillcolor'] = node_colors.get(k, 'lightgray')
        dot.node(name, _attributes=input_attrs)

    for n in used_nodes:
        if n in inputs:
            continue

        np = vars(genome.nodes[n])
        np['sign'] = '-' if np['bias'] < 0 else '+'
        np['abias'] = abs(np['bias'])
        attrs = {}
        if n not in outputs:
            attrs['style'] = 'filled'
            attrs['fillcolor'] = node_colors.get(n, 'white')
        name = node_names.get(n)
        namenl = '{}\\l'.format(name) if name is not None else ''
        if name is None:
            name = n
        attrs['label'] = namenl + (
                    '{activation}(\\l  {aggregation}(...)\\l'
                    '      * {response:4.2}\\l    {sign} {abias:4.2})\\l'
                ).format(**np)
        dot.node(str(name), _attributes=attrs)

    for cg in genome.connections.values():
        if cg.enabled or show_disabled:
            input, output = cg.key
            if input not in used_nodes or output not in used_nodes:
                continue
            a = node_names.get(input, str(input))
            b = node_names.get(output, str(output))
            style = 'solid' if cg.enabled else 'dotted'
            color = 'green' if cg.weight > 0 else 'red'
            width = str(0.1 + abs(cg.weight / 5.0))
            dot.edge(a, b, _attributes={
                        'style': style,
                        'color': color,
                        'penwidth': width,
                        'label': '{:4.2}'.format(cg.weight)
                    })

    dot.render(filename, view=view)

    return dot


class GraphReporter(neat.reporting.BaseReporter):

    def __init__(self, *, node_names=None):
        super().__init__()
        self.node_names = node_names
        self.generation = 0

    def start_generation(self, generation):
        self.generation = generation

    #def end_generation(self, config, population, species_set):
    #    best_genome = None
    #    for g in population.values():
    #        if g.fitness is not None and (
    #                best_genome is None or g.fitness > best_genome.fitness):
    #            best_genome = g
    #    ...

    def post_evaluate(self, config, population, species, best_genome):
        if best_genome is None:
            return
        draw_net(config, best_genome, node_names=self.node_names)
        limit = 4
        def filename(species_rank, genome_rank):
            return os.path.join('output', 'neat_s{:02}_g{:02}'.format(
                    species_rank, genome_rank) + os.path.extsep + 'gv')
        def filename_svg(species_rank, genome_rank):
            return filename(species_rank, genome_rank) + '.svg'
        sorted_species = sorted(species.species.values(),
                key=lambda s: max(s.get_fitnesses()), reverse=True)
        sorted_genomes = [[] for _ in range(len(sorted_species))]
        for i, s in zip(range(limit), sorted_species):
            sorted_genomes[i] = sorted(s.members.values(),
                    key=lambda g: g.fitness, reverse=True)
            for j, g in zip(range(limit), sorted_genomes[i]):
                #print('visualizing {}, {}: (fitness: {})'.format(
                #        i, j, g.fitness))
                draw_net(config, g, filename=filename(i, j),
                        node_names=self.node_names)
            for j in range(len(sorted_genomes[i]), limit):
                with open(filename_svg(i, j), 'w'):
                    pass
        for i in range(len(sorted_species), limit):
            for j in range(limit):
                with open(filename_svg(i, j), 'w'):
                    pass
        nets_table = [
                    [
                        {
                            'svg': filename_svg(i, j)[
                                len('output'+os.path.sep):],
                            'fitness': genome.fitness,
                        }
                        for j, genome in zip(range(limit), spec)
                    ]
                    for i, spec in zip(range(limit), sorted_genomes)
                ]
        species_table = [
                    {
                        'id': key,
                        'age': self.generation - s.created,
                        'size': len(s.members),
                        'fitness': 'n/a' if s.fitness is None else
                            '{:6.4f}'.format(s.fitness),
                        'adjfit': 'n/a' if s.adjusted_fitness is None else
                            '{:6.4f}'.format(s.adjusted_fitness),
                        'stag': self.generation-s.last_improved,
                    }
                    for key, s in sorted(species.species.items())
                ]
        with open(os.path.join('tests', 'sp',
                'index_html_template'+os.path.extsep+'txt')) as template_file:
            template = template_file.read()
        output = jinja2.Template(template).render(
                    nets=nets_table,
                    n_genomes=len(population),
                    n_species=len(species.species),
                    species=species_table,
                )
        with open(os.path.join('output', 'index'+os.path.extsep+'html'),
                'w') as index_html:
            index_html.write(output)


