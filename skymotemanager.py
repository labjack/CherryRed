# SkyMote Manager
from groundedutils import *
import threading
import LabJackPython, skymote

import csv, os
from datetime import datetime

def moteAsDict(mote):
    returnDict = dict()
    
    returnDict['name'] = mote.nickname
    returnDict['firmware'] = mote.mainFWVersion
    returnDict['productName'] = mote.productName
    returnDict['devType'] = mote.devType
    returnDict['serial'] = mote.serialNumber
    returnDict['unitId'] = mote.unitId
    returnDict['checkinInverval'] = mote.checkinInterval

    return returnDict

class SkyMoteManager(object):
    def __init__(self):
        # The address and port to try to connect to LJSocket
        self.address = LJSOCKET_ADDRESS
        self.port = LJSOCKET_PORT

        # Dictionary of all open bridges. Key = Serial, Value = Object.
        self.bridges = dict()
        
        # Logging Threads
        self.loggingThreads = dict()
        
        # Use Direct USB instead of LJSocket.
        self.usbOverride = False
        
    def shutdownThreads(self):
        """
        Called when cherrypy starts shutting down, shutdownThreads stops all the
        logging threads.
        """
        for s, thread in self.loggingThreads.items():
            thread.stop()
    
    def findBridges(self):
        print "self.bridges:", self.bridges
        devs = []
        ljsocketAddress = "localhost:6000"
        
        try:
            devs = LabJackPython.listAll(ljsocketAddress, 200)
        except:
            return {}
        
        #print "devsObj" = 
        
        #for dev in devsObj.values():
        #    devs.append({"serial" : dev["serialNumber"], "prodId" : dev["devType"]})
        
        for dev in devs:
            print "Got dev: serial = %s, prodId = 0x%X" % (dev['serial'], dev['prodId'])
            if dev['prodId'] != 0x501:
                continue
            elif str(dev['serial']) in self.bridges:
                d = self.bridges[str(dev['serial'])]
                if d.numMotes() != len(d.motes):
                    print "Found new motes"
                    d.motes = d.listMotes()
                    for mote in d.motes:
                        t = PlaceMoteInRapidModeThread(mote)
                        t.start()
                continue
            
            print "Got a bridge... opening."
            d = skymote.Bridge(LJSocket = ljsocketAddress, serial = dev['serial'])
            try:
                d.ethernetFirmwareVersion()
            except:
                d.ethernetFWVersion = "(No Ethernet)"
            d.nameCache = d.getName()
            d.usbFirmwareVersion()
            d.mainFirmwareVersion()
            d.productName = "SkyMote Bridge"
            d.meetsFirmwareRequirements = True
            d.spontaneousDataCache = dict()
            d.motes = d.listMotes()
            for mote in d.motes:
                t = PlaceMoteInRapidModeThread(mote)
                t.start()
            
            self.bridges["%s" % dev['serial']] = d
            
            t = SpontaneousDataLoggingThread(d)
            t.start()
            self.loggingThreads["%s" % dev['serial']] = t
        
        
        return self.bridges

    def scan(self):
        results = dict()
        
        for b in self.bridges.values():
            for mote in b.listMotes():
                results[str(mote.moteId)] = mote.sensorSweep()
                
        return results
    
    def getBridge(self, serial):
        if isinstance(serial, skymote.Bridge):
            return serial
        elif serial in self.bridges:
            return self.bridges[serial]
        else:
            return self.bridges[str(serial)]
    
    def scanBridge(self, serial):
        results = dict()
        
        b = self.getBridge(serial)
        
        numMotes = b.numMotes()
        
        if numMotes != len(b.motes):
            b.motes = b.listMotes()
            
            for mote in b.motes:
                t = PlaceMoteInRapidModeThread(mote)
                t.start()
        
        results['Number of Connected Motes'] = len(b.motes)
        
        motes = list()
        
        for m in b.motes:
            moteDict = moteAsDict(m)
            moteDict['Readings'] = b.spontaneousDataCache.get(str(m.unitId), {})
            
            motes.append(moteDict)
        
        results['Connected Motes'] = motes
        
        # Not implemented: results['Temperature'] = 
                
        return results
        

class PlaceMoteInRapidModeThread(threading.Thread):
    def __init__(self, mote):
        threading.Thread.__init__(self)
        self.daemon = True
        self.mote = mote

    def run(self):
        self.mote.startRapidMode()
        self.mote.nickname = self.mote.name
        self.mote.mainFirmwareVersion()
        self.mote.devType = self.mote.readRegister(65000)
        if self.mote.devType == 2000:
            self.mote.productName = "SkyMote TLB"
        else:
            self.mote.productName = "SkyMote Unknown Type"
        self.mote.readSerialNumber()
        self.mote.checkinInterval = self.mote.readCheckinInterval()

class SpontaneousDataLoggingThread(threading.Thread):
    def __init__(self, bridge):
        threading.Thread.__init__(self)
        self.daemon = True
        self.bridge = bridge
        self.name = sanitize(self.bridge.name)
        self.filename = "%%Y-%%m-%%d %%H__%%M__%%S %s %s.csv" % (self.name, "spontaneous")
        self.filename = datetime.now().strftime(self.filename)
        
        self.headers = [ "Timestamp", "Unit ID", "Temp", "Light", "Bump", "RxLQI", "TxLQI", "Battery"]
        
        self.filepath = "./logfiles/%s" % self.filename
        
        self.running = False
        
        try:
            self.stream = open(self.filepath, "wb", 1)
            self.csvWriter = csv.writer(self.stream)
        except IOError:
            os.mkdir("./logfiles")
            self.stream = open(self.filepath, "wb", 1)
            self.csvWriter = csv.writer(self.stream)
        
        self.csvWriter.writerow(self.headers)
        
    def stop(self):
        self.running = False
        
    def run(self):
        print "Spontaneous Data Logger for %s started." % (self.name)
        self.running = True
        
        while self.running:
            data = self.bridge.spontaneous().next()
            now = datetime.now()
            data['timestamp'] = str(now)
            self.bridge.spontaneousDataCache[str(data['unitId'])] = data
            print "Logging spontaneous data."
            
            results = [ now, data['unitId'], data['Temp'], data['Light'], data['Motion'], data['RxLQI'], data['TxLQI'], data['Battery']]
            self.csvWriter.writerow(results)
        
        print "Spontaneous Data Logger for %s stopped." % (self.name)
        
        
        #{'Sound': 0.0, 'RxLQI': 108.0, 'unitId': 5, 'Temp': 24.9375, 'Battery': 4.3470158576965332, 'Light': 2716.149658203125, 'Motion': 0.0, 'TxLQI': 120.0}
















