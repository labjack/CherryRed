"""
For logging in CherryRed.
"""
import threading
import csv
from time import sleep
from datetime import datetime

class LoggingThread(threading.Thread):
    def __init__(self, dm, serial):
        threading.Thread.__init__(self)
        self.dm = dm
        self.serial = str(serial)
        self.logging = False
        self.csvWriter = csv.writer(open("./log-%s.csv" % self.serial, "wb", 1))
        
    def stop(self):
        print "Stopping logging thread."
        self.logging = False
        
    def run(self):
        self.logging = True
        print "Starting logging thread for device %s." % self.serial
        
        while self.logging:
            result = self.dm.scan(self.serial)[1]
            values = [ None ] * (len(result)+1)
            values[0] = datetime.now()
            for i, connection in enumerate(result):
                values[i+1] = connection['value']
            self.csvWriter.writerow(values)
            sleep(1)