#!/usr/bin/env python
# -*- coding: utf-8 -*-


import aiohttp
import asyncio
import async_timeout
import logging
import os
import uvloop
from aioinflux import InfluxDBClient
from collections import namedtuple

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

HTTPServerInfo = namedtuple("HTTPServerInfo", "addr port endpoint")
DBServerInfo = namedtuple("DBServerInfo", "addr port name")


class Client(object):

    """Client Abstraction."""

    def __init__(
        self,
        name: str,
        https_info: HTTPServerInfo,
        dbs_info: DBServerInfo,
        frequency: float = 0.001,
        timeout: int = 1,
    ) -> None:
        """Constructor of Client."""
        self.name = name
        self.h_info = https_info
        self.d_info = dbs_info
        self.influx_client = InfluxDBClient(
            host=dbs_info.addr, db=dbs_info.name, port=dbs_info.port
        )
        self.timeout = timeout
        self.frequency = frequency

    async def make_request(self, session, url):
        """ Make request. """

        async with async_timeout.timeout(self.timeout):
            async with session.get(url) as response:
                return await response.text()

    async def run(self):
        """Coroutine run."""
        client = InfluxDBClient(host=self.d_info.addr, db=self.d_info.name)
        try:
            await client.create_database(host=self.d_info.addr, db=self.d_info.name)
        except aiohttp.client_exceptions.ClientConnectorError as e:
            log.error(e)
            return
        cnt_pkt_loss = 0
        cur_rtt = 0.0
        url = f"http://{self.h_info.addr}:{self.h_info.port}/{self.h_info.endpoint}"
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    request_start = loop.time()
                    await self.make_request(session, url)
                    cur_rtt = ((loop.time() - request_start) * 1e3) / 2.0
                    print(cur_rtt)
            except asyncio.TimeoutError as e:
                cur_rtt = 0.0
                cnt_pkt_loss += 1
            except aiohttp.client_exceptions.ClientConnectorError as e:
                log.error(f"HTTP server {self.h_info.addr} connection error")
            finally:
                rtt_point = dict(
                    measurement="rtt",
                    tags={"host": CONTAINER},
                    fields={"value": cur_rtt},
                )
                await client.write(rtt_point)
                pkt_loss_point = dict(
                    measurement="cnt_pkt_loss",
                    tags={"host": CONTAINER},
                    fields={"value": cnt_pkt_loss},
                )
                await client.write(pkt_loss_point)
                await asyncio.sleep(self.frequency)


if __name__ == "__main__":

    HTTP_SERVER = os.environ.get("HTTP_SERVER", "localhost")
    HTTP_PORT = os.environ.get("HTTP_PORT", "8000")
    ENDPOINT = os.environ.get("ENDPOINT", "echo")
    DB_SERVER = os.environ.get("DB_SERVER", "localhost")
    DB_PORT = os.environ.get("DB_PORT", 8086)
    DB_NAME = os.environ.get("DB_NAME", "dvel")
    CONTAINER = os.environ.get("HOSTNAME", "cx")

    try:
        loop = uvloop.new_event_loop()
        asyncio.set_event_loop(loop)
        http_server_info = HTTPServerInfo(HTTP_SERVER, HTTP_PORT, ENDPOINT)
        db_server_info = DBServerInfo(DB_SERVER, DB_PORT, DB_NAME)
        c = Client(CONTAINER, http_server_info, db_server_info)
        loop.run_until_complete(c.run())
    except KeyboardInterrupt:
        loop.close()
    finally:
        loop.close()
