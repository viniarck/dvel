#!/usr/bin/env python
# -*- coding: utf-8 -*-

import aiohttp
import asyncio
import async_timeout
import logging
import os
import uvloop
from aioinflux import InfluxDBClient

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
HTTP_SERVER = os.environ.get('HTTP_SERVER', 'localhost')
HTTP_PORT = os.environ.get('HTTP_PORT', '8181')
ENDPOINT = os.environ.get('ENDPOINT', 'api/viniciusarcanjo/dvel/changelane')
DB_SERVER = os.environ.get('DB_SERVER', 'localhost')
DB_NAME = os.environ.get('DB_NAME', 'dvel')

FREQUENCY = 0.5
TIMEOUT = 3
params = {'l_rtt_key': 'd3', 'max_rtt': 1.0e4}
containers = {'d3': {'rtt': 0.0, 'pkt_loss': 0, 'evc_path': 1}, 'd4': {'rtt': 0, 'pkt_loss': 0.0, 'evc_path': 2}, 'd5': {'rtt': 0.0, 'pkt_loss': 0, 'evc_path': 3}}


async def post(session, url):
    """ Send post. """

    async with async_timeout.timeout(TIMEOUT):
        async with session.post(url) as response:
            return await response.text()


async def main_coroutine():
    """ Main loop corroutine await for requests,
    Measure RTTs and push to InfluxDB.

    """
    client = InfluxDBClient(host=DB_SERVER, db=DB_NAME)
    while True:
        try:
            global containers
            global params
            cur_key = params['l_rtt_key']
            l_rtt = containers[cur_key]['rtt']
            for key, attrs in containers.items():
                query = f"select mean(\"value\") from rtt where (\"host\" = '{key}') and time > now() - 3s fill(0) limit 1"
                query_res = await client.query(query)
                series = query_res['results'][0].get('series')
                if series:
                    values = series[0].get('values')
                    point = float(values[0][-1])
                    containers[key]['rtt'] = point
                    # if current path is down, steer away
                    if point == 0.0:
                        containers[key]['rtt'] = params['max_rtt']
            # print(containers)
            await asyncio.sleep(FREQUENCY)
            # optimize
            log.debug(f"current_lowest {containers[cur_key]['rtt']}")
            for key, attrs in containers.items():
                # if the latency is lower, update lowest rtt key
                if attrs['rtt'] < l_rtt:
                    cur_key = key

            log.debug(f"{cur_key} best")
            # change path
            if params['l_rtt_key'] != cur_key:
                evc_path = containers[cur_key]['evc_path']
                log.info(f"changing to lane #{evc_path}")
                params['l_rtt_key'] = cur_key

                async with aiohttp.ClientSession() as session:
                    my_str = f'http://{HTTP_SERVER}:{HTTP_PORT}/{ENDPOINT}/{evc_path}'
                    print(my_str)
                    data = await post(session, my_str)
                    log.info(data)

        except aiohttp.client_exceptions.ClientConnectorError as e:
            log.error(f"HTTP server {HTTP_SERVER} connection refused")
            return

if __name__ == '__main__':
    try:
        loop = uvloop.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main_coroutine())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
