#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
from sanic import Sanic
from sanic.response import json

app = Sanic()


@app.middleware('request')
async def add_start_time(request):
    request['start_time'] = time.time()


@app.middleware('response')
async def add_spent_time(request, response):
    spend_time = (time.time() - request['start_time']) * 1000
    print("{} {} {} {} {}ms".format(response.status, request.method,
                                    request.path, request.query_string, spend_time))

@app.route('/echo')
async def test(request):
    return json({'response': 'reply'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
