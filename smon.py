#!/usr/bin/env python

import asyncio
from aiohttp import web

import argparse
import imp
import sys

from libsmon import Scheduler, OK, ERR, all_checks, __version__


#PREFIX = '/usr/share/smon-%s/' % __version__
PREFIX = './'
STATIC_ROOT = PREFIX + 'static'
HOST = '0.0.0.0'
PORT = 8181

app = web.Application()


class get:
  meth = 'GET'
  def __init__(self, uri):
    self.uri = uri
  def __call__(self, f):
    f = asyncio.coroutine(f)
    app.router.add_route(self.meth, self.uri, f)
    return f

@get("/")
def index(req):
  status = OK
  for c in all_checks:
    if c.last_status not in [OK, None]:
      status = ERR
  http_status = 200 if status == OK else 500
  http_status = 200
  return web.Response(text=str(http_status), status=http_status)
#app.router.add_route('GET', '/', index)


@get('/flush')
def flush(req):
  scheduler.flush()
  yield from asyncio.sleep(1)  # give it a chance to finish some checks
  return web.HTTPSeeOther('/')



app.router.add_static('/static', STATIC_ROOT)


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Monitor the machine.')
  parser.add_argument('-d', '--debug', default=False, type=bool, const=True, nargs='?', help='enable debug mode')
  parser.add_argument('-l', '--listen', default="%s:%s"%(HOST,PORT), type=str,
      help='Override listen address. :8080 means to bind on 0.0.0.0:8080')
  parser.add_argument('-c', '--config', default=['/etc/smoncfg.py'], nargs='*')
  args = parser.parse_args()

  if args.debug:
    STATIC_ROOT = 'static/'
    print("running in debug mode", file=sys.stderr)

  for i, cfg in enumerate(args.config):
    imp.load_source("cfg%s"%i, pathname=cfg)

  scheduler = Scheduler()
  scheduler.start()
  for c in all_checks:  # do initial scheduling
    scheduler.schedule(c)

  try:
    HOST, PORT = args.listen.split(':')
  except ValueError:
    raise Exception("listen address should be in the form of <HOST>:<PORT> or :<PORT>")

  PORT = int(PORT)
  if not HOST:
    HOST = "0.0.0.0"

  # AIO HTTP

  loop = asyncio.get_event_loop()
  handler = app.make_handler()
  f = loop.create_server(handler, HOST, PORT)
  srv = loop.run_until_complete(f)
  print('serving on', srv.sockets[0].getsockname())
  try:
      loop.run_forever()
  except KeyboardInterrupt:
      pass
  finally:
      loop.run_until_complete(handler.finish_connections(1.0))
      srv.close()
      loop.run_until_complete(srv.wait_closed())
      loop.run_until_complete(app.finish())
  loop.close()
