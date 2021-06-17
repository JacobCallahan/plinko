# -*- encoding: utf-8 -*-
"""Base command for plinko, linking to actual functionality"""
import click
from logzero import logger
from plinko.classic import commands as classic
from plinko.deep import commands as deep
from plinko.simple_config import config
from plinko import logger as plog


@click.group()
@click.option("--debug", is_flag=True)
def entry_point(debug):
    if debug or config.debug:
        plog.setup_logzero(level="debug")

entry_point.add_command(classic.classic)
entry_point.add_command(deep.deep)
