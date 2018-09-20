#!/usr/bin/env python3


import argparse
import collections
import json
import os
import sys

import jsonschema

import yaml


class ClearAction(argparse.Action):

    def __init__(
            self, option_strings, dest, nargs=None, const=None, default=None,
            type=None, choices=None, required=False, help=None, metavar=None):
        super().__init__(
            option_strings, dest, None, const, default,
            type, choices, requirede, help, metavar)

    def __call__(self, parser, namespace, values, option_string=None):
        l = getattr(namespace, self.dest)
        if l is not None:
            l.clear()


class ConfigDict(collections.OrderedDict):

    def __getattr__(self, name):
        return self.get(name.replace('_', '-'))


class Config(ConfigDict):

    def __init__(self, argv=sys.argv, environ=os.environ, description=None):
        super().__init__()

        # get paths from environment
        self.home_dir = environ.get('HOME', '')
        self.prog = argv[0]
        self.prog_dir = os.path.dirname(os.path.abspath(self.prog))
        self.src_dir = os.path.dirname(os.path.abspath(__file__))
        # TODO: unify filename handling, every filename entry should be marked
        #       with a special format value or similar; while reading the
        #       configuration, the prefixes (~, $...) should be converted to
        #       the corresponding paths

        # generate filenames of meta-schema, schema, and default config
        self.meta_schema_filename = os.path.join(
                self.src_dir, 'meta-schema.json')
        self.config_schema_filename = os.path.join(
                self.src_dir, 'config-schema.yaml')
        self.config_filename = os.path.join(self.src_dir, 'config.yaml')

        # read meta-schema and schema, validate schema
        self.meta_schema = json.load(open(self.meta_schema_filename))
        self.config_schema = self.ordered_load(
                open(self.config_schema_filename))
        jsonschema.validate(self.config_schema, self.meta_schema)

        # TODO: get default values from schema
        #self['kafka-frontend'] = {
        #        'topics': {'topic': None},
        #        'bootstrap-servers': 'localhost:9092',
        #    }
        #self['kafka-backend'] = {
        #        'topics': {None: 'topic'},
        #        'bootstrap-servers': 'localhost:9092',
        #    }

        # action nargs const default type choices required help metavar dest

        # parse command line arguments, generate options from schema
        self.parser = argparse.ArgumentParser(
                prog=self.prog,
                description=description)
        for k, v in self.config_schema['properties'].items():
            # TODO: this should recurse into items of object type
            if not v.get('cl'):
                continue
            cl_short = '-' + v['cl-short'] if 'cl-short' in v else None
            cl_long = '--' + v.get('cl-long', k)
            action = v.get('action')
            typ = v.get('type')
            if isinstance(typ, list):
                typ = [t for t in typ if t != 'null']
                if len(typ) == 1:
                    typ = typ[0]
            typ = {
                    'array': list,
                    'boolean': bool,
                    'integer': int,
                    'number': float,
                    'null': type(None),
                    'object': dict,
                    'string': str,
                }.get(typ)
            dest = v.get(
                'dest', k.replace('-', '_') if cl_long is not None else None)
            metavar = v.get(
                'metavar',
                v['cl-long'].upper() if typ != bool and 'cl-long' in v else None)
            nargs = None
            default = v.get('default')
            hlp = v.get('description')
            if 'enum' in v:
                hlp += '; possible choices: {}'.format(', '.join(
                    '"{}"'.format(val)
                    for val in v['enum'] if val is not None))
            action = None
            if action is None:
                if typ == bool:
                    action = 'store_false' if default else 'store_true'
            elif action == 'clear':
                action = ClearAction
                nargs = 0
            #else:
            #    action = 'store'
            if action in ['store_false', 'store_true']:
                typ = None
            self.parser.add_argument(
                *(arg for arg in [cl_short, cl_long] if arg is not None),
                **{k: v for k, v in {
                    'action': action,
                    'dest': dest,
                    'help': hlp,
                    'metavar': metavar,
                    'nargs': nargs,
                    'type': typ,
                }.items() if v is not None})
        args = self.parser.parse_args(argv[1:])

        # read config files
        processed_configs = []
        configs = (
            ([] if args.no_default_configs else [self.config_filename]) +
            (args.configs or []))
        if not args.configs and not args.no_default_configs:
            configs = [self.config_filename]
        else:
            configs = ([] if args.no_default_configs else
                args.additional_configs.copy())
        while configs:
            f = configs.pop(0)
            if f.startswith('~'):
                f = os.path.join(self.home_dir, f[len('~' + os.path.sep):])
            elif f.startswith(os.path.pardir):
                f = os.path.join(self.prog_dir, os.path.pardir,
                        f[len(os.path.pardir + os.path.sep):])
            elif f.startswith(os.path.curdir):
                f = os.path.join(
                        self.prog_dir, f[len(os.path.curdir + os.path.sep):])
            if f not in processed_configs and os.path.isfile(f):
                configs.extend(self.read_config(self.ordered_load(open(f))))
                processed_configs.append(f)

        # override configuration values with command line options
        # TODO: this needs to be more sophisticated in order to support
        #       override of nested configuration options
        self.update(vars(args))

    def read_config(self, config):
        jsonschema.validate(config, self.config_schema)
        for k, v in config.items():
            # TODO: append to lists, support clears
            self[k] = v
        return config.get('additional-configs', [])

    def ordered_load(
            self, stream, Loader=yaml.Loader, object_pairs_hook=ConfigDict):
        class OrderedLoader(Loader):
            pass
        def construct_mapping(loader, node):
            loader.flatten_mapping(node)
            return object_pairs_hook(loader.construct_pairs(node))
        OrderedLoader.add_constructor(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            construct_mapping)
        return yaml.load(stream, OrderedLoader)


