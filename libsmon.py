from subprocess import check_output, CalledProcessError
from threading import Thread, Lock, Timer, Event
from queue import Queue, PriorityQueue, Empty
from useful.log import Log, logfilter
from collections import deque
import shlex
import time

__version__ = 1.9
logfilter.default = True
OK = True
ERR = False
logfilter.rules.append(("*.debug", False))


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
    if t < 0:
      t = 0  # just in case, not really needed by standard implementation
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
    return ERR, "<you need to override this method>"

  def get_next_check(self):
    if not self.last_checked:
      # was never checked, requesting immediate check"
      next_check = -1
    elif self.last_status[0] == OK:
      next_check = self.last_checked + self.interval
    else:
      # reduce interval if last status was bad
      next_check = self.interval / 3
      next_check = max(next_check, 10)   # not less than 10 seconds
      next_check = min(next_check, 120)  # no more than two minutes
      next_check += self.last_checked
    return next_check

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
    self.timer   = MyTimer(0)             # timer placeholder for .schedule() so it can call self.timer.cancel() during the first call
    self.lock    = Lock()                 # lock pending queue
    self.lockev  = Event()                # set by .run() when lock is acquired
    self.history = deque(maxlen=histlen)  # keep track of the history
    self.log     = Log("scheduler")

    for i in range(workers):
      worker = Worker(self)
      worker.start()

  def flush(self):
    """ Request immidiate check. """
    self.log.debug("flushing pending queue")
    with self.lock:
      self.lockev.clear()
      self.pending.put((-1000, None))
      self.timer.cancel()
      self.lockev.wait()

      queued = []
      while True:
        try:
          _, check = self.pending.get(block=False)
          queued.append(check)
        except Empty:
          break

      for checker in queued:
        self.ready.put(checker)
      self.log.debug("flushing done")

  def schedule(self, checker):
    t = checker.get_next_check()
    with self.lock:
      self.pending.put((t, checker))
      self.timer.cancel()

  def run(self):
    pending = self.pending
    ready   = self.ready
    while True:
      t, c = pending.get()
      if c is None:
        self.lockev.set()
        with self.lock:
          continue

      with self.lock:
        delta = t - time.time()
        self.log.debug("sleeping for %.2f" % delta)
        self.timer = MyTimer(delta)
        self.timer.start()

      try:
        self.timer.join()
        ready.put(c)
      except TimerCanceled:
        self.log.debug("new item scheduled, restarting scheduler (this is normal)")
        pending.put((t, c))


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
      checker = queue.get()
      self.log.debug("running %s" % checker)
      r, out = checker._check()
      self.log.debug("result: %s %s" %(r, out))
      schedule(checker)
      history.appendleft((time.time(), r, out))
