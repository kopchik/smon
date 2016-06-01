from subprocess import check_output, CalledProcessError, STDOUT
from threading import Thread, Lock, Timer
from queue import Queue, PriorityQueue, Empty
from useful.log import Log, logfilter
from collections import deque
import shlex
import time
import sys

__version__ = 1.7
OK = True
ERR = False
logfilter.rules.append(("*.debug", False))



class TimerCanceled(Exception):
  """Fired in .join() when MyTimer is aborted by .cancel"""


assert not hasattr(Timer, "canceled"),  \
    "Do not want to override attribute, pick another name"
class MyTimer(Timer):
  """ Advanced timer. It support the following enhancements:
      2. .join() raises TimerCanceled if timer was canceled
  """
  def __init__(self, t, f=lambda: True, **kwargs):
    super().__init__(t, f, **kwargs)
    self.canceled = False

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
    r = check_output(cmd, stderr=STDOUT)
    return OK, r.decode()
  except CalledProcessError as err:
    return ERR, err.output.decode()


checks = []
class Checker:
  last_checked = None
  last_status = None, "<no checks were performed yet>"

  def __init__(self, interval=60, name="<no name>", descr=None, history=6):
    self.interval = interval
    self.name = name
    self.descr = descr
    self.statuses = deque(maxlen=history)
    self.log = Log("checker %s" % self.__class__.__name__)
    global checks; checks += [self]

  def _check(self):
    if self.last_checked:
      delay = time.time() - self.last_checked - self.interval
      if delay > 0.5:
        self.log.critical("we are %.2fs behind the schedule (interval=%.2fs)" % (delay, self.interval))
    try:
      self.last_status  =  self.check()
    except Exception as err:
      self.last_status = ERR, err
    self.statuses += [self.last_status]
    self.last_checked = time.time()
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
    """ This is for PriorityQueue that requires added elements
        to support ordering
    """
    return True


class CMDChecker(Checker):
  def __init__(self, cmd, **kwargs):
    super().__init__(**kwargs)
    self.cmd = cmd

  def check(self):
    st, out = run_cmd(self.cmd)
    return st, (out if out else "<no output>")

  def __repr__(self):
    return '%s("%s")' % (self.__class__.__name__, self.cmd)


class Scheduler(Thread):
  """ Schedules and executes tasks using threaded workers
  """
  def __init__(self, workers=5):
    super().__init__(daemon=True)
    self.qlock = Lock()      # freeze scheduling of pending tasks
    self.queue  = PriorityQueue()
    self.outq = Queue()      # fired checks to be executed
    self.timer = MyTimer(0)  # timer placeholder for .schedule() so it can call self.timer.cancel() during the first time
    self.log = Log("scheduler")
    for i in range(workers):
      worker = Worker(self)
      worker.start()

  def flush(self):
      """ Request immidiate check.  """
      self.queue.put((-1, None))  # -1 to ensure that this event will be served first
      with self.qlock:
        self.timer.cancel()

  def _flush(self):
    """ flush the queue. To be called by run() """
    while True:
      try:
        _,c = self.queue.get(block=False)
        self.outq.put(c)
      except Empty:
        break

  def schedule(self, checker):
    time = checker.get_next_check()
    self.queue.put((time, checker))
    with self.qlock:
      self.timer.cancel()  # trigger timeline recalculate

  def run(self):
    while True:
      with self.qlock:
        t,c = self.queue.get()
        if c == None:  # flush() was called
          self._flush()
          continue

        delta = t - time.time()
        self.timer = MyTimer(delta)
        self.timer.start()

      try:
        self.log.debug("sleeping for %.2f" % delta)
        self.timer.join()
      except TimerCanceled:
        self.log.debug("timer aborted, recalculating timeouts")
        self.queue.put((t,c))  # put back pending task
        continue  # restart loop

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
