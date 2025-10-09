#!/usr/bin/env python3

from setuptools import setup, find_packages
import os

# Read README file
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="dmoj-user-activity-tracker",
    version="1.0.0",
    author="Phan Cong Dung",
    author_email="phancddev@gmail.com",
    description="A comprehensive Django app for tracking user activities and sessions in DMOJ online judge system",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/phancddev/dmoj-user-activity-tracker",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Framework :: Django",
        "Framework :: Django :: 3.2",
        "Framework :: Django :: 4.0",
        "Framework :: Django :: 4.1",
        "Framework :: Django :: 4.2",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Monitoring",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    include_package_data=True,
    zip_safe=False,
    keywords="django dmoj online-judge user-tracking session-monitoring activity-tracking",
    project_urls={
        "Bug Reports": "https://github.com/phancddev/dmoj-user-activity-tracker/issues",
        "Source": "https://github.com/phancddev/dmoj-user-activity-tracker",
        "Documentation": "https://github.com/phancddev/dmoj-user-activity-tracker#readme",
    },
) 