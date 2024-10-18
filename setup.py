# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

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
    package_data={"lets": ["resources/*.*"]},
    include_package_data=True,
    packages=setuptools.find_packages(exclude=["tests", "tests/*"]),
    install_requires=requires,
    platforms=["any"],
    python_requires=">=3.8",
    entry_points = {
        'console_scripts': ['lets=lets:main'],
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
