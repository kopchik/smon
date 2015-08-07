from subprocess import check_output, CalledProcessError
from threading import Thread, Lock, Timer
from queue import Queue, PriorityQueue
from useful.log import Log, logfilter
from collections import deque
import shlex
import time

__version__ = 1.4
logfilter.default = True
OK = True
ERR = False


def run_cmd(cmd):
  if isinstance(cmd, str):
    cmd = shlex.split(cmd)
  try:
    r = check_output(cmd)
    return OK, r.decode()
  except CalledProcessError as err:
    return ERR, err.output.decode()


class TimerCanceled(Exception):
  """Fired in .join() when MyTimer is aborted by .cancel"""


assert not hasattr(Timer, "canceled"),  \
    "Do not want to override attribute, pick another name"
assert not hasattr(Timer, "interval"),  \
    "Do not want to override attribute, pick another name"


class MyTimer(Timer):
  """ A timer with the following enhancements:
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


all_checks = []
class Checker:
  last_checked = None
  last_status = None, "<no check were performed yet>"

  def __init__(self, interval=60, name="<no name>", descr=None):
    global all_checks
    all_checks.append(self)
    self.interval = interval
    self.name = name
    self.descr = descr
    self.statuses = deque(maxlen=10)
    self.log = Log("checker %s" % self.__class__.__name__)

  def _check(self):
    if self.last_checked:
      delta = time.time() - self.last_checked
      if delta > (self.interval + 1):  # tolerate one second delay
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
    """ Dummy function to make instances orderable and comparable. Used by PriorityQueue. """
    return True


class CMDChecker(Checker):
  def __init__(self, cmd, **kwargs):
    super().__init__(**kwargs)
    self.cmd = cmd

  def check(self):
    st, out = run_cmd(self.cmd)
    return st, out if out else "(no output)"

  def __repr__(self):
    return '%s("%s")' % (self.__class__.__name__, self.cmd)


class Scheduler(Thread):
  """ Schedules and executes tasks using threaded workers. """
  def __init__(self, workers=5, histlen=10000):
    super().__init__(daemon=True)
    self.pending = PriorityQueue()
    self.ready = Queue()      # fired checks to be executed
    self.lock = Lock()        # lock queue manipulations
    self.timer = MyTimer(0)   # timer placeholder for .schedule() so it can call self.timer.cancel() during the first call
    self.log = Log("scheduler")
    self.history = deque(maxlen=histlen)  # keep track of the history
    for i in range(workers):
      worker = Worker(self)
      worker.start()

  def schedule(self, checker):
    t = checker.get_next_check()
    with self.lock:
      self.pending.put((t, checker))
      self.timer.cancel()  # trigger recalculate because this task may go before pending

  def run(self):
    while True:
      t, c = self.pending.get()
      with self.lock:
        now = time.time()
        self.timer = MyTimer(t-now)
      try:
        self.timer.start()
        self.log.debug("sleeping for %s" % self.timer.interval)
        self.timer.join()
      except TimerCanceled:
        self.log.debug("new item scheduled, restarting scheduler (this is normal)")
        with self.lock:
          print(t,c)
          self.pending.put((t, c))
        continue
      self.ready.put(c)


class Worker(Thread):
  """ Get tasks that are ready to run and execute them. """
  def __init__(self, scheduler):
    super().__init__(daemon=True)
    self.scheduler = scheduler
    self.log = Log("worker %s" % self.name)

  def run(self):
    queue = self.scheduler.ready
    schedule = self.scheduler.schedule
    history  = self.scheduler.history
    while True:
      c = queue.get()
      self.log.debug("running %s" % c)
      r, out = c._check()
      schedule(c)
      history.appendleft((time.time(), r, out))
