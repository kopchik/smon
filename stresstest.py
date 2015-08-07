from libsmon import CMDChecker

for i in range(1,15):
  interval = 1/i
  CMDChecker(name="%.2f"%interval, cmd="ls -lad .", interval=interval)
