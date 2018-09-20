#!/usr/bin/env python3


def run_sp_test(*args, **kwargs):
    import diagnoser.testsp
    return diagnoser.testsp.run(*args, **kwargs)


def run_sh_test(*args, **kwargs):
    import diagnoser.testsh
    return diagnoser.testsh.run(*args, **kwargs)


