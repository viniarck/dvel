#!/usr/bin/python
"""
Containernet custom topology
"""

import copy
import re
import signal
import subprocess
import sys
import os
from mininet.net import Containernet
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel

setLogLevel("info")


def handler(signum, frame):
    info("*** Stopping network")
    net.stop()
    docker_stop_mn_hosts()
    sys.exit(0)


def docker_stop_mn_hosts(rm=False):
    """Stop and clean up extra mininet hosts"""
    try:
        pass
        host_re = r".*?(mn.\w+)"
        out = subprocess.check_output(["docker", "ps"], universal_newlines=True)
        for l in out.split("\n"):
            g = re.match(host_re, l)
            if g:
                subprocess.run(
                    ["docker", "stop", g.group(1)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                if rm:
                    subprocess.run(
                        ["docker", "rm", g.group(1)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
    except (IOError, FileNotFoundError):
        pass


"""
Topology

- hosts: d1, d2 (used for data plane tests, send untagged traffic in this topo)
- edge_sws: s1, s2 (mainly used for pushing and popping VLANs on hosts)
- bb_sws: s3, s4, s5

datapath-id follows this pattern "00:00:00:00:00:00:00:sw", where sw is the switch number

   edge/host                backbone                edge/host
---------------- ------------------------------- ------------------
                |                               |
                |        s3 (2) -- (2) s4       |
d1 -- (1) s1 (2)| -- (1) s3 (3) -- (3) s4 (1) --| (2) s2 (1) -- d2
d3 -- (3)       |        s3 (4) -- (4) s4       |        (3) -- d6
d4 -- (4)       |                               |        (4) -- d7
d5 -- (5)       |                               |        (5) -- d8
                |                               |
---------------- ------------------------------- ------------------

"""
# To gracefully shutdown
signal.signal(signal.SIGINT, handler)
signal.signal(signal.SIGTERM, handler)

# IP addressing
host_d1 = "d1"
host_d2 = "d2"
host_d3 = "d3"
host_d4 = "d4"
host_d5 = "d5"
host_d6 = "d6"
host_d7 = "d7"
host_d8 = "d8"

env = {
    host_d1: "10.0.0.1",
    host_d2: "10.0.0.2",
    host_d3: "10.0.0.3",
    host_d4: "10.0.0.4",
    host_d5: "10.0.0.5",
    host_d6: "10.0.0.6",
    host_d7: "10.0.0.7",
    host_d8: "10.0.0.8",
    "DB_SERVER": "172.17.0.1",
    "DB_NAME": "dvel",
    "ENDPOINT": "echo"
}

controller_ip = "127.0.0.1"
if os.environ.get("ofcontroller_ip"):
    controller_ip = os.environ.get("ofcontroller_ip")

controller_port = 6633
if os.environ.get("ofcontroller_port"):
    controller_port = int(os.environ.get("ofcontroller_port"))

info("*** Cleaning up ***")
docker_stop_mn_hosts(True)


info("*** Instantiating Network elements ***")
c0 = RemoteController("c0", ip=controller_ip, port=controller_port)
net = Containernet()

info("*** Adding controller\n")
net.addController(c0)

info("*** Adding docker containers\n")
d1_env = copy.copy(env)
d1_env["HTTP_SERVER"] = d1_env[host_d2]
d1_env["CONTAINER"] = host_d1
d1 = net.addDocker(
    host_d1,
    ip=env["d1"],
    dimage="registry.gitlab.com/viniarck/containernet-docker:client",
    dcmd="/sbin/my_init",
    environment=d1_env,
)
d2 = net.addDocker(
    host_d2,
    ip=env["d2"],
    dcmd="/sbin/my_init",
    dimage="registry.gitlab.com/viniarck/containernet-docker:server",
    environment=env,
)
d3_env = copy.copy(env)
d3_env["HTTP_SERVER"] = d3_env[host_d6]
d3_env["CONTAINER"] = host_d3
d3 = net.addDocker(
    host_d3,
    ip=env["d3"],
    dcmd="/sbin/my_init",
    dimage="registry.gitlab.com/viniarck/containernet-docker:client",
    environment=d3_env,
)
d4_env = copy.copy(env)
d4_env["HTTP_SERVER"] = d4_env[host_d7]
d4_env["CONTAINER"] = host_d3
d4 = net.addDocker(
    host_d4,
    ip=env["d4"],
    dcmd="/sbin/my_init",
    dimage="registry.gitlab.com/viniarck/containernet-docker:client",
    environment=d4_env,
)
d5_env = copy.copy(env)
d5_env["HTTP_SERVER"] = d5_env[host_d8]
d5_env["CONTAINER"] = host_d3
d5 = net.addDocker(
    host_d5,
    ip=env["d5"],
    dcmd="/sbin/my_init",
    dimage="registry.gitlab.com/viniarck/containernet-docker:client",
    environment=d5_env,
)
d6 = net.addDocker(
    host_d6,
    ip=env["d6"],
    dcmd="/sbin/my_init",
    dimage="registry.gitlab.com/viniarck/containernet-docker:server",
    environment=env,
)
d7 = net.addDocker(
    host_d7,
    ip=env["d7"],
    dcmd="/sbin/my_init",
    dimage="registry.gitlab.com/viniarck/containernet-docker:server",
    environment=env,
)
d8 = net.addDocker(
    host_d8,
    ip=env["d8"],
    dcmd="/sbin/my_init",
    dimage="registry.gitlab.com/viniarck/containernet-docker:server",
    environment=env,
)

info("*** Adding switches\n")
s1 = net.addSwitch("s1")
s2 = net.addSwitch("s2")
s3 = net.addSwitch("s3")
s4 = net.addSwitch("s4")

info("*** Creating links\n")
net.addLink(s1, d1, port1=1)
net.addLink(s1, d3, port1=3)
net.addLink(s1, d4, port1=4)
net.addLink(s1, d5, port1=5)

net.addLink(s2, d2, port1=1)
net.addLink(s2, d6, port1=3)
net.addLink(s2, d7, port1=4)
net.addLink(s2, d8, port1=5)

net.addLink(s1, s3, port1=2, port2=1, cls=TCLink, delay="1ms", bw=1000)
net.addLink(s2, s4, port1=2, port2=1, cls=TCLink, delay="1ms", bw=1000)

net.addLink(s3, s4, port1=2, port2=2, cls=TCLink, delay="25ms", bw=1000)
net.addLink(s3, s4, port1=3, port2=3, cls=TCLink, delay="50ms", bw=1000)
net.addLink(s3, s4, port1=4, port2=4, cls=TCLink, delay="100ms", bw=1000)

info("*** Starting network\n")
net.start()
info("*** Running CLI\n")
CLI(net)
