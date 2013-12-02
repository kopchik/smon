from libsmon import Checker, CMDChecker
CHECK_MDRAID = "sudo mdadm --detail --test --scan"

CMDChecker(CHECK_MDRAID, interval=120)
#CMDChecker("ls -la", interval=120)