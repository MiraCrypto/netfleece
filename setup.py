#!/usr/bin/env python3
"""netfleece installation script."""

import setuptools


def main():
    """netfleece installation wrapper"""
    kwargs = {
        'name': 'netfleece',
        'version': '0.1.2',
        'author': 'nago',
        'author_email': 'nago@malie.io',
        'description': (
            "Python 3.7+ Microsoft .NET Remoting Binary Format (MS-NRBF) to JSON parser"
        ),
        'url': "https://gitlab.com/malie-library/netfleece",
        'packages': setuptools.find_packages(),
        'scripts': ['bin/netfleece'],
        'classifiers': [
            "Development Status :: 2 - Pre-Alpha",
            "License :: OSI Approved :: MIT License",
            "Natural Language :: English",
            "Operating System :: OS Independent",  # Uh, I hope, haha
            "Programming Language :: Python :: 3",
            "Topic :: Software Development :: Disassemblers",
        ]
    }

    with open("README.md", "r") as infile:
        kwargs['long_description'] = infile.read()
    kwargs['long_description_content_type'] = 'text/markdown'

    setuptools.setup(**kwargs)


if __name__ == '__main__':
    main()
