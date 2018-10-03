#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

with open("README.md") as readme_file:
    readme = readme_file.read()

with open("HISTORY.rst") as history_file:
    history = history_file.read()

requirements = ["click", "logzero", "pyyaml"]

setup(
    name="plinko",
    version="0.0.1",
    description="Determine what tests are most likely applicable, based on a diff between product versions.",
    long_description=readme + "\n\n" + history,
    author="Jacob J Callahan",
    author_email="jacob.callahan05@@gmail.com",
    url="https://github.com/JacobCallahan/plinko",
    packages=["plinko"],
    entry_points={"console_scripts": ["plinko=plinko.plinko:plinko"]},
    include_package_data=True,
    install_requires=requirements,
    license="GNU General Public License v3",
    zip_safe=False,
    keywords="plinko",
    classifiers=[
        "Development Status :: 1 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
    ],
)
