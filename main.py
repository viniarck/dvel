"""Main module of dvel."""

import requests
import time
from kytos.core import KytosNApp, log, rest
from kytos.core.helpers import listen_to
from flask import jsonify
from napps.viniciusarcanjo.dvel import settings
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
    """Main class of viniciusarcanjo/dvel NApp.

    """

    def setup(self):
        """Create a graph to handle the nodes and edges."""

        self.dpids = [
            '00:00:00:00:00:00:00:01', '00:00:00:00:00:00:00:02',
            '00:00:00:00:00:00:00:03', '00:00:00:00:00:00:00:04'
        ]
        self.bb_n_evcs = 3  # only 3 different paths in the core for now
        self.bb_nni_ofn1 = 2
        self.bb_nni_ofn2 = self.bb_nni_ofn1 + self.bb_n_evcs
        self.bb_nni_vlan1 = 100  # starts at vlan id 100
        self.bb_nn1_vlan2 = self.bb_nni_vlan1 + self.bb_n_evcs
        self.bb_edge_uni_ofnum = 1
        self.bb_host_vlan = self.bb_nn1_vlan2 + 1

        self.bb_sws = {
            'dpids': self.dpids[-2:],  # last two elements.
            'nni_ofnums': range(self.bb_nni_ofn1, self.bb_nni_ofn2),
            'nni_vlans': range(self.bb_nni_vlan1, self.bb_nn1_vlan2),
            'uni_ofnum': self.bb_edge_uni_ofnum
        }

        self.edge_n_evcs = self.bb_n_evcs  # one container for each evc
        self.edge_uni_ofn1 = 3
        self.edge_uni_ofn2 = self.edge_uni_ofn1 + self.edge_n_evcs
        self.edge_host_ofnum = 1
        self.bb_edge_nni_ofnum = 2  # single uplink, so no range for now.

        self.edge_sws = {
            'dpids': self.dpids[0:2],
            'uni_ofnums': range(self.edge_uni_ofn1, self.edge_uni_ofn2),
            'nni_vlans': self.bb_sws['nni_vlans'],
            'nni_ofnum': self.bb_edge_nni_ofnum
        }

    def execute(self):
        """Execute."""
        self._wait_all_dpids(self.dpids)

    def shutdown(self):
        """Shutdown the napp."""
        pass

    def _wait_all_dpids(self, dpids):
        """Wait until all dpids have connected

        :dpids: List of switch dpids

        """

        log.info('Waiting for all dpids to connect')
        connected = False
        while not connected:
            if self.controller.switches.keys():
                for dpid in dpids:
                    # if any dpid is not in the dict yet then break
                    if dpid not in self.controller.switches.keys():
                        break
                    # if the dpid is in the dict but not connected, then break
                    if dpid in self.controller.switches.keys():
                        if not self.controller.switches[dpid].is_connected():
                            break
                connected = True
        log.info('All dpids have connected')
        time.sleep(3)  # after handshake
        for dpid in dpids:
            self.provision_evcs_dpid(dpid)

    def _provision_bb_evcs(self, dpid):
        """Provision Backbone Ethernet Virtual Circuits for this dpid.

        :dpid: Switch dpid

        """
        fmods = []
        for nni, vlan in zip(self.bb_sws['nni_ofnums'],
                             self.bb_sws['nni_vlans']):
            # tagged
            fmod = self.prepare_flow_mod(
                in_interface=self.bb_sws['uni_ofnum'],
                out_interface=nni,
                in_vlan=vlan,
                out_vlan=vlan)
            fmods.append(fmod)
            # tagged
            fmod_opposite = self.prepare_flow_mod(
                in_interface=nni,
                out_interface=self.bb_sws['uni_ofnum'],
                in_vlan=vlan,
                out_vlan=vlan)
            fmods.append(fmod_opposite)
        response = self.send_flow_mods(dpid, fmods)
        if response.status_code != 200:
            log.error('Response {}'.format(response.text))
        return response

    def _provision_edge_evcs(self, dpid):
        """Provision Backbone Ethernet Virtual Circuits on this dpid.

        :dpid: Switch dpid

        """
        fmods = []
        unis = []
        # containers probes
        unis.extend(self.edge_sws['uni_ofnums'])
        # host ofnum
        unis.append(self.edge_host_ofnum)

        nnis_vlans = []
        nnis_vlans.extend(self.edge_sws['nni_vlans'])
        nnis_vlans.append(self.bb_host_vlan)

        for uni, vlan in zip(unis, nnis_vlans):
            # untagged
            fmod = self.prepare_flow_mod(
                in_interface=uni,
                out_interface=self.edge_sws['nni_ofnum'],
                push=True,
                out_vlan=vlan)
            fmods.append(fmod)
            # pop
            fmod_opposite = self.prepare_flow_mod(
                in_interface=self.edge_sws['nni_ofnum'],
                out_interface=uni,
                in_vlan=vlan,
                pop=True)
            fmods.append(fmod_opposite)
        response = self.send_flow_mods(dpid, fmods)
        if response.status_code != 200:
            log.error('Response {}'.format(response.text))
        return response

    def _provision_host_bb_evc(self, dpid, path=1):
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
            out_vlan=vlan)
        fmods.append(fmod)
        # tagged
        fmod_opposite = self.prepare_flow_mod(
            in_interface=int(path) + self.bb_edge_uni_ofnum,
            out_interface=self.bb_edge_uni_ofnum,
            in_vlan=vlan,
            out_vlan=vlan)
        fmods.append(fmod_opposite)
        response = self.send_flow_mods(dpid, fmods)
        if response.status_code != 200:
            log.error('Response {}'.format(response.text))
        return response

    def provision_evcs_dpid(self, dpid):
        """Provision Ethernet Virtual Circuits (EVCs) for each pre-defined dpid

        :dpid: Switch dpid

        """
        response = None
        if dpid in self.bb_sws['dpids']:
            response = self._provision_bb_evcs(dpid)
            response = self._provision_host_bb_evc(dpid)
        elif dpid in self.edge_sws['dpids']:
            response = self._provision_edge_evcs(dpid)
        if response:
            log.info('Switch {} Response {}'.format(dpid,
                                                    response.status_code))
        else:
            log.error('dpid {} not found'.format(dpid))

    @staticmethod
    def prepare_flow_mod(in_interface,
                         out_interface,
                         in_vlan=None,
                         out_vlan=None,
                         push=False,
                         pop=False):
        """Prepare flow mod for sigle-tag EVCs."""
        default_action = {"action_type": "output", "port": out_interface}

        flow_mod = {
            "match": {
                "in_port": in_interface
            },
            "actions": [default_action]
        }
        if in_vlan:
            flow_mod['match']['dl_vlan'] = in_vlan
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
    def send_flow_mods(switch, flow_mods):
        """Send a flow_mod list to a specific switch."""
        endpoint = "%s/flows/%s" % (settings.FMNGR_URL, switch)

        data = {"flows": flow_mods}
        return requests.post(endpoint, json=data)

    def _activate_host_evc(self, dpid, cvlan):
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
            out_vlan=cvlan)
        fmods.append(fmod)
        # pop
        fmod_opposite = self.prepare_flow_mod(
            in_interface=self.bb_edge_nni_ofnum,
            out_interface=self.edge_host_ofnum,
            in_vlan=cvlan,
            pop=True)
        fmods.append(fmod_opposite)
        response = self.send_flow_mods(dpid, fmods)
        if response.status_code != 200:
            log.error('Response {}'.format(response.text))
        return response

    @rest('/changelane/<path>', methods=['POST'])
    def change_lane(self, path):
        """Change the application EVC to another path.

        :path: path number either 1, 2, or 3
        """

        if int(path) not in range(1, 4):
            return jsonify({
                'response': 'path number should be 1, 2 or 3'
            }), 404

        response = None
        for dpid in self.bb_sws['dpids']:
            response = self._provision_host_bb_evc(dpid, int(path))
            if response.status_code != 200:
                log.error('Response {}'.format(response.text))
                return jsonify({'response': response.text}), 404

        return jsonify({'response': 'changed to lane #{}'.format(path)}), 200

    @listen_to('kytos/of_core.handshake_complete')
    def update_topology(self, event):
        """Listens to new connection and reconnection events.

        """
        if 'switch' not in event.content:
            return

        switch = event.content['switch']
        time.sleep(3)  # after handshake
        self.provision_evcs_dpid(switch.dpid)
