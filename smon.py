#!/usr/bin/env python

from subprocess import check_output, CalledProcessError
from bottle import HTTPResponse, route, run
import argparse
import shlex

CHECK_MDRAID = "sudo mdadm --detail --test --scan"
HOST = ''
PORT = 8181
OK = True
ER = False

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
def all():
  output = []
  status = OK
  for attr in dir(monitor):
    if attr.startswith("check_"):
      st, out = getattr(monitor, attr)()
      if st != OK: status = ER
      output += [out]
  return HTTPResponse("\n".join(output), 200 if status == OK else 504)


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Monitor the machine.')
  parser.add_argument('--debug', default=False, type=bool, const=True, nargs='?', help='enable debug mode')
  parser.add_argument('--listen', default="%s:%s"%(HOST,PORT), type=str,
      help='Override listen address. :8080 means to bind on 0.0.0.0:8080')
  args = parser.parse_args()
  HOST, PORT = args.listen.split(':')
  run(host=HOST, port=PORT, debug=args.debug, reloader=args.debug, interval=0.2)
