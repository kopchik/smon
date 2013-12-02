smon
====


A simple monitoring system with web-console.

Usage
-----

Just create a config file like this:

~~~~
# cat /etc/smoncfg.py
from libsmon import Checker, CMDChecker
CHECK_MDRAID = "sudo mdadm --detail --test --scan"

CMDChecker(name="mdraid", cmd=CHECK_MDRAID, interval=120)
CMDChecker(name="backups", 
           cmd="ssh -o BatchMode=yes backupserver.net '/usr/bin/check_backups.sh'", interval=600)
~~~~

Then run smon.py and brouse the results on http://localhost:8181/ .
You may want to protect this page with a password :).
