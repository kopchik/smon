#!/usr/bin/env python

from bottle import SimpleTemplate, TEMPLATE_PATH, static_file, route, request, response, view, run, redirect
from libsmon import Scheduler, __version__, OK, ERR, checks
import argparse
import time
import imp
import sys

PREFIX = '/usr/share/smon-%s/' % __version__
TEMPLATE_PATH.insert(0, PREFIX + 'views')
STATIC_ROOT = PREFIX + 'static'
HOST = ''
PORT = 8181

class Time:
    def epoch(self):
      return time.time()
    def __str__(self):
        return time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
SimpleTemplate.defaults['time'] = Time()
SimpleTemplate.defaults['OK'] = OK
SimpleTemplate.defaults['ERR'] = ERR
SimpleTemplate.defaults['DEBUG'] = False

@route('/')
@view('all')
def all():
  status = OK
  for c in checks:
    if c.last_status[0] not in [OK, None]:
      status = ERR
  response.status = 200 if status == OK else 500
  return dict(checks=checks, status=status)


@route('/flush')
def flush():
  scheduler.flush()
  redirect('/')

@route('/static/<path:path>')
def callback(path):
    return static_file(path, root=STATIC_ROOT)


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Monitor the machine.')
  parser.add_argument('-d', '--debug', default=False, type=bool, const=True, nargs='?', help='enable debug mode')
  parser.add_argument('-l', '--listen', default="%s:%s"%(HOST,PORT), type=str,
      help='Override listen address. :8080 means to bind on 0.0.0.0:8080')
  parser.add_argument('-c', '--config', default=['/etc/smoncfg.py'], nargs='*')
  args = parser.parse_args()

  if args.debug:
    TEMPLATE_PATH.insert(0, 'views/')
    STATIC_ROOT = 'static/'
    SimpleTemplate.defaults['DEBUG'] = True
    print("running in debug mode", file=sys.stderr)

  for i, cfg in enumerate (args.config):
    imp.load_source("cfg%s"%i, pathname=cfg)

  scheduler = Scheduler()
  scheduler.start()
  for c in checks:
    scheduler.schedule(c)

  HOST, PORT = args.listen.split(':')
  PORT = int(PORT)
  run(host=HOST, port=PORT, debug=args.debug, reloader=args.debug, interval=0.2)
