# -*- encoding: utf-8 -*-
"""The core methods for Plinko"""
import click
from pathlib import Path
from logzero import logger
from plinko import helpers


def pyt_collect_to_dict(collect_path):
    """Turn pytest --collect-only output into a dictionary"""
    test_dir = {}
    function_text = "<Function "
    with Path(collect_path).open("r") as pt:
        logger.debug("In the file...")
        latest_mod, latest_class = None, None
        for line in pt:
            # Unittest has a different output than pure pytest
            if function_text == "<Function " and "<UnitTestCase" in line:
                logger.debug("Unittest!!")
                function_text = "<TestCaseFunction "
            if "<Module " in line:
                latest_mod = line.split("<Module ")[1][1:-3]
            elif "<UnitTestCase " in line:
                latest_class = line.split("<UnitTestCase ")[1][1:-3]
                if not test_dir.get(latest_mod):
                    test_dir[latest_mod] = {latest_class: []}
                else:
                    test_dir[latest_mod][latest_class] = []
            elif function_text in line:
                if latest_class:
                    test_dir[latest_mod][latest_class].append(
                        line.split(function_text)[1][1:-3]
                    )
                else:
                    if not test_dir.get(latest_mod):
                        test_dir[latest_mod] = [line.split(function_text)[1][1:-3]]
                    else:
                        test_dir[latest_mod].append(line.split(function_text)[1][1:-3])
    return test_dir


def find_test_match(feature, method, test_dict, interface=None, max_res=3):
    """Parse through the pytest dict to find a matching test"""
    matching_modules = []
    if feature[-1] == "s":  # we don't want plurals
        feature = feature[:-1]
    normalized_feature = helpers.normalize(feature, prefer_spaces=False)
    normalized_method = helpers.normalize(method)
    for module in test_dict.keys():
        if helpers.match_all(normalized_feature, helpers.normalize(module)):
            matching_modules.append(module)
    if matching_modules:
        matching_tests = {}
        for module in matching_modules:
            if interface and not helpers.match_all(
                [interface], helpers.normalize(module)
            ):
                continue
            if isinstance(test_dict[module], dict):  # unitest style
                for test_class in test_dict[module].keys():
                    for function in test_dict[module][test_class]:
                        if helpers.match_all(
                            normalized_method, helpers.normalize(function)
                        ):
                            logger.debug(f"matched {function}")
                            if not matching_tests.get(module):
                                matching_tests[module] = {}
                            if not matching_tests[module].get(test_class):
                                matching_tests[module][test_class] = []
                            if len(matching_tests[module][test_class]) < max_res:
                                matching_tests[module][test_class].append(function)
            else:  # normal pytest style
                for function in test_dict[module]:
                    if helpers.match_all(
                        normalized_method, helpers.normalize(function)
                    ):
                        if not matching_tests.get(module):
                            matching_tests[module] = []
                        if matching_tests[module] < max_res:
                            matching_tests[module].append(function)
        return matching_tests
    else:
        return None


def plink_clix(diff_path, pt_export_path):
    """Parse a clix version/diff dict and find any matching tests"""
    diff_dict = helpers.get_diff_dict(diff_path)
    pt_dict = pyt_collect_to_dict(pt_export_path)
    if not diff_dict or not pt_dict:
        logger.warning("Please check supplied files for clix-diff and pytest-export...")
        return
    logger.debug(diff_dict)
    plink_results = {"found": [], "missing": []}
    with click.progressbar(diff_dict, label="Finding test matches") as d_dict:
        for test in d_dict:
            logger.debug(f"test - {test}")
            split_test = test.split()
            results = find_test_match(
                split_test[1], " ".join(split_test[2:]), pt_dict, "cli"
            )
            logger.debug(results)
            if results:
                plink_results["found"].append([test, results])
            else:
                plink_results["missing"].append(test)
    return plink_results


def plink_apix(diff_path, pt_export_path):
    """Parse an apix version/diff dict and find any matching tests"""
    diff_dict = helpers.get_diff_dict(diff_path)
    pt_dict = pyt_collect_to_dict(pt_export_path)
    if not diff_dict or not pt_dict:
        logger.warning("Please check supplied files for clix-diff and pytest-export...")
        return
    logger.debug(diff_dict)
    plink_results = {"found": [], "missing": []}
    with click.progressbar(diff_dict, label="Finding test matches") as d_dict:
        for test in d_dict:
            logger.debug(f"test - {test}")
            split_test = test.split()
            results = find_test_match(
                split_test[0], " ".join(split_test[1:]), pt_dict, "api"
            )
            logger.debug(results)
            if results:
                plink_results["found"].append([test, results])
            else:
                plink_results["missing"].append(test)
    return plink_results


def plinko_to_ptcommand(plinko_results, allow_dupes=False):
    pytest_list = []
    for feature in plinko_results:
        file_name = list(feature[1].keys())[0]
        if isinstance(feature[1][file_name], dict):  # unittest style
            for test_class in feature[1][file_name].keys():
                for test in feature[1][file_name][test_class]:
                    pytest_list.append(f"{file_name}::{test_class}::{test}")
        else:
            for test in feature[1][file_name]:
                pytest_list.append(f"{file_name}::{test}")
    if not allow_dupes:
        pytest_list = set(pytest_list)
        logger.info(f"Found {len(pytest_list)} unique tests.")
    return " ".join(pytest_list)
