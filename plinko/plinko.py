"""Base command for plinko, linking to actual functionality"""
import click
from logzero import logger
from plinko import helpers
from plinko.simple_config import config
from plinko import code_parser


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
    "--test-directory",
    help="Path to the directory that contains your tests.",
    type=click.Path(exists=True, dir_okay=True),
    prompt=True,
)
@click.option(
    "--behavior",
    help="How Plinko should limit returned tests.",
    type=click.Choice(["all", "no-dupes", "minimal"]),
    prompt=True,
)
@click.option(
    "--depth",
    help="Max depth of recursive method resolutions.",
    type=click.IntRange(0, 20),
    prompt=True,
)
@click.option(
    "--search-aggressiveness",
    help="Specify how aggressively Plinko should search for entity names.",
    type=click.Choice(["low", "med", "high"]),
    default=config.search_aggressiveness,
)
@click.option(
    "--name",
    help="The name of your project.",
    type=str,
    prompt=True,
)
def entry_point(clix_diff, apix_diff, test_directory, behavior, depth, search_aggressiveness, name):
    if not test_directory:
        logger.warning("You must provide a test directory path.")
        return
    if clix_diff:
        product_ver = helpers.get_version(clix_diff)
        diff_dict = helpers.get_diff_dict(clix_diff, flatten=False)
        helpers.del_from_iter(name, diff_dict)
        parser = code_parser.CodeParser(
            entity_methods=diff_dict,
            max_depth=depth,
            behavior=behavior,
            search_aggressiveness=search_aggressiveness
        )
        parser.parse_directory(test_directory)
        helpers.write_to_file(
            parser.cov_tests,
            f"projects/{name}/cli/{product_ver}/test-coverage.yaml",
            "tests with coverage",
        )
        helpers.write_to_file(
            parser.miss_tests,
            f"projects/{name}/cli/{product_ver}/test-no-coverage.yaml",
            "tests without coverage",
        )
        if behavior == "minimal":
            helpers.write_to_file(
                helpers.get_min_tests(parser.cov_tests),
                f"projects/{name}/cli/{product_ver}/min-tests.yaml",
                "minimal tests",
            )
    if apix_diff:
        product_ver = helpers.get_version(apix_diff)
        diff_dict = helpers.get_diff_dict(apix_diff, flatten=False)
        helpers.del_from_iter(name, diff_dict)
        parser = code_parser.CodeParser(
            entity_methods=diff_dict,
            max_depth=depth,
            behavior=behavior,
            search_aggressiveness=search_aggressiveness
        )
        parser.parse_directory(test_directory)
        helpers.write_to_file(
            parser.cov_tests,
            f"projects/{name}/api/{product_ver}/test-coverage.yaml",
            "tests with coverage",
        )
        helpers.write_to_file(
            parser.miss_tests,
            f"projects/{name}/api/{product_ver}/test-no-coverage.yaml",
            "tests without coverage",
        )
        if behavior == "minimal":
            helpers.write_to_file(
                helpers.get_min_tests(parser.cov_tests),
                f"projects/{name}/api/{product_ver}/min-tests.yaml",
                "minimal tests",
            )
