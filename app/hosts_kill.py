#!/usr/bin/env python
# -*- coding: utf-8 -*-

import subprocess
import re


def docker_stop_mn_hosts():
    """Stop and clean up extra mininet hosts"""
    try:
        pass
        host_re = r".*?(mn.\w+)"
        out = subprocess.check_output(
            ["docker", "ps"],
            universal_newlines=True
        )
        for l in out.split("\n"):
            g = re.match(host_re, l)
            if g:
                subprocess.run(
                    ["docker", "stop", g.group(1)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
    except (IOError, FileNotFoundError):
        pass


def main():
    """Main function."""
    docker_stop_mn_hosts()


if __name__ == "__main__":
    main()
