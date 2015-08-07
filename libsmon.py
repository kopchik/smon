from subprocess import check_output, CalledProcessError
from threading import Thread, Lock, Timer, Condition
from queue import Queue, PriorityQueue, Empty
from useful.log import Log, logfilter
from collections import deque
import shlex
import time

__version__ = 1.9
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
  """ This exception fired in .join() when MyTimer is aborted by .cancel. """


class MyTimer(Timer):
  """ A timer with the following enhancements:
      1. It keeps interval in .interval
      2. .join() raises TimerCanceled if timer was canceled
  """
  assert not hasattr(Timer, "canceled"),  \
      "Do not want to override attribute, pick another name"
  assert not hasattr(Timer, "interval"),  \
      "Do not want to override attribute, pick another name"

  def __init__(self, t, f=lambda: True, **kwargs):
    if t < 0: t = 0  # just in case, not really needed by current implementation
    super().__init__(t, f, **kwargs)
    self.canceled = False

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
  last_status = None, "<no checks were performed yet>"

  def __init__(self, interval=60, name="<no name>", descr=None, histlen=10):
    global all_checks
    all_checks.append(self)
    self.interval = interval
    self.name     = name
    self.descr    = descr
    self.history  = deque(maxlen=histlen)
    self.log      = Log("checker %s" % self.__class__.__name__)

  def _check(self):
    if self.last_checked:
      delta = time.time() - self.last_checked
      if delta > (self.interval + 1):  # tolerate one second delay
        self.log.critical("behind schedule for %ss" % delta)
    self.last_status  =  self.check()
    self.last_checked = time.time()
    self.history.append(self.last_status)
    self.last_checked = time.time()
    return self.last_status

  def check(self):
    return ERR, "<this is a generic check>"

  def get_next_check(self):
    if not self.last_checked:
      self.log.debug("was never checked, requesting immediate check")
      return -1
    return self.last_checked + self.interval

  def __lt__(self, other):
    """ This is for PriorityQueue that requires added elements to support ordering. """
    return True


class CMDChecker(Checker):
  def __init__(self, cmd, **kwargs):
    super().__init__(**kwargs)
    self.cmd = cmd

  def check(self):
    status, output = run_cmd(self.cmd)
    return status, (output if output else "<no output>")

  def __repr__(self):
    return '%s("%s")' % (self.__class__.__name__, self.cmd)


class Scheduler(Thread):
  """ Schedules and executes tasks using threaded workers. """
  def __init__(self, workers=5, histlen=10000):
    super().__init__(daemon=True)
    self.pending = PriorityQueue()
    self.ready   = Queue()                # checks to be executed
    self.cond    = Condition()
    self.state   = None
    self.lock    = Lock()                 # lock queue manipulations
    self.timer   = MyTimer(0)             # timer placeholder for .schedule() so it can call self.timer.cancel() during the first call
    self.log     = Log("scheduler")
    self.history = deque(maxlen=histlen)  # keep track of the history
    for i in range(workers):
      worker = Worker(self)
      worker.start()

  def flush(self):
      """ Request immidiate check. """
      # TODO: the current pending task won't be flushed
      self.log.debug("flushing queue")
      with self.cond:
        self.cond.waitfor(lambda: self.state == 'loop')
        while True:
          try:
            _, check = self.pending.get_nowait()
            self.ready.put(check)
          except Empty:
            pass
      self.recalculate()

  def recalculate(self):
    """ recalculate timeouts (e.g., when new event was added) """
    with self.lock:
      self.timer.cancel()  # trigger timeline recalculate

  def schedule(self, checker):
    t = checker.get_next_check()
    self.pending.put((t, checker))
    self.recalculate()

  def run(self):
    while True:
      t, c = self.pending.get()
      with self.lock:
        delta = t - time.time()
        self.log.debug("sleeping for %.2f" % delta)
        self.timer = MyTimer(delta)
        self.timer.start()

      try:
        self.timer.join()
        self.ready.put(c)
      except TimerCanceled:
        self.log.debug("new item scheduled, restarting scheduler (this is normal)")
        self.pending.put((t, c))
        continue



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
