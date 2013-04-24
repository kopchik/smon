#!/usr/bin/env python3
from smon import *
from useful.log import set_global_level

set_global_level("debug")

def test_timer():
  t = MyTimer(2)
  t.start()
  canceler = MyTimer(0.2, lambda: t.cancel())
  canceler.start()
  try:
    t.join()
  except TimerCanceled:
    pass


class TestChecker(Checker):
  interval = 1
  def check(self):
    self.last_checked = time.time()
    print("checking... done")
    return OK, "<check done>"


def test_timeline():
  scheduler = Scheduler()
  scheduler.start()
  scheduler.schedule(TestChecker())
  t = MyTimer(2)
  t.start()
  t.join()