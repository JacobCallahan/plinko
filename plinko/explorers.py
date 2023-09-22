"""A collection of methods to assist in handling product explorers."""


def flatten_clix_diff(clix_diff):
    compiled = []
    if isinstance(clix_diff, dict):
        for key in clix_diff:
            for item in clix_diff[key]:
                res = flatten_clix_diff(item)
                if isinstance(res, list):
                    for sub_item in res:
                        compiled.append(f"{key} {sub_item}")
                else:
                    compiled.append(f"{key} {res}")
    elif isinstance(clix_diff, list):
        compiled = [flatten_clix_diff(item) for item in clix_diff]
    else:
        compiled = clix_diff
    print(f"returning {compiled}")
    return compiled


def plink_clix(diff_path, pt_export_path):
    if "comp-diff" not in diff_path:
        print("Incorrect diff format. Rerun CLIx's diff with the --compact option")
        return
    diff_dict = import_yaml(diff_path)
    pt_dict = pyt_collect_to_dict(pt_export_path)
    if not diff_dict or not pt_dict:
        print("something went wrong...")
        return
    diff_dict = flatten_clix_diff(list(diff_dict.values()))[0]
    print(diff_dict)
    plink_results = {"found": [], "missing": []}
    for test in diff_dict:
        print(f"test - {test}")
        split_test = test.split()
        results = find_test_match(
            split_test[1], " ".join(split_test[2:]), pt_dict, "cli"
        )
        print(results)
        if results:
            plink_results["found"].append([test, results])
        else:
            plink_results["missing"].append(test)
    return plink_results


def flatten_apix_diff(apix_diff):
    compiled = []
    if isinstance(apix_diff, dict):
        for key in apix_diff:
            for item in apix_diff[key]:
                res = flatten_apix_diff(item)
                if isinstance(res, list):
                    for sub_item in res:
                        compiled.append(f"{key} {sub_item}")
                else:
                    compiled.append(f"{key} {res}")
    elif isinstance(apix_diff, list):
        compiled = [flatten_apix_diff(item) for item in apix_diff]
    else:
        compiled = apix_diff
    print(f"returning {compiled}")
    return compiled


def plink_apix(diff_path, pt_export_path):
    if "comp-diff" not in diff_path:
        print("Incorrect diff format. Rerun apix's diff with the --compact option")
        return
    diff_dict = import_yaml(diff_path)
    pt_dict = pyt_collect_to_dict(pt_export_path)
    if not diff_dict or not pt_dict:
        print("something went wrong...")
        return
    diff_dict = flatten_apix_diff(list(diff_dict.values()))[0]
    print(diff_dict)
    plink_results = {"found": [], "missing": []}
    for test in diff_dict:
        print(f"test - {test}")
        split_test = test.split()
        results = find_test_match(
            split_test[0], " ".join(split_test[1:]), pt_dict, "api"
        )
        print(results)
        if results:
            plink_results["found"].append([test, results])
        else:
            plink_results["missing"].append(test)
    return plink_results


# def flatten_clix_diff(clix_diff):
#     compiled = []
#     logger.debug(f"received {clix_diff}")
#     if isinstance(clix_diff, dict):
#         for key in clix_diff.keys():
#             if isinstance(clix_diff[key], dict):
#                 # compiled = [
#                 #     f"{key} {sub}" for sub in flatten_clix_diff(list(clix_diff[key].values())[0])
#                 # ]
#                 for sub, values in clix_diff[key].items():
#                     for value in flatten_clix_diff(values):
#                         compiled.append(f"{key} {sub} {value}")
#                         logger.debug(f"latest dict compile {compiled[-1]}")
#         else:
#             for item in clix_diff[key]:
#                 res = flatten_clix_diff(item)
#                 if isinstance(res, list):
#                     for sub_item in res:
#                         compiled.append(f"{key} {sub_item}")
#                 else:
#                     compiled.append(f"{key} {res}")
#     elif isinstance(clix_diff, list):
#         compiled = [flatten_clix_diff(item) for item in clix_diff]
#         for item in clix_diff:
#             res = flatten_clix_diff(item)
#             while res != flatten_clix_diff(res):
#                 res = flatten_clix_diff(res)
#     else:
#         compiled = clix_diff
#     if (
#         isinstance(compiled, list)
#         and len(compiled) == 1
#         and not isinstance(compiled[0], str)
#     ):
#         compiled = compiled[0]  # find a better way to handle this!
#     logger.debug(f"returning {compiled}")
#     return compiled


# def flatten_clix_diff2(clix_diff):
#     compiled = []
#     logger.debug(f"received {clix_diff}")
#     if isinstance(clix_diff, dict):
#         for key in clix_diff.keys():
#             for item in clix_diff[key]:
#                 if isinstance(clix_diff[key], dict):
#                     res = [
#                         f"{item} {sub}"
#                         for sub in flatten_clix_diff(clix_diff[key][item])
#                     ]
#                     logger.debug(f"dict-handler {res}")
#                 else:
#                     res = flatten_clix_diff(item)
#                 if isinstance(res, list):
#                     for sub_item in res:
#                         compiled.append(f"{key} {sub_item}")
#                 else:
#                     compiled.append(f"{key} {res}")
#     elif isinstance(clix_diff, list):
#         compiled = [flatten_clix_diff(item) for item in clix_diff]
#     else:
#         compiled = clix_diff
#     if (
#         isinstance(compiled, list)
#         and len(compiled) == 1
#         and not isinstance(compiled[0], str)
#     ):
#         compiled = compiled[0]  # find a better way to handle this!
#     logger.debug(f"returning {compiled}")
#     return compiled


# def flatten_apix_diff(apix_diff):
#     compiled = []
#     if isinstance(apix_diff, dict):
#         for key in apix_diff.keys():
#             for item in apix_diff[key]:
#                 res = flatten_apix_diff(item)
#                 if isinstance(res, list):
#                     for sub_item in res:
#                         compiled.append(f"{key} {sub_item}")
#                 else:
#                     compiled.append(f"{key} {res}")
#     elif isinstance(apix_diff, list):
#         compiled = [flatten_apix_diff(item) for item in apix_diff]
#     else:
#         compiled = apix_diff
#     logger.debug(f"returning {compiled}")
#     return compiled
