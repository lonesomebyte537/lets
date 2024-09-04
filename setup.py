# Copyright 2021-2023 NXP
# This software is owned or controlled by NXP and may only be used
# strictly in accordance with the applicable license terms.  By expressly
# accepting such terms or by downloading, installing, activating and/or
# otherwise using the software, you are agreeing that you have read, and
# that you agree to comply with and are bound by, such license terms.  If
# you do not agree to be bound by the applicable license terms, then you
# may not retain, install, activate or otherwise use the software.

import os

import setuptools

with open("README.md", "r") as file_handle:
    long_description = file_handle.read()

requires = open("requirements.txt").read().strip().split("\n")

setuptools.setup(
    name="lets",
    version="0.1",
    description="Test framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/lonesomebyte537/lets",
    license="Apache License 2.0",
    package_dir={"": "src"},
    package_data={"lets": ["lets.py", "plugins/__init__.py"]},
    include_package_data=True,
    install_requires=requires,
    platforms=["any"],
    python_requires=">=3.8",
    entry_points = {
        'console_scripts': ['lets=lets.__main__:main'],
    },
    classifiers=[
        "Development Status :: 4 - Beta",  # 3 - Alpha, 4 - Beta, 5 - Production/Stable
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Release Tools",
        "License :: Apache Software License",
        "Programming Language :: Python :: 3.8",
    ],
)
