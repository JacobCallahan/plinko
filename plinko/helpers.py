"""A collection of miscellaneous helpers that don't quite fit in."""
from pathlib import Path

import click
from logzero import logger
import yaml

from plinko.config import BANNED_DIRS, PLINKO_DATA_DIR


def import_yaml(fpath):
    imported = {}
    with Path(fpath).open() as opened:
        try:
            imported = yaml.load(opened, Loader=yaml.FullLoader)
        except Exception as e:
            logger.warning(f"Unable to load {fpath} due to {e}")
    return imported


def normalize(reg_string, prefer_spaces=True, ret_string=False):
    """Make sure everything is lowercase and remove _ and -."""
    space = " " if prefer_spaces else ""
    result = list(reg_string.lower()
        .replace("_", " ")
        .replace("/", " ")
        .replace("-", space)
        .replace("s.py", "")
        .replace(".py", "")
        .split())
    return "".join(result) if ret_string else result


def del_from_iter(needle, haystack, keep_children=True):
    """Remove an entry from an iterable, optionally keeping all its children."""
    if isinstance(haystack, dict):
        if needle in haystack:
            children = haystack[needle]
            if isinstance(children, dict):
                haystack.update(children)
            else:
                if len(haystack.keys()) == 1:
                    haystack = children
                elif "orphans" in haystack:
                    haystack["orphans"].append(children)
                else:
                    haystack["orphans"] = [children]
            del haystack[needle]
        else:
            for val in haystack.values():
                del_from_iter(needle, val, keep_children)
    elif isinstance(haystack, list):
        if needle in haystack:
            haystack.remove(needle)


def match_all(needles, haystack):
    """Check to see if all needles are in the haystack."""
    if not isinstance(needles, list) or not isinstance(haystack, list):
        logger.debug(
            f"match_all failed with needles: {needles} and haystack: {haystack}"
        )
        return
    logger.debug(f"searching for {needles} in {haystack}")
    for needle in needles:
        if needle not in haystack:
            return
    return True


def gen_variants(text):
    """Return a number of common variants to naming conventions."""
    low_str = text.lower()  # all lowercase
    up_str = text.upper()  # all uppercase
    return [low_str, up_str, f"{low_str}s", f"{up_str}S"]


def get_coverage(method, method_dict, coverage=None, chain=None):
    """Recursively chase down coverage for a method, returning a list of what is covered."""
    # recursion safety
    if not chain:
        chain = set()
    elif method in chain:
        return method_dict[method].covers
    else:
        chain.update(method)
    # now recursivley determine the coverage
    if getattr(method_dict.get(method), "covers", None) is None:
        # This is an unresolved method
        return
    if coverage:
        coverage.update(method_dict[method].covers)
    else:
        coverage = method_dict[method].covers.copy()  # copy it to avoid mutating the original
    for call in method_dict[method].calls:
        call_covers = get_coverage(call, method_dict, coverage, chain)
        if call_covers:
            coverage.update(call_covers)
    return coverage


def _identify_not_needed(min_coverage, all_coverage):
    """Identify tests that are not needed."""
    def count_in_list(needle, haystack):
        """Count the number of times a needle appears in a list."""
        return sum(1 for x in haystack if x == needle)

    for name, coverage in min_coverage.items():
        if all(count_in_list(cov, all_coverage) > 1 for cov in coverage):
            return name


def get_min_tests(test_dict, test_startswith="test_", compile_cov=False):
    """Takes in a dict, mapping method names to what they cover.
    returns a dict of tests that cover everything with as little overlap as possible.
    """
    if compile_cov:
        compiled_coverage = {}
        for method in test_dict:
            if test_startswith in method:
                compiled_coverage[method] = get_coverage(method, test_dict)
    else:
        compiled_coverage = test_dict.copy()
    min_coverage = {}
    all_coverage = []  # a running list of featues covered
    # now we want to sort our test from most to least coverage
    sorted_tests = sorted(
        compiled_coverage, key=lambda covs: len(compiled_coverage[covs]), reverse=True
    )
    for test in sorted_tests:
        to_add = False
        for covered in compiled_coverage[test]:
            if covered not in all_coverage and not to_add:
                # this test add coverage, so we'll add it in
                to_add = True
                break
        min_coverage[test] = compiled_coverage[test]
        all_coverage.extend(compiled_coverage[test])
    # now we make sure tests that are not needed are removed
    while (to_remove := _identify_not_needed(min_coverage, all_coverage)):
        del min_coverage[to_remove]
        all_coverage = [c for covs in min_coverage.values() for c in covs]
    return min_coverage


def get_pt_project_name(pt_export):
    """Strip the project name from the pytest export's rootdir line."""
    with Path(pt_export).open() as pt_file:
        for line in pt_file:
            if "rootdir:" in line:
                return line.split(",")[0].split("/")[-1]


def get_version(diff_file, ix=True):
    """Determine the product version from the diff file name.
    param ix denotes if the diff file was generated by APIx or CLIx.
    """
    split_ver = diff_file.split("/")[-1].split("-")
    if "-comp.yaml" in diff_file:
        return split_ver[0]
    else:
        return f"{split_ver[0]}-to{split_ver[2]}"


def write_to_file(data, path, name="results"):
    """Write the data to the specified location, creating path and deleting old contents if necessary."""
    path = Path(path)
    if not path.is_absolute():
        path = PLINKO_DATA_DIR / path
    if path.exists():
        logger.warning(f"Deleting previous {name} file: {path.absolute()}")
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    logger.info(f"Saving {name} to {path.absolute()}")
    with path.open("w+") as outfile:
        yaml.dump(data, outfile, default_flow_style=False)


def flatten_mixed(data, outlist=None, parents=""):
    """Flatten a data structure of nested lists and dicts into a single list."""
    if outlist is None:
        outlist = []
    if isinstance(data, dict):
        [
            flatten_mixed(children, outlist, f"{parents} {key}")
            for key, children in data.items()
        ]
    elif isinstance(data, list):
        [flatten_mixed(child, outlist, parents) for child in data]
    else:
        outlist.append(f"{parents} {data}".strip())
    return outlist


def normalize_text(in_str, style):
    """Format a string to match the style pattern expected."""
    decomposed_str = in_str.lower().replace("-", " ").replace("_", " ").split()
    # check if the trailing S needs to be stripped
    if style[-1] not in ["s", "S"]:
        if decomposed_str[-1][-1] == "s" and decomposed_str[-1][-2] != "s":
            decomposed_str[-1] = decomposed_str[-1][:-1]
    if style == "ExampleName":
        return "".join(x.capitalize() for x in decomposed_str)
    elif style == "example_name":
        return "_".join(decomposed_str)
    elif style == "example-name":
        return "-".join(decomposed_str)
    elif style == "examplename":
        return "".join(decomposed_str)


def get_diff_dict(diff_path, flatten=True, ignore=None):
    """Read a diff file and convert it to a diff dict."""
    if "comp-diff" not in diff_path and "-comp.yaml" not in diff_path:
        logger.warning(
            "Incorrect diff format. Rerun CLIx's diff/explore with the --compact option"
        )
        return
    diff_dict = import_yaml(diff_path)
    if "-comp.yaml" in diff_path:
        diff_dict = {"buffer": diff_dict}
    return (
        flatten_mixed(list(diff_dict.values()))
        if flatten
        else next(iter(diff_dict.values()))
    )


def plinko_to_ptcommand(plinko_results, allow_dupes=False):
    """Convert plinko-identified tests into pytest arguments."""
    pytest_list = []
    with click.progressbar(
        plinko_results, label="Converting results to pytest command"
    ) as plink_res:
        for feature in plink_res:
            file_name = next(iter(feature[1].keys()))
            if isinstance(feature[1][file_name], dict):  # unittest style
                for test_class in feature[1][file_name]:
                    for test in feature[1][file_name][test_class]:
                        pytest_list.append(f"{file_name}::{test_class}::{test}")
            else:
                for test in feature[1][file_name]:
                    pytest_list.append(f"{file_name}::{test}")
        if not allow_dupes:
            pytest_list = set(pytest_list)
            logger.info(f"Found {len(pytest_list)} unique tests.")
    return f"pytest -v {' '.join(pytest_list)}"


def recurse_down(dir_path, suffix=None, ignore=None):
    """Given a base directory, return a list of all nested files."""
    results = []
    for item in dir_path.iterdir():
        if item.is_dir() and item.name not in BANNED_DIRS:
            results.extend(recurse_down(item, suffix, ignore))
        elif item.is_file():
            if ignore and ignore in item.name:
                continue
            if (not suffix) or (suffix and item.suffix == suffix):
                results.append(item)
    return results


def recurse_up(dir_path, root_path, suffix=None, ignore=None):
    """Given a base directory, return a list of all matching files back to root."""
    if dir_path.is_file():
        dir_path = dir_path.parent
    dir_path = dir_path.resolve()
    results = []
    for item in dir_path.iterdir():
        if item.is_file():
            if ignore and ignore in item.name:
                continue
            if (not suffix) or (suffix and item.suffix == suffix):
                results.append(item)
    if dir_path.parent >= root_path:
        results.extend(recurse_up(dir_path.parent, root_path, suffix, ignore))
    return results


def expand_dict_keys(to_insert, sep=":"):
    """Expand a single-layer dictionary into a multi-layer dictionary
    based on the separator in each key.

    For example, the dictionary:
        {"abc:def:ghi": {"my", "set"}} becomes
        {"abc": {"def": {"ghi": ["my", "set"]}}}
    Note that the set was converted to a list
    """
    if isinstance(to_insert, dict):
        res_dict = {}
        for key, val in to_insert.items():
            k, *rem = key.split(sep)
            if rem:
                res_dict[k] = res_dict.get(k, {})
                res_dict[k].update(expand_dict_keys({":".join(rem): val}, sep))
            else:
                res_dict[k] = res_dict.get(k, [])
                if isinstance(res_dict[k], list):
                    res_dict[k].extend(list(val))
                else:
                    print(f"something funky with {k}: {val}")
        return res_dict
