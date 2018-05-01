#!/usr/bin/env python
# -*- coding: utf-8 -*-


import aiohttp
import asyncio
import async_timeout
import logging
import os
import uvloop
from aioinflux import InfluxDBClient

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)
HTTP_SERVER = os.environ.get('HTTP_SERVER', 'localhost')
HTTP_PORT = os.environ.get('HTTP_PORT', '8000')
ENDPOINT = os.environ.get('ENDPOINT', 'echo')
DB_SERVER = os.environ.get('DB_SERVER', 'localhost')
DB_NAME = os.environ.get('DB_NAME', 'dvel')
CONTAINER = os.environ.get('HOSTNAME', 'cx')

FREQUENCY = 0.001
TIMEOUT = 1

async def make_request(session, url):
    """ Make request. """

    async with async_timeout.timeout(TIMEOUT):
        async with session.get(url) as response:
            return await response.text()


async def main_coroutine():
    """ Main loop corroutine await for requests,
    Measure RTTs and push to InfluxDB.

    """
    client = InfluxDBClient(host=DB_SERVER, db=DB_NAME)
    await client.create_database(host=DB_SERVER, db=DB_NAME)
    cnt_pkt_loss = 0
    cur_rtt = 0.0
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                request_start = loop.time()
                data = await make_request(session, f'http://{HTTP_SERVER}:{HTTP_PORT}/{ENDPOINT}')
                cur_rtt = ((loop.time() - request_start) * 1e3) / 2.0  # two req
        except asyncio.TimeoutError as e:
            cur_rtt = 0.0
            cnt_pkt_loss += 1
        except aiohttp.client_exceptions.ClientConnectorError as e:
            log.error(f"HTTP server {HTTP_SERVER} connection error")
        finally:
            rtt_point = dict(measurement='rtt', tags={'host': CONTAINER}, fields={'value': cur_rtt})
            await client.write(rtt_point)
            pkt_loss_point = dict(measurement='cnt_pkt_loss', tags={'host': CONTAINER}, fields={'value': cnt_pkt_loss})
            await client.write(pkt_loss_point)
            await asyncio.sleep(FREQUENCY)

if __name__ == '__main__':
    try:
        loop = uvloop.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main_coroutine())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
