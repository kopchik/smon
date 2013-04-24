#!/usr/bin/env python

from bottle import SimpleTemplate, TEMPLATE_PATH, static_file, route, request, response, view, run
from subprocess import check_output, CalledProcessError
import argparse
import shlex
import time

__version__ = 1.2
CHECK_MDRAID = "sudo mdadm --detail --test --scan"
HOST = ''
PORT = 8181
OK = True
ER = False

PREFIX = '/usr/share/smon-%s/' % __version__
TEMPLATE_PATH.insert(0, PREFIX + 'views')
STATIC_ROOT = PREFIX + 'static'

class Time:
    def __str__(self):
        return time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
SimpleTemplate.defaults['tstamp'] = Time()

def check(cmd):
  if isinstance(cmd, str):
    cmd = shlex.split(cmd)
  try:
    r = check_output(cmd)
    return OK, r.decode()
  except CalledProcessError as err:
    return ER, err.output.decode()


class Monitor:
  def check_mdraid(self):
    st, out = check(CHECK_MDRAID)
    return st, out if out else "no raid configured?"
monitor = Monitor()


@route('/')
@view('all')
def all():
  checks = []
  status = OK
  for attr in dir(monitor):
    if attr.startswith("check_"):
      st, out = getattr(monitor, attr)()
      if st != OK: status = ER
      checks += [(st, out)]
  response.status = 200 if status == OK else 504
  return dict(checks=checks, status=status)

@route('/static/<path:path>')
def callback(path):
    return static_file(path, root='static/')

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Monitor the machine.')
  parser.add_argument('--debug', default=False, type=bool, const=True, nargs='?', help='enable debug mode')
  parser.add_argument('--listen', default="%s:%s"%(HOST,PORT), type=str,
      help='Override listen address. :8080 means to bind on 0.0.0.0:8080')
  args = parser.parse_args()
  HOST, PORT = args.listen.split(':')
  run(host=HOST, port=PORT, debug=args.debug, reloader=args.debug, interval=0.2)