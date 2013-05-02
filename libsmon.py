from subprocess import check_output, CalledProcessError
from threading import Thread, Lock, Timer
from queue import Queue, PriorityQueue
from useful.log import Log, set_global_level
from collections import deque
import shlex
import time
import sys

__version__ = 1.3
set_global_level("debug")
OK = True
ERR = False



class TimerCanceled(Exception):
  """Fired in .join() when MyTimer is aborted by .cancel"""


assert not hasattr(Timer, "canceled"),  \
    "Do not want to override attribute, pick another name"
assert not hasattr(Timer, "interval"),  \
    "Do not want to override attribute, pick another name"

class MyTimer(Timer):
  """ Advanced timer. It support the following enhancements:
      1. It keeps interval in .interval
      2. .join() raises TimerCanceled if timer was canceled
  """
  def __init__(self, t, f=lambda: True, **kwargs):
    super().__init__(t, f, **kwargs)
    self.canceled = False
    self.interval = t

  def cancel(self):
    super().cancel()
    self.canceled = True

  def join(self):
    super().join()
    if self.canceled:
      raise TimerCanceled


def run_cmd(cmd):
  if isinstance(cmd, str):
    cmd = shlex.split(cmd)
  try:
    r = check_output(cmd)
    return OK, r.decode()
  except CalledProcessError as err:
    return ERR, err.output.decode()


checks = []
class Checker:
  last_checked = None
  last_status = None, "<no check were performed yet>"

  def __init__(self, interval=60, name="<no name>", descr=None):
    self.interval = interval
    self.name = name
    self.descr = descr
    self.statuses = deque(maxlen=6)
    self.log = Log("checker %s" % self.__class__.__name__)
    global checks; checks += [self]

  def _check(self):
    if self.last_checked:
      delta = time.time() - self.last_checked
      if delta > (self.interval+1):
        self.log.critical("behind schedule for %ss" % delta)
    self.last_status  =  self.check()
    self.last_checked = time.time()
    self.statuses += [self.last_status]
    return self.last_status

  def check(self):
    return ERR, "<this is a generic check>"

  def get_next_check(self):
    if not self.last_checked:
      self.log.debug("was never checked, requesting immediate check")
      return -1
    now = time.time()
    next_check = self.last_checked + self.interval
    if next_check < now:
      return now
    return next_check

  def __lt__(self, other):
    return True


class CMDChecker(Checker):
  def __init__(self, cmd, **kwargs):
    super().__init__(**kwargs)
    self.cmd = cmd

  def check(self):
    st, out = run_cmd(self.cmd)
    return st, out if out else "no raid configured?"

  def __repr__(self):
    return '%s("%s")' % (self.__class__.__name__, self.cmd)


class Scheduler(Thread):
  """ Schedules and executes tasks using threaded workers
  """
  def __init__(self, workers=5):
    super().__init__(daemon=True)
    self.lock = Lock()       # lock queue manipulations
    self.inq  = PriorityQueue()
    self.outq = Queue()      # fired checks to be executed
    self.timer = MyTimer(0)  # timer placeholder for .schedule() so it can call self.timer.cancel() during first time
    self.log = Log("scheduler")
    for i in range(workers):
      worker = Worker(self)
      worker.start()

  def schedule(self, checker):
    time = checker.get_next_check()
    with self.lock:
      self.inq.put((time, checker))
      self.timer.cancel()  # trigger recalculate because this task may go before pending

  def run(self):
    while True:
      t, c = self.inq.get()
      with self.lock:
        now = time.time()
        self.timer = MyTimer(t-now)
      try:
        self.timer.start()
        self.log.debug("sleeping for %s" % self.timer.interval)
        self.timer.join()
      except TimerCanceled:
        self.log.notice("timer aborted, recalculating timeouts")
        with self.lock:
          print(t,c)
          self.inq.put((t,c))
        continue
      self.outq.put(c)


class Worker(Thread):
  def __init__(self, timeline):
    super().__init__(daemon=True)
    self.timeline = timeline
    self.log = Log("worker %s" % self.name)

  def run(self):
    queue = self.timeline.outq
    schedule = self.timeline.schedule
    while True:
      c = queue.get()
      self.log.debug("running %s" % c)
      r, out = c._check()
      schedule(c)
