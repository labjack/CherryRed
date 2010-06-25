"""
For logging in CherryRed.
"""
import csv, os
from time import sleep
from datetime import datetime

from groundedutils import sanitize

class LoggingThread(object):
    def __init__(self, dm, serial, name, headers = None):
        self.dm = dm
        self.serial = str(serial)
        self.name = sanitize(name)
        self.event = None
        if headers:
            self.headers = ["Timestamp"] + headers
        else:
            self.headers = None
        self.first = True
        self.filename = "%%Y-%%m-%%d %%H__%%M__%%S %s %s.csv" % (self.name, self.serial)
        self.filename = datetime.now().strftime(self.filename)
        
        self.filepath = "./logfiles/%s" % self.filename
        try:
            self.csvWriter = csv.writer(open(self.filepath, "wb", 1))
        except IOError:
            os.mkdir("./logfiles")
            self.csvWriter = csv.writer(open(self.filepath, "wb", 1))
        
    def stop(self):
        self.event.reschedule = False

    def log(self):
        print "log:", datetime.now()
        
        if self.first and self.headers:
            self.csvWriter.writerow(self.headers)
            self.first = False
        
        result = self.dm.scan(self.serial)[1]
        if self.headers:
            values = []
            values.append(datetime.now())
            for i, connection in enumerate(result):
                if connection["connection"] in self.headers:
                    values.append(connection['value'])
        else:
            values = [ None ] * (len(result)+1)
            values[0] = datetime.now()
            for i, connection in enumerate(result):
                values[i+1] = connection['value']
        self.csvWriter.writerow(values)