from plinko import helpers
from plinko.deep import code_parser

# def test_robottelo_api():
#     CliRunner().invoke(entry_point, [
#         "deep",
#         "--apix-diff", "/home/jake/Programming/apix/APIs/satellite6/6.8.0s15-comp.yaml",
#         "--test-directory", "/home/jake/Programming/robottelo/tests/foreman/api/test_activationkey.py",
#         "--behavior", "minimal",
#         "--depth", "5",
#         "--search-aagressiveness", "med",
#         "--name", "robottelo",
#     ])


apix_diff = "/home/jake/Programming/apix/APIs/satellite6/6.8.0s15-comp.yaml"
test_directory = "/home/jake/Programming/robottelo/tests/foreman/api/test_activationkey.py"
name = "robottelo"
depth = 5
behavior = "minimal"
search_aggressiveness = "med"

def test_robottelo_api():
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
