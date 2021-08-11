#!/usr/bin/env python3

import setuptools
import pkg_resources

def main() -> None:
    """Meowdy, Ny'all"""

    # https://medium.com/@daveshawley/safely-using-setup-cfg-for-metadata-1babbe54c108
    pkg_resources.require('setuptools>=39.2')

    setuptools.setup()


if __name__ == '__main__':
    main()
