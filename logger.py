"""
For logging in CherryRed.
"""
import threading
import csv, os
from time import sleep
from datetime import datetime

import re

def sanitize(name):
    """
    >>> sanitize("My U3-HV")
    'My U3-HV'
    >>> sanitize("My U3-HV%$#@!")
    'My U3-HV'
    >>> sanitize("My_Underscore_Name")
    'My_Underscore_Name'
    """
    p = re.compile('[^a-zA-Z0-9_ -]')
    return p.sub('', name)

class LoggingThread(object):
    def __init__(self, dm, serial, name, headers = None):
        self.dm = dm
        self.serial = str(serial)
        self.name = sanitize(name)
        if headers:
            self.headers = ["Timestamp"] + headers
        else:
            self.headers = None
        self.logging = False
        self.filename = "./logfiles/%%Y-%%m-%%d %%H__%%M__%%S %s %s.csv" % (sanitize(name), self.serial)
        self.filename = datetime.now().strftime(self.filename)
        
        try:
            self.csvWriter = csv.writer(open(self.filename, "wb", 1))
        except IOError:
            os.mkdir("./logfiles")
            self.csvWriter = csv.writer(open(self.filename, "wb", 1))
            
        self.interval = 1
        self.timer = None
        
    def stop(self):
        print "Stopping logging thread."
        self.logging = False
        try:
            self.timer.cancel()
        except:
            pass
        
    def start(self):
        self.logging = True
        print "Starting logging thread for device %s." % self.serial
        
        if self.headers:
            self.csvWriter.writerow(self.headers)
            
        self.rescheduleThenRun()
       
    def _rescheduleTimer(self):
        self.timer = threading.Timer(self.interval, self.rescheduleThenRun)
        self.timer.start()
        
    def rescheduleThenRun(self):
        print "rescheduleThenRun", datetime.now()
        if not self.logging:
            return None
        
        self._rescheduleTimer()
        
        result = self.dm.scan(self.serial)[1]
        values = [ None ] * (len(result)+1)
        values[0] = datetime.now()
        for i, connection in enumerate(result):
            values[i+1] = connection['value']
        self.csvWriter.writerow(values)