# -*- encoding: utf-8 -*-
"""Base command for plinko classic"""
import click
from logzero import logger
from plinko import helpers
from plinko.classic import core
from plinko import logger as plog


@click.command()
@click.option(
    "--clix-diff",
    help="Path to a clix compact diff file.",
    type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "--apix-diff",
    help="Path to an apix compact diff file.",
    type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "--pytest-export",
    help="Path to a file containing the output of pytest --collect-only.",
    prompt=True,
    type=click.Path(exists=True, dir_okay=False),
)
@click.option("--allow-dupes", help="Allow multiples of the same test.", is_flag=True)
def classic(clix_diff, apix_diff, pytest_export):
    if not pytest_export:
        logger.warning("You must provide a pytest --collect-only output file.")
        return
    project_name = helpers.get_pt_project_name(pytest_export)
    if not project_name:
        logger.warning(f"Unable to determine project name from {pytest_export}")
        return
    if clix_diff:
        product_ver = helpers.get_version(clix_diff)
        res = core.plink_clix(clix_diff, pytest_export)
        logger.info(f"Found {len(res['missing'])} uncovered methods.")
        helpers.write_to_file(
            res["missing"],
            f"projects/{project_name}/cli/{product_ver}/missing-coverage.txt",
            "missing coverage",
        )
        if res:
            clix_pt = helpers.plinko_to_ptcommand(res["found"], allow_dupes)
            if clix_pt:
                logger.debug(clix_pt)
        helpers.write_to_file(
            clix_pt,
            f"projects/{project_name}/cli/{product_ver}/diff-tests.txt",
            "pytest arguments",
        )
    if apix_diff:
        product_ver = helpers.get_version(apix_diff)
        res = core.plink_apix(apix_diff, pytest_export)
        logger.info(f"Found {len(res['missing'])} uncovered methods.")
        helpers.write_to_file(
            res["missing"],
            f"projects/{project_name}/api/{product_ver}/missing-coverage.txt",
            "missing coverage",
        )
        if res:
            apix_pt = helpers.plinko_to_ptcommand(res["found"], allow_dupes)
            if apix_pt:
                logger.debug(apix_pt)
        helpers.write_to_file(
            apix_pt,
            f"projects/{project_name}/api/{product_ver}/diff-tests.txt",
            "pytest arguments",
        )
