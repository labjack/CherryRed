"""
For logging in CherryRed.
"""
import threading
import csv
from time import sleep
from datetime import datetime

class LoggingThread(threading.Thread):
    def __init__(self, device):
        threading.Thread.__init__(self)
        self.dev = device
        self.logging = False
        self.csvWriter = csv.writer(open("./log-%s.csv" % self.dev.serialNumber, "wb", 1))
        
    def stop(self):
        print "Stopping logging thread."
        self.logging = False
        
    def run(self):
        self.logging = True
        print "Starting logging thread for device %s." % self.dev.serialNumber
        
        while self.logging:
            result = self.dev.readRegister(0, numReg = 8)
            self.csvWriter.writerow([datetime.now()] + result)
            sleep(1)