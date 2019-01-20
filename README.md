## dvel (DTN VPN Express Lane)

It's a dynamic source-based VPN forwarding SDN application, which selects an optimal network path to maximize the throughput of an E-Line VPN/EVC on [Kytos](https://www.kytos.io). dvel leverages OpenvSwitch to extend the OpenFlow domain up to the DTN's (Data Transfer Node - Endpoint) NIC and uses periodic measurement probes over multiple network paths to compute the average latency, packet loss between two DTNs and reacts to network failure events.

## Demo

![demo](https://s2.gifyu.com/images/dvel.gif)

## Network Architecture

![network](docs/dvel.png?raw=true "SDN Network with end-to-end OpenFlow domains")

## EVCs (Ethernet Virtual Circuit)

- The EVC, provisioned by the [MEF E-line application](https://github.com/kytos/mef_eline), will terminate on SDN switches that belong to the provides, and the OvS instance on the host will stitch or extend the circuit to the host's NIC (network interface card).
- MEF E-line will try to compute and install at least three EVCs for each DTN node. (`3*O(n) complexity` on OvS). At scale, if there are hundreds/thousands of DTNs, in the network core these tunnels could be reutilized like MPLS does.
- Periodic network measurement probes will be activated for each EVC. Ideally, these probes would be based on sampled traffic of the application but at lower rates, thousand samples per second via a network socket. These probes will generate asynchronous events.
- Either kytos controller itself or the DTNs will run an optimization algorithm and make http requests to dvel in order to change lanes (paths).

### Network Measurement Probes

 Initially, a pair of client-server HTTP application will be used with asyncio as measurements probes for each EVC circuit for each DTN pair.

## Assumptions

QoS is outside of the scope of dvel. QoS policies should be in place per hop, prioritizing each circuits/VLANs accordingly.

## Future suggested features/roadmap:

- Add dynamic paths discovery/computations in the core, for example `kytos/pathfinder` (which runs OSPF algorithm).
- Compute other variable factors such as packet loss when switching to the best path (currently only rtt is taken into account).
- Implement events to better communicate with other NApps.
- Provision the EVCs with `kytos/mef_eline`, currently it uses `kytos/flow_manager` directly (since when I started prototyping this mef_eline was not fully stable and didn't have VLAN pool settings)
