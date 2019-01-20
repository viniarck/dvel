"""Main module of dvel."""

import aiohttp
import requests
import time
import uvloop
import async_timeout
import asyncio
from aioinflux import InfluxDBClient
from kytos.core import KytosNApp, log, rest
from kytos.core.helpers import listen_to
from kytos.core.events import KytosEvent
from flask import jsonify
from napps.viniarck.dvel import settings
from typing import List, Dict, Any
from requests.models import Response

"""
Topology

- hosts: d1 (application), d2 (application)
- containers host d1 (probes): d3, d4, d5
- containers host d2 (probes): d6, d7, d8

- edge_sws: s1, s2
- bb_sws: s3, s4


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


class Main(KytosNApp):
    """Main class of viniarck/dvel NApp.

    """

    def setup(self) -> None:
        """Create a graph to handle the nodes and edges."""

        try:
            self.dpids: List[str] = settings.dpids
        except AttributeError:
            log.error("dpids list is missing on settings.py")
            exit(1)

        self.http_server = settings.http_server
        self.http_port = settings.http_port
        self.endpoint = settings.endpoint
        self.db_server = settings.db_server
        self.db_name = settings.db_name
        self.frequency = settings.frequency
        self.timeout = settings.timeout
        self.c_params = settings.c_params
        self.containers = settings.containers

        self.bb_n_evcs: int = 3  # only 3 different paths in the core for now
        self.bb_nni_ofn1: int = 2
        self.bb_nni_ofn2: int = self.bb_nni_ofn1 + self.bb_n_evcs
        self.bb_nni_vlan1: int = 100  # starts at vlan id 100
        self.bb_nn1_vlan2: int = self.bb_nni_vlan1 + self.bb_n_evcs
        self.bb_edge_uni_ofnum: int = 1
        self.bb_host_vlan: int = self.bb_nn1_vlan2 + 1

        self.bb_sws: Dict[str, Any] = {
            "dpids": self.dpids[-2:],  # last two elements.
            "nni_ofnums": range(self.bb_nni_ofn1, self.bb_nni_ofn2),
            "nni_vlans": range(self.bb_nni_vlan1, self.bb_nn1_vlan2),
            "uni_ofnum": self.bb_edge_uni_ofnum,
        }

        self.edge_n_evcs: int = self.bb_n_evcs  # one container for each evc
        self.edge_uni_ofn1: int = 3
        self.edge_uni_ofn2: int = self.edge_uni_ofn1 + self.edge_n_evcs
        self.edge_host_ofnum: int = 1
        self.bb_edge_nni_ofnum: int = 2  # single uplink, so no range for now.

        self.edge_sws: Dict[str, Any] = {
            "dpids": self.dpids[0:2],
            "uni_ofnums": range(self.edge_uni_ofn1, self.edge_uni_ofn2),
            "nni_vlans": self.bb_sws["nni_vlans"],
            "nni_ofnum": self.bb_edge_nni_ofnum,
        }

        self.loop = None
        self.run_flag = True

    async def http_post(self, session, url):
        """ Send http post. """
        async with async_timeout.timeout(self.timeout):
            async with session.post(url) as response:
                return await response.text()

    async def main_coroutine(self):
        """Main coroutine."""
        client = InfluxDBClient(host=self.db_server, db=self.db_name)
        try:
            await client.create_database(host=self.db_server, db=self.db_name)
        except aiohttp.client_exceptions.ClientConnectorError as e:
            log.error(e)
            return
        log_flag = True
        while self.run_flag:
            try:
                cur_key = self.c_params["l_rtt_key"]
                l_rtt = self.containers[cur_key]["rtt"]
                for key, attrs in self.containers.items():
                    query = f'select mean("value") from rtt where ("host" = \'{key}\') and time > now() - 3s fill(0) limit 1'
                    query_res = await client.query(query)
                    series = query_res["results"][0].get("series")
                    if series:
                        values = series[0].get("values")
                        point = float(values[0][-1])
                        self.containers[key]["rtt"] = point
                        # if current path is down, steer away
                        if point == 0.0:
                            if log_flag and key == cur_key:
                                log.info("Current path is down! Steering away.")
                                log_flag = False
                            self.containers[key]["rtt"] = self.c_params["max_rtt"]
                await asyncio.sleep(self.frequency)
                # optimize
                log.debug(f"current_lowest {self.containers[cur_key]['rtt']}")

                # find lowest first
                for key, attrs in self.containers.items():
                    # if the latency is lower, update lowest rtt key
                    if attrs["rtt"] * 1.20 < l_rtt and attrs["rtt"] > 0:
                        cur_key = key
                        l_rtt = attrs["rtt"]
                if self.c_params["l_rtt_key"] != cur_key:
                    log_flag = True
                    evc_path = self.containers[cur_key]["evc_path"]
                    log.info(f"changing to lane #{evc_path}")
                    self.c_params["l_rtt_key"] = cur_key

                    async with aiohttp.ClientSession() as session:
                        my_str = f"http://{self.http_server}:{self.http_port}/{self.endpoint}/{evc_path}"
                        print(my_str)
                        data = await self.http_post(session, my_str)
                        log.info(data)

            except aiohttp.client_exceptions.ClientConnectorError as e:
                log.error(f"HTTP server {self.http_server} connection refused")
                return

    def execute(self) -> None:
        """Execute."""
        log.info("Starting uvloop")
        self.loop = uvloop.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._wait_all_dpids(self.dpids)
        self.loop.run_until_complete(self.main_coroutine())

    def shutdown(self) -> None:
        """Shutdown the napp."""
        if self.loop:
            self.run_flag = False
            time.sleep(1)
            self.loop.close()

    def _wait_all_dpids(self, dpids: List[str]) -> None:
        """Wait until all dpids have connected.

        :dpids: List of switch dpids

        """

        log.info("Waiting for all dpids to connect")
        connected = False
        while not connected:
            if self.controller.switches.keys():
                for dpid in dpids:
                    if dpid not in self.controller.switches.keys():
                        break
                    if dpid in self.controller.switches.keys():
                        if not self.controller.switches[dpid].is_connected():
                            break
                connected = True
            time.sleep(1)
        log.info("All dpids have connected")
        time.sleep(3)  # after handshake
        for dpid in dpids:
            self.provision_evcs_dpid(dpid)

    def _provision_bb_evcs(self, dpid: str) -> Response:
        """Provision Backbone Ethernet Virtual Circuits for this dpid.

        :dpid: Switch dpid

        """
        fmods = []
        for nni, vlan in zip(self.bb_sws["nni_ofnums"], self.bb_sws["nni_vlans"]):
            # tagged
            fmod = self.prepare_flow_mod(
                in_interface=self.bb_sws["uni_ofnum"],
                out_interface=nni,
                in_vlan=vlan,
                out_vlan=vlan,
            )
            fmods.append(fmod)
            # tagged
            fmod_opposite = self.prepare_flow_mod(
                in_interface=nni,
                out_interface=self.bb_sws["uni_ofnum"],
                in_vlan=vlan,
                out_vlan=vlan,
            )
            fmods.append(fmod_opposite)
        response = self.send_flow_mods(dpid, fmods)
        if response.status_code != 200:
            log.error("Response {}".format(response.text))
        return response

    def _provision_edge_evcs(self, dpid: str) -> Response:
        """Provision Backbone Ethernet Virtual Circuits on this dpid.

        :dpid: Switch dpid

        """
        fmods = []
        unis = []
        # containers probes
        unis.extend(self.edge_sws["uni_ofnums"])
        # host ofnum
        unis.append(self.edge_host_ofnum)

        nnis_vlans = []
        nnis_vlans.extend(self.edge_sws["nni_vlans"])
        nnis_vlans.append(self.bb_host_vlan)

        for uni, vlan in zip(unis, nnis_vlans):
            # untagged
            fmod = self.prepare_flow_mod(
                in_interface=uni,
                out_interface=self.edge_sws["nni_ofnum"],
                push=True,
                out_vlan=vlan,
            )
            fmods.append(fmod)
            # pop
            fmod_opposite = self.prepare_flow_mod(
                in_interface=self.edge_sws["nni_ofnum"],
                out_interface=uni,
                in_vlan=vlan,
                pop=True,
            )
            fmods.append(fmod_opposite)
        response = self.send_flow_mods(dpid, fmods)
        if response.status_code != 200:
            log.error("Response {}".format(response.text))
        return response

    def _provision_host_bb_evc(self, dpid: str, path: int = 1) -> Response:
        """Provision Backbone Ethernet Virtual Circuit of the Host on this dpid.

        :dpid: Switch dpid
        :path: int 1, 2, or 3

        """
        fmods = []
        vlan = self.bb_host_vlan
        # tagged
        fmod = self.prepare_flow_mod(
            in_interface=self.bb_edge_uni_ofnum,
            out_interface=int(path) + self.bb_edge_uni_ofnum,
            in_vlan=vlan,
            out_vlan=vlan,
        )
        fmods.append(fmod)
        # tagged
        fmod_opposite = self.prepare_flow_mod(
            in_interface=int(path) + self.bb_edge_uni_ofnum,
            out_interface=self.bb_edge_uni_ofnum,
            in_vlan=vlan,
            out_vlan=vlan,
        )
        fmods.append(fmod_opposite)
        response = self.send_flow_mods(dpid, fmods)
        if response.status_code != 200:
            log.error("Response {}".format(response.text))
        return response

    def provision_evcs_dpid(self, dpid: str) -> None:
        """Provision Ethernet Virtual Circuits (EVCs) for each pre-defined dpid

        :dpid: Switch dpid

        """
        response = None
        if dpid in self.bb_sws["dpids"]:
            response = self._provision_bb_evcs(dpid)
            response = self._provision_host_bb_evc(dpid)
        elif dpid in self.edge_sws["dpids"]:
            response = self._provision_edge_evcs(dpid)
        if response:
            log.info("Switch {} Response {}".format(dpid, response.status_code))
        else:
            log.error("dpid {} not found".format(dpid))

    @staticmethod
    def prepare_flow_mod(
        in_interface, out_interface, in_vlan=None, out_vlan=None, push=False, pop=False
    ) -> Dict[str, Any]:
        """Prepare flow mod for sigle-tag EVCs."""
        default_action = {"action_type": "output", "port": out_interface}

        flow_mod = {"match": {"in_port": in_interface}, "actions": [default_action]}
        if in_vlan:
            flow_mod["match"]["dl_vlan"] = in_vlan
        if out_vlan:
            new_action = {"action_type": "set_vlan", "vlan_id": out_vlan}
            flow_mod["actions"].insert(0, new_action)
        if push:
            new_action = {"action_type": "push_vlan", "tag_type": 1}
            flow_mod["actions"].insert(0, new_action)
        if pop:
            new_action = {"action_type": "pop_vlan"}
            flow_mod["actions"].insert(0, new_action)
        return flow_mod

    @staticmethod
    def send_flow_mods(switch, flow_mods) -> Response:
        """Send a flow_mod list to a specific switch."""
        endpoint = "%s/flows/%s" % (settings.FMNGR_URL, switch)

        data = {"flows": flow_mods}
        return requests.post(endpoint, json=data)

    def _activate_host_evc(self, dpid, cvlan) -> Response:
        """Activate the host EVPL cvlan

        :dpid: Switch dpid
        :cvlan: customer vlan (int)
        """
        fmods = []
        # untagged
        fmod = self.prepare_flow_mod(
            in_interface=self.edge_host_ofnum,
            out_interface=self.bb_edge_nni_ofnum,
            push=True,
            out_vlan=cvlan,
        )
        fmods.append(fmod)
        # pop
        fmod_opposite = self.prepare_flow_mod(
            in_interface=self.bb_edge_nni_ofnum,
            out_interface=self.edge_host_ofnum,
            in_vlan=cvlan,
            pop=True,
        )
        fmods.append(fmod_opposite)
        response = self.send_flow_mods(dpid, fmods)
        if response.status_code != 200:
            log.error("Response {}".format(response.text))
        return response

    @rest("/changelane/<path>", methods=["POST"])
    def change_lane(self, path) -> tuple:
        """Change the application EVC to another path.

        :path: path number either 1, 2, or 3
        """

        if int(path) not in range(1, 4):
            return jsonify({"response": "path number should be 1, 2 or 3"}), 404

        response = None
        for dpid in self.bb_sws["dpids"]:
            response = self._provision_host_bb_evc(dpid, int(path))
            if response.status_code != 200:
                log.error("Response {}".format(response.text))
                return jsonify({"response": response.text}), 404
        log.info("changed to lane #{}".format(path))

        return jsonify({"response": "changed to lane #{}".format(path)}), 200

    @listen_to("kytos/of_core.handshake_complete")
    def update_topology(self, event: KytosEvent) -> None:
        """Listens to new connection and reconnection events.

        """
        if "switch" not in event.content:
            return

        switch = event.content["switch"]
        time.sleep(3)  # after handshake
        self.provision_evcs_dpid(switch.dpid)
