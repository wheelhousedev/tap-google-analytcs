#!/usr/bin/env python
from setuptools import setup

setup(
    name="tap-google-analytics",
    version="0.1.4",
    description="Wheelhouse DMG fork of Meltano's Google Analytics tap",
    author='Aditya Sastry, Meltano Team & Contributors',
    author_email="aditya@wheelhousedmg.com",
    url="ssh://git@github.com/wheelhousedev/tap-google-analytcs.git",
    classifiers=["Programming Language :: Python :: 3 :: Only"],
    py_modules=["tap_google_analytics"],
    install_requires=[
        "singer-python==5.6.1",
        "google-api-python-client==1.7.9",
        "oauth2client==4.1.3",
        "backoff==1.3.2",
        "requests==2.25.1"
    ],
    entry_points="""
    [console_scripts]
    tap-google-analytics=tap_google_analytics:main
    """,
    packages=["tap_google_analytics"],
    package_data = {
      'tap_google_analytics/defaults': [
        "default_report_definition.json",
      ],
    },
    include_package_data=True,
)
