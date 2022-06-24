"""Base command for plinko."""
import click
from logzero import logger

from plinko import code_parser, helpers, logger as plog
from plinko.config import PLINKO_DATA_DIR, settings


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
    default=settings.behavior,
)
@click.option(
    "--depth",
    help="Max depth of recursive method resolutions.",
    type=click.IntRange(0, 20),
    default=settings.max_depth,
)
@click.option(
    "--search-aggressiveness",
    help="Specify how aggressively Plinko should search for entity names.",
    type=click.Choice(["low", "med", "high"]),
    default=settings.search_aggressiveness,
)
@click.option(
    "--name",
    help="The name of your project.",
    type=str,
    prompt=True,
)
@click.option("--log-level", help="Log level", default=settings.log_level)
def cli(
    clix_diff, apix_diff, test_directory, behavior, depth, search_aggressiveness, name, log_level
):
    plog.setup_logzero(log_level.lower())
    def run_reports(interface, diff_path):
        """Run the reports for the given interface and diff file."""
        product_ver = helpers.get_version(diff_path)
        diff_dict = helpers.get_diff_dict(diff_path, flatten=False)
        helpers.del_from_iter(name, diff_dict)
        parser = code_parser.CodeParser(
            entity_methods=diff_dict,
            max_depth=depth,
            behavior=behavior,
            search_aggressiveness=search_aggressiveness,
        )
        parser.parse_directory(test_directory)
        helpers.write_to_file(
            helpers.expand_dict_keys(parser.cov_tests),
            f"{PLINKO_DATA_DIR}/projects/{name}/{interface}/{product_ver}/test-coverage.yaml",
            "tests with coverage",
        )
        helpers.write_to_file(
            helpers.expand_dict_keys(parser.miss_tests),
            f"{PLINKO_DATA_DIR}/projects/{name}/{interface}/{product_ver}/test-no-coverage.yaml",
            "tests without coverage",
        )
        if behavior == "minimal":
            helpers.write_to_file(
                helpers.expand_dict_keys(helpers.get_min_tests(parser.cov_tests)),
                f"{PLINKO_DATA_DIR}/projects/{name}/{interface}/{product_ver}/min-tests.yaml",
                "minimal tests",
            )

    # Run the reports for the given interface and diff file(s)
    if not test_directory:
        logger.warning("You must provide a test directory path.")
        return
    if clix_diff:
        run_reports("cli", clix_diff)
    if apix_diff:
        run_reports("api", apix_diff)
    if not clix_diff and not apix_diff:
        logger.error("You must provide a diff file.")


if __name__ == "__main__":
    cli()
