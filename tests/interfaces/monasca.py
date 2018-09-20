#!/usr/bin/env python3


import os
import sys


sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        os.path.pardir,
        os.path.pardir))


import diagnoser.config
import diagnoser.monasca


if __name__ == '__main__':
    config = diagnoser.config.Config()
    mc = diagnoser.monasca.RealMonascaClient(config)
    print(mc.get_notification_id())


