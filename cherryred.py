"""

Name: cherryred.py
Desc:

"""

# Imports
import cherrypy
import cherrypy.lib
from cherrypy.lib.static import serve_file
from Cheetah.Template import Template
from datetime import datetime

from threading import Lock, Event

import xmppconnection, logger, scheduler
from groundedutils import sanitize
from fio import FIO, UE9FIO

import os, os.path, zipfile

import json, httplib2
from urllib import urlencode

import sys, time

import cStringIO as StringIO, ConfigParser

import LabJackPython, u3, u6, ue9, bridge
from Autoconvert import autoConvert

import webbrowser

import mimetypes
mimetypes.init()
mimetypes.types_map['.dwg']='image/x-dwg'
mimetypes.types_map['.ico']='image/x-icon'
mimetypes.types_map['.bz2']='application/x-bzip2'
mimetypes.types_map['.gz']='application/x-gzip'
mimetypes.types_map['.csv']='text/plain'

import gdata.docs.service
import gdata.service

# Function dictionaries:
def buildLowerDict(aClass):
    d = {}
    for key in aClass.__dict__:
        if not key.startswith('_'):
            d[key.lower()] = key
    for key in LabJackPython.Device.__dict__:
        if not key.startswith('_'):
            d[key.lower()] = key
    return d

CLOUDDOT_GROUNDED_VERSION = "0.01"

CLOUDDOT_GROUNDED_CONF = "./clouddotgrounded.conf"
GOOGLE_DOCS_SCOPE = 'https://docs.google.com/feeds/'

# Map all the functions to lower case.
u3Dict = buildLowerDict(u3.U3)
u6Dict = buildLowerDict(u6.U6)
ue9Dict = buildLowerDict(ue9.UE9)

LJSOCKET_ADDRESS = "localhost"
LJSOCKET_PORT = "6000"

ANALOG_TYPE = "analogIn"
DIGITAL_OUT_TYPE = "digitalOut"
DIGITAL_IN_TYPE = "digitalIn"

DAC_DICT = { 5000: "DAC0", 5002: "DAC1" }

FLOAT_FORMAT = "%0.3f"

if not getattr(sys, 'frozen', ''):
    # not frozen: in regular python interpreter
    IS_FROZEN = False
else:
    # py2exe: running in an executable
    IS_FROZEN = True

# Create some decorator methods for functions.
def exposeRawFunction(f):
    """ Simply exposes the function """
    f.exposed = True
    return f

def exposeJsonFunction(f):
    """
    Creates and exposes a function which will JSON encode the output of the
    passed in function.
    """
    def jsonFunction(self, *args, **kwargs):
        cherrypy.response.headers['content-type'] = "application/json"
        result = f(self, *args, **kwargs)
        return json.dumps(result)
        
    jsonFunction.exposed = True
    return jsonFunction


def kelvinToFahrenheit(value):
    """Converts Kelvin to Fahrenheit"""
    # F = K * (9/5) - 459.67
    return value * (9.0/5.0) - 459.67

def internalTempDict(kelvinTemp):
    # Returns Kelvin, converting to Fahrenheit
    # F = K * (9/5) - 459.67
    internalTemp = kelvinToFahrenheit(kelvinTemp)
    return {'connection' : "Internal Temperature", 'state' : (FLOAT_FORMAT + " &deg;F") % internalTemp, 'value' : FLOAT_FORMAT % internalTemp, 'chType' : "internalTemp", "disabled" : True}

def deviceAsDict(dev):
    """ Returns a dictionary representation of a device.
    """
    name = dev.getName()
    
    if dev.devType == 9:
        firmware = [dev.commFWVersion, dev.controlFWVersion]
    elif dev.devType == 0x501:
        firmware = [dev.ethernetFWVersion, dev.usbFWVersion]
    else:
        firmware = dev.firmwareVersion 
    
    return {'devType' : dev.devType, 'name' : name, 'serial' : dev.serialNumber, 'productName' : dev.deviceName, 'firmware' : firmware, 'localId' : dev.localId}


def replaceUnderscoresWithColons(filename):
    splitFilename = filename.split(" ")
    if len(splitFilename) > 1:
        replacedFilename = splitFilename[1].replace("__", ":").replace("__", ":")
        splitFilename[1] = replacedFilename
        newName = " ".join(splitFilename)
        return newName
    else:
        return filename

# Class Definitions

class DeviceManager(object):
    """
    The DeviceManager class will manage all the open connections to LJSocket
    """
    def __init__(self):
        self.address = LJSOCKET_ADDRESS
        self.port = LJSOCKET_PORT
        
        self.username = None
        self.apikey = None
        
        self.devices = dict()
        self.xmppThreads = dict()
        
        self.loggingScheduler = scheduler.Scheduler()
        self.loggingThreads = dict()
        
        self.loggingThreadLock = Lock()
        
        # There are times when we need to pause scans for a moment.
        self.scanEvent = Event()
        self.scanEvent.set()
        
        cherrypy.engine.subscribe('stop', self.shutdownThreads)
        
        self.usbOverride = False
        
        try:
            self.updateDeviceDict()
            self.connected = True
        except Exception:
            try:
                self.usbOverride = True
                self.updateDeviceDict()
                self.connected = True
            except Exception:
                self.connected = False
            
        
        print self.devices
    
    def getDevice(self, serial):
        if serial is None:
            return self.devices.values()[0]
        else:
            return self.devices[serial]
    
    def makeLoggingSummary(self):
        loggingList = []
        
        for serial, thread in self.loggingThreads.items():
            headers = list(thread.headers)
            headers.remove("Timestamp")
            loggingList.append({ "devName" : thread.name, "headers" : ", ".join(headers), "filename" : thread.filename, "serial" : serial, "logname" : replaceUnderscoresWithColons(thread.filename), "stopurl" : "/logs/stop?serial=%s" % serial})
        
        return loggingList
    
    def startDeviceLogging(self, serial, headers = None):
        d = self.getDevice(serial)
        returnValue = False
        
        try:
            self.loggingThreadLock.acquire()
            if str(d.serialNumber) not in self.loggingThreads:
                lt = logger.LoggingThread(self, d.serialNumber, d.getName(), headers)
                e = self.loggingScheduler.addReschedulingEvent(1, lt.log)
                lt.event = e
                self.loggingThreads[str(d.serialNumber)] = lt
                
                returnValue = True
            else:
                sn = str(d.serialNumber)
                if self.loggingThreads[sn].headers != headers:
                    lt = self.loggingThreads[sn]
                    lt.stop()
                    if headers:
                        lt = logger.LoggingThread(self, d.serialNumber, d.getName(), headers)
                        e = self.loggingScheduler.addReschedulingEvent(1, lt.log)
                        lt.event = e
                        self.loggingThreads[str(d.serialNumber)] = lt
                        returnValue = True
                    else:
                        self.loggingThreads.pop(sn)
                        returnValue = True
                else:
                     returnValue =  False
        finally:
            self.loggingThreadLock.release()
        
        return returnValue    
        
    def stopDeviceLogging(self, serial):
        d = self.getDevice(serial)
        returnValue = False
        
        try:
            self.loggingThreadLock.acquire()
            if str(d.serialNumber) in self.loggingThreads:
                lt = self.loggingThreads.pop(str(d.serialNumber))
                lt.stop()
                returnValue = True
            else:
                returnValue = False
        finally:
            self.loggingThreadLock.release()
        
        return returnValue
    
    def connectDeviceToCloudDot(self, serial):
        d = self.getDevice(serial)
        
        if str(d.serialNumber) not in self.xmppThreads:
            xt = xmppconnection.XmppThread(d, password = self.apikey)
            xt.start()
            self.xmppThreads[str(d.serialNumber)] = xt
            
            return True
        else:
            return False
        
    def shutdownThreads(self):
        for s, thread in self.xmppThreads.items():
            thread.stop()
            
        self.loggingScheduler.shutdown()
    
    def getFioInfo(self, serial, inputNumber):
        dev = self.getDevice(serial)
        
        if inputNumber in DAC_DICT.keys():
            returnDict = { "state" : dev.readRegister(inputNumber), "label" : DAC_DICT[inputNumber], "connectionNumber" : inputNumber, "chType" : "DAC" }
        elif dev.devType == 9:
            returnDict = UE9FIO.getFioInfo(dev, inputNumber)
        else:
            returnDict = dev.fioList[inputNumber].asDict()
        
        # devType, productName
        returnDict['device'] = deviceAsDict(dev)
        
        return returnDict
        
    def updateFio(self, serial, inputConnection):
        dev = self.getDevice(serial)
        try:
            self.scanEvent.clear()
            if dev.devType == 9:
                UE9FIO.updateFIO(dev, inputConnection)
            else:
                current = dev.fioList[ inputConnection.fioNumber ]
                current.transform(dev, inputConnection)
                
                if dev.devType == 6:
                    self.remakeU6AnalogCommandList(dev)
                elif dev.devType == 3:
                    self.remakeFioList(dev)
        finally:
            self.scanEvent.set()
    
    def remakeFioList(self, serial):
        if isinstance(serial, str):
            dev = self.getDevice(serial)
        else:
            dev = serial
        
        if dev.devType == 3:
            fioList, fioFeedbackCommands = self.makeU3FioList(dev)
            dev.fioList = fioList
            dev.fioFeedbackCommands = fioFeedbackCommands
        elif dev.devType == 6:
            self.remakeU6AnalogCommandList(dev)
    
    def remakeU6AnalogCommandList(self, dev):
        analogCommandList = list()
        for i in range(14):
            ain = dev.fioList[i]
            analogCommandList.append( ain.makeFeedbackCommand(dev) )
        
        dev.analogCommandList = analogCommandList

    def makeU6FioList(self, dev):
        # Make a list to hold the state of all the fios
        fios = list()
        analogCommandList = list()
        for i in range(14):
            fios.append( FIO(i) )
            analogCommandList.append( u6.AIN24(i) )
        dev.numberOfAnalogIn = 14
        
        for i in range(20):
            
            label = "FIO%s"
            labelOffset = 0
            if i in range(8,16):
                label = "EIO%s"
                labelOffset = -8
            elif i >= 16:
                label = "CIO%s"
                labelOffset = -16            
        
            fioDir = dev.readRegister(6100 + i)
            fioState = dev.readRegister(6000 + i)                
            fios.append( FIO(i+14, label = label % (i + labelOffset), chType = (DIGITAL_IN_TYPE if fioDir == 0 else DIGITAL_OUT_TYPE), state = fioState) )
        dev.numberOfDigitalIOs = 20
        
        digitalCommandList = [ u6.PortDirRead(), u6.PortStateRead() ]
            
        return fios, analogCommandList, digitalCommandList


    def makeU3FioList(self, dev):
        # Make a list to hold the state of all the fios
        
        fioAnalog = dev.readRegister(50590)
        eioAnalog = dev.readRegister(50591)
        
        results = list()
        
        fios = list()
        for i in range(20):
            analog = ( fioAnalog if i < 8 else eioAnalog )
            
            label = "FIO%s"
            labelOffset = 0
            if i in range(8,16):
                label = "EIO%s"
                labelOffset = -8
            elif i >= 16:
                label = "CIO%s"
                labelOffset = -16            
        
            if i < 16 and (( analog >> (i + labelOffset)) & 1):
                fios.append( FIO(i) )
            else:
                fioDir = dev.readRegister(6100 + i)
                fioState = dev.readRegister(6000 + i)
                
                fios.append( FIO(i, label % (i + labelOffset), (DIGITAL_IN_TYPE if fioDir == 0 else DIGITAL_OUT_TYPE), fioState) )
        
        fioFeedbackCommands = list()
        for fio in fios:
            fioFeedbackCommands.append(fio.makeFeedbackCommand(dev))
        
        return fios, fioFeedbackCommands
        
    
    def updateDeviceDict(self):
        try:
            if self.usbOverride:
                self.scanEvent.clear()
                ljsocketAddress = None
                devs = list()
                
                devCount = LabJackPython.deviceCount(None)
                
                for serial, dev in self.devices.items():
                    dev.close()
                    self.devices.pop(str(serial))
                
                devsObj = LabJackPython.listAll(3)
                for dev in devsObj.values():
                    devs.append({"serial" : dev["serialNumber"], "prodId" : dev["devType"]})
                
                devsObj = LabJackPython.listAll(6)
                for dev in devsObj.values():
                    devs.append({"serial" : dev["serialNumber"], "prodId" : dev["devType"]})
                
                devsObj = LabJackPython.listAll(9)
                for dev in devsObj.values():
                    devs.append({"serial" : dev["serialNumber"], "prodId" : dev["devType"]})
                    
                devsObj = LabJackPython.listAll(0x501)
                for dev in devsObj.values():
                    devs.append({"serial" : dev["serialNumber"], "prodId" : dev["devType"]})
                    
                print "usbOverride:",devs
                    
            else:
                ljsocketAddress = "%s:%s" % (self.address, self.port)
                devs = LabJackPython.listAll(ljsocketAddress, LabJackPython.LJ_ctLJSOCKET)
            
            serials = list()
            
            for dev in devs:
                serials.append(str(dev['serial']))
            
                if str(dev['serial']) in self.devices:
                    continue
                
                if dev['prodId'] == 3:
                    print "Adding new device with serial = %s" % (dev['serial'])
                    try:
                        d = u3.U3(LJSocket = ljsocketAddress, serial = dev['serial'])
                    except Exception, e:
                        raise Exception( "Error opening U3: %s" % e )
                        
                    try:
                        d.configU3()
                        d.getCalibrationData()
                    except Exception, e:
                        raise Exception( "Error with configU3: %s" % e )
                        
                    try:
                        #d.debug = True
                        fioList, fioFeedbackCommands = self.makeU3FioList(d)
                        d.fioList = fioList
                        d.fioFeedbackCommands = fioFeedbackCommands
                    except Exception, e:
                        print "making u3 fio list: %s" % e
                        raise Exception( "making u3 fio list: %s" % e )
                    
                elif dev['prodId'] == 6:
                    try:
                        d = u6.U6(LJSocket = ljsocketAddress, serial = dev['serial'])
                        d.configU6()
                        d.getCalibrationData()
                        fios, analogCommandList, digitalCommandList = self.makeU6FioList(d)
                        d.fioList = fios
                        d.analogCommandList = analogCommandList
                        d.digitalCommandList = digitalCommandList
                    except Exception, e:
                        print "In opening a U6: %s" % e
                    
                elif dev['prodId'] == 9:
                    d = ue9.UE9(LJSocket = ljsocketAddress, serial = dev['serial'])
                    d.controlConfig()
                    
                    UE9FIO.setupNewDevice(d)
                    
                elif dev['prodId'] == 0x501:
                    print "Got a bridge... opening."
                    d = bridge.Bridge(LJSocket = ljsocketAddress, serial = dev['serial'])
                    d.ethernetFirmwareVersion()
                    d.usbFirmwareVersion()
                else:
                    raise Exception("Unknown device type")
                
                d.scanCache = (0, None)
                d.timerCounterCache = None
                self.devices["%s" % dev['serial']] = d
            
            # Remove the disconnected devices
            for serial in self.devices.keys():
                if serial not in serials:
                    print "Removing device with serial = %s" % serial
                    self.devices[str(serial)].close()
                    self.devices.pop(str(serial))
        finally:
            self.scanEvent.set()
                   

    def scan(self, serial = None, noCache = False):
        self.scanEvent.wait()
        dev = self.getDevice(serial)
        now = int(time.time())
        if noCache or (now - dev.scanCache[0]) >= 1:
            if dev.devType == 3:
                result = self.u3Scan(dev)
            elif dev.devType == 6:
                result = self.u6Scan(dev)
            elif dev.devType == 9:
                result = self.ue9Scan(dev)
            elif dev.devType == 0x501:
                num = dev.readNumberOfMotes()
                result = [dev.serialNumber, [{'connection' : 'Number Of Motes', 'state' : num, 'value' : num, 'chType' : ANALOG_TYPE }]]
                
            dev.scanCache = (now, result)
            return result
        else:
            return dev.scanCache[1]
    

    def readTimer(self, dev, timerNumber):
        timer = dev.readRegister(7200 + (2 * timerNumber))
        infoDict = {'connection' : "Timer %s" % timerNumber, 'state' : "%s" % timer, 'value' : "%s" % timer}
        infoDict['chType'] = ("timer")
        
        return infoDict
        
    def readCounter(self, dev, counterNumber):
        counter = dev.readRegister(7300 + (2 * counterNumber))
        infoDict = {'connection' : "Counter %s" % counterNumber, 'state' : "%s" % counter, 'value' : "%s" % counter}
        infoDict['chType'] = ("counter")
        
        return infoDict

    def _appendExtraDataToScanResults(self, dev, results):
        if str(dev.serialNumber) in self.loggingThreads:
            headers = self.loggingThreads[str(dev.serialNumber)].headers
        else:
            headers = []
            
        for result in results:
            result['devType'] = dev.devType
            if "disabled" not in result:
                result['disabled'] = False
            
            if result['connection'] in headers:
                result['logging'] = True
            else:
                result['logging'] = False
                
        return results

    def ue9Scan(self, dev):
        results = list()
        
        feedbackResults = dev.feedback(AINMask = 0xef, AIN14ChannelNumber = dev.AIN14ChannelNumber, AIN15ChannelNumber = dev.AIN15ChannelNumber, Resolution = dev.Resolution, SettlingTime = dev.SettlingTime, AIN1_0_BipGain = dev.AIN1_0_BipGain, AIN3_2_BipGain = dev.AIN3_2_BipGain, AIN5_4_BipGain  = dev.AIN5_4_BipGain, AIN7_6_BipGain = dev.AIN7_6_BipGain, AIN9_8_BipGain = dev.AIN9_8_BipGain, AIN11_10_BipGain = dev.AIN11_10_BipGain, AIN13_12_BipGain = dev.AIN13_12_BipGain)
        
        for i in range(14):
            c = "AIN%s" % i
            v = feedbackResults[c]
            results.append({'connection' : c, 'state' : FLOAT_FORMAT % v, 'value' : FLOAT_FORMAT % v, 'chType' : ANALOG_TYPE, 'connectionNumber' : i})
            
        dirs = feedbackResults["FIODir"]
        states = feedbackResults["FIOState"]
        for i in range(8):
            f = FIO(i+14, label = "FIO%s" % i)
            d = (dirs >> i) & 1
            s = (states >> i) & 1
            
            results.append(f.parseFioResults(d, s))
            
        dirs = feedbackResults["EIODir"]
        states = feedbackResults["EIOState"]
        for i in range(8):
            f = FIO(i+14+8, label = "EIO%s" % i)
            d = (dirs >> i) & 1
            s = (states >> i) & 1
            
            results.append(f.parseFioResults(d, s))
            
        dirs = feedbackResults["CIODir"]
        states = feedbackResults["CIOState"]
        for i in range(4):
            f = FIO(i+14+16, label = "CIO%s" % i)
            d = (dirs >> i) & 1
            s = (states >> i) & 1
            
            results.append(f.parseFioResults(d, s))
            
        dirs = feedbackResults["MIODir"]
        states = feedbackResults["MIOState"]
        for i in range(3):
            f = FIO(i+34, label = "MIO%s" % i)
            d = (dirs >> i) & 1
            s = (states >> i) & 1
            
            results.append(f.parseFioResults(d, s))
            
        
        # Counter 0
        counter = feedbackResults["Counter0"]
        results.append({'connection' : "Counter 0", 'state' : "%s" % counter, 'value' : "%s" % counter, "chType" : "counter"})
        
        # Counter 1
        counter = feedbackResults["Counter1"]
        results.append({'connection' : "Counter 1", 'state' : "%s" % counter, 'value' : "%s" % counter, "chType" : "counter"})
        
        for i, l in enumerate(('A', 'B', 'C')):
            timer = feedbackResults["Timer%s" % l]
            results.append({'connection' : "Timer %s" % i, 'state' : "%s" % timer, 'value' : "%s" % timer, "chType" : "timer"})
        
        for register, label in DAC_DICT.items():
            dacState = dev.readRegister(register)
            results.append({'connection' : label, 'connectionNumber' : register, 'state' : FLOAT_FORMAT % dacState, 'value' : FLOAT_FORMAT % dacState})
        
        results.append(internalTempDict(dev.readRegister(266)))
        
        return dev.serialNumber, self._appendExtraDataToScanResults(dev, results)

    def u3Scan(self, dev):
        fioAnalog = dev.readRegister(50590)
        eioAnalog = dev.readRegister(50591)
        
        results = list()
        
        rawResponse = dev.getFeedback(dev.fioFeedbackCommands)
        for i, bits in enumerate(rawResponse):
            fio = dev.fioList[i]
            
            if fio.chType == ANALOG_TYPE:
                isLowVoltage = True
                if dev.deviceName.endswith("HV") and i < 4:
                    isLowVoltage = False
                
                isSingleEnded = True
                isSpecialChannel = False
                if fio.negChannel == 32:
                    isSpecialChannel = True
                elif fio.negChannel != 31:
                    isSingleEnded = False
                    
                value = dev.binaryToCalibratedAnalogVoltage(bits, isLowVoltage, isSingleEnded, isSpecialChannel, i)
                results.append( fio.parseAinResults(value) )
            elif fio.chType == DIGITAL_IN_TYPE:
                #value = bits["%ss" % (fio.label[:3])]
                #value = (value >> int(fio.label[3:])) & 1
                results.append( fio.parseFioResults(0, bits) )
            else:
                #value = bits["%ss" % (fio.label[:3])]
                #value = (value >> int(fio.label[3:])) & 1
                results.append( fio.parseFioResults(1, bits) )
        
        ioResults = dev.configIO()
        for i in range(ioResults['NumberOfTimersEnabled']):
            results.append( self.readTimer(dev, i) )
            
        if ioResults['EnableCounter0']:
            results.append( self.readCounter(dev, 0) )
            
        if ioResults['EnableCounter1']:
            results.append( self.readCounter(dev, 1) )

        for register, label in DAC_DICT.items():
            dacState = dev.readRegister(register)
            results.append({'connection' : label, 'connectionNumber' : register, 'state' : FLOAT_FORMAT % dacState, 'value' : FLOAT_FORMAT % dacState})
        
        results.append(internalTempDict(dev.readRegister(60)))
        
        return dev.serialNumber, self._appendExtraDataToScanResults(dev, results)

    def u6Scan(self, dev):
        results = list()
        
        if dev.timerCounterCache is None:
            self.readTimerCounterConfig(dev)
        
        analogInputs = dev.getFeedback( dev.analogCommandList )
        
        for i, value in enumerate(analogInputs):
            fio = dev.fioList[i]
            v = dev.binaryToCalibratedAnalogVoltage(fio.gainIndex, value)
            
            results.append(fio.parseAinResults(v))
        
        digitalDirections, digitalStates = dev.getFeedback( dev.digitalCommandList )
        
        offset = dev.timerCounterCache['offset']
        totalTaken = 0
        labels = []
        
        timers = self._convertTimerSettings(dev.timerCounterCache, onlyEnabled = True)
        totalTaken += len(timers)
        for i in range(totalTaken):
            labels.append("Timer%i" % i)
        
        if dev.timerCounterCache['counter0Enabled']:
            labels.append("Counter0")
            totalTaken += 1
            
        if dev.timerCounterCache['counter1Enabled']:
            labels.append("Counter1")
            totalTaken += 1
        
        taken = range(0+offset, totalTaken+offset)
        
        for i in range(dev.numberOfDigitalIOs):
            fio = dev.fioList[ i + dev.numberOfAnalogIn ]
            
            direction = ((digitalDirections[fio.label[:3]]) >> int(fio.label[3:])) & 1
            state = ((digitalStates[fio.label[:3]]) >> int(fio.label[3:])) & 1
            
            dioDict = fio.parseFioResults(direction, state)
            
            if i in taken:
                dioDict['connection'] = labels[taken.index(i)]
                dioDict['disabled'] = True
                dioDict['chType'] = "internalTemp"
                
                if dioDict['connection'].startswith("Timer"):
                    t = self.readTimer(dev, int(dioDict['connection'][-1]))
                    dioDict.update(t)
                elif dioDict['connection'].startswith("Counter"):
                    c = self.readCounter(dev, int(dioDict['connection'][-1]))
                    dioDict.update(c)
            
            dioDict['connectionNumber'] = i + dev.numberOfAnalogIn
            
            results.append( dioDict )
        
        for register, label in DAC_DICT.items():
            dacState = dev.readRegister(register)
            results.append({'connection' : label, 'connectionNumber' : register, 'state' : FLOAT_FORMAT % dacState, 'value' : FLOAT_FORMAT % dacState})
        
        results.append(internalTempDict(dev.readRegister(28)))
        
        return dev.serialNumber, self._appendExtraDataToScanResults(dev, results)

    def listAll(self):
        devices = dict()
        for dev in self.devices.values():
            name = dev.getName()
            devices[str(dev.serialNumber)] = name
        
        return devices
        
    def details(self, serial):
        dev = self.devices[serial]
        
        return deviceAsDict(dev)
        

    def readTimerCounterConfig(self, serial):
        if isinstance(serial, str):
            dev = self.getDevice(serial)
        else:
            dev = serial
        returnDict = dict()
         
        TYPE_TO_NUM_TIMERS_MAPPING = { '3' : 2, '6' : 4, '9' : 6 }
        returnDict['totalTimers'] = TYPE_TO_NUM_TIMERS_MAPPING[str(dev.devType)]
        for i in range(returnDict['totalTimers']):
            returnDict["timer%iEnabled" % i] = False
            returnDict["timer%iMode" % i] = 10
            returnDict["timer%iValue" % i] = 0
        
        tcb, divisor = dev.readRegister(7000, numReg = 4)
        returnDict['timerClockBase'] = tcb
        returnDict['timerClockDivisor'] = divisor
        
        counter = dev.readRegister(50502)
        counter0Enabled = bool(counter & 1)
        counter1Enabled = bool((counter >> 1) & 1)
        returnDict['counter0Enabled'] = counter0Enabled
        returnDict['counter1Enabled'] = counter1Enabled
        
        offset = dev.readRegister(50500)
        returnDict['offset'] = offset
        
        numTimers = dev.readRegister(50501)
        returnDict['numTimers'] = offset
        
        for i in range(numTimers):
            mode, value = dev.readRegister(7100 + 2*i, format = ">HH", numReg = 2)
            returnDict["timer%iEnabled" % i] = True
            returnDict["timer%iMode" % i] = mode
            returnDict["timer%iValue" % i] = value
        
        dev.timerCounterCache = returnDict
        
        return returnDict
        
    def _convertTimerSettings(self, timerSettings, onlyEnabled = False):
        timers = []
        print "timerSettings =", timerSettings
        for i in range(6):
            if "timer%iEnabled" % i in timerSettings:
                print "timer%iEnabled found." % i
                if onlyEnabled and timerSettings["timer%iEnabled" % i]:
                    timers.append({"enabled" : int(timerSettings["timer%iEnabled" % i]), "mode" : int(timerSettings["timer%iMode" % i]), "value" : int(timerSettings["timer%iValue" % i])})
                elif not onlyEnabled:
                    print "timer%i appended." % i
                    timers.append({"enabled" : int(timerSettings["timer%iEnabled" % i]), "mode" : int(timerSettings["timer%iMode" % i]), "value" : int(timerSettings["timer%iValue" % i])})
            else:
                break
        return timers
        
    def updateTimerCounterConfig(self, serial, timerClockBase, timerClockDivisor, pinOffset, counter0Enable, counter1Enable, timerSettings):
        dev = self.getDevice(serial)
        
        currentSettings = dev.timerCounterCache
        
        if timerClockBase != currentSettings['timerClockBase'] or timerClockDivisor != currentSettings['timerClockDivisor']:
            self.setupClock(dev, timerClockBase, timerClockDivisor)
            currentSettings['timerClockBase'] = timerClockBase
            currentSettings['timerClockDivisor'] = timerClockDivisor
        
        print "Old timers:"
        oldTimers = self._convertTimerSettings(currentSettings)
        print "New Timers"
        newTimers = self._convertTimerSettings(timerSettings)
        if pinOffset != currentSettings['offset'] or oldTimers != newTimers:
            self.setupTimers(dev, newTimers, pinOffset)
            
        if counter0Enable and currentSettings['timerClockDivisor'] > 2:
            # Raise an error, this is an invalid configuration
            raise Exception("When a clock with a divisor is used, Counter0 is unavailable.")
            
        if counter0Enable != currentSettings['counter0Enabled'] or counter1Enable != currentSettings['counter1Enabled']:
            self.setupCounter(dev, bool(counter0Enable), bool(counter1Enable))
            currentSettings['counter0Enabled'] = bool(counter0Enable)
            currentSettings['counter1Enabled'] = bool(counter1Enable)
        
    def setupClock(self, dev, timerClockBase = 0, divisor = 0):       
        dev.writeRegister(7000, timerClockBase)
        dev.writeRegister(7002, divisor)
        
    def setupCounter(self, dev, enableCounter0 = False, enableCounter1 = False):        
        value = (int(enableCounter1) << 1) + int(enableCounter0)
        
        dev.writeRegister(50502, value)
    
    def setupTimers(self, dev, timers = [], offset = 0):
        print "setupTimers:"
        print "timers =", timers
        print "offset =", offset
        numTimers = len(timers)
        
        dev.writeRegister(50500, offset)
        dev.writeRegister(50501, numTimers)
        
        for i, timer in enumerate(timers):
            dev.writeRegister(7100 + 2*i, [timer['mode'], timer['value']])
        
    
    def setFioState(self, serial, fioNumber, state):
        dev = self.getDevice(serial)
            
        dev.writeRegister(6000 + int(fioNumber), int(state))
        
        if int(state) == 0:
            return "Low"
        else:
            return "High"
            
    def setName(self, serial, name):
        dev = self.getDevice(serial)
            
        dev.setName(name)
        
        return dev.serialNumber, name
        
    def setDefaults(self, serial):
        dev = self.getDevice(serial)
        
        dev.setDefaults()
        
        return "Ok"
        
        
    def callDeviceFunction(self, serial, funcName, pargs, kwargs):
        """ Allows you to call any function a device offers.
            serial = serial number of the device
            funcName = all lowercase version of the function name
            pargs = a list of positional arguments
            kwargs = a dict of keyword
        """
        dev = self.getDevice(serial)
        
        pargs = list(pargs)
        for i in range(len(pargs)):
            pargs[i] = autoConvert(pargs[i])
            
        for key, value in kwargs.items():
            kwargs[key] = autoConvert(value)
        
        if dev.devType == 3:
            classDict = u3Dict
        elif dev.devType == 6:
            classDict = u6Dict
        elif dev.devType == 9:
            classDict = ue9Dict
        
        return deviceAsDict(dev), dev.__getattribute__(classDict[funcName])(*pargs, **kwargs)

class DevicesPage(object):
    """ A class for handling all things /devices/
    """
    def __init__(self, dm):
        self.dm = dm
    
    def header(self):
        return "<html><body>"
    
    def footer(self):
        return "</body></html>"

    @exposeJsonFunction
    def index(self):
        """ Handles /devices/, returns a JSON list of all known devices.
        """
        self.dm.updateDeviceDict()
        
        devices = self.dm.listAll()
        
        t = serve_file2("templates/devices.tmpl")
        t.devices = devices

        t2 = serve_file2("templates/device-summary-list.tmpl")
        t2.devices = [ deviceAsDict(d) for d in  self.dm.devices.values() ]
        
        devices['html'] = t.respond()
        devices['htmlSummaryList'] = t2.respond()
        
        return devices
        
    @exposeJsonFunction
    def default(self, serial, cmd = None, *pargs, **kwargs):
        """ Handles URLs like: /devices/<serial number>/
            if the URL is just /devices/<serial number>/ it returns the
            "details" of that device.
            
            if the URL is more like /devices/<serial number>/<command>, it runs
            that command on the device.
        """
        if cmd is None:
            returnDict = self.dm.details(serial)
            
            t = serve_file2("templates/device-details.tmpl")
            t.device = returnDict
            
            tScanning = serve_file2("templates/device-scanning.tmpl")
            tScanning.device = returnDict
            
            returnDict['html'] = t.respond()
            
            returnDict['htmlScanning'] = tScanning.respond()
            
            return returnDict
        else:
            cmd = cmd.lower()
            return { "result" : self.dm.callDeviceFunction(serial, cmd, pargs, kwargs)[1] }

    @exposeRawFunction
    def timerCounterConfig(self, serial = None, message = ""):
        devType = self.dm.getDevice(serial).devType
        currentConfig = self.dm.readTimerCounterConfig(serial.encode("ascii", "replace"))
        
        print currentConfig
        
        t = serve_file2("templates/device-configureTimerCounter.tmpl")
        t.message = message
        t.devType = devType
        t.updateUrl = "/devices/updateTimerCounterConfig/%s" % serial
        t.currentConfig = currentConfig
        
        return t.respond()
        
    @exposeRawFunction
    def updateTimerCounterConfig(self, serial, timerClockBase = 0, timerClockDivisor = 1, pinOffset = 0, counter0Enable = 0, counter1Enable = 0,  **timerSettings):
        print "got: serial =", serial
        print "timerClockBase =", timerClockBase
        print "timerClockDivisor =", timerClockDivisor
        print "pinOffset =", pinOffset
        print "counter0Enable =", counter0Enable
        print "counter1Enable =", counter1Enable
        print "timerSettings =", timerSettings
        
        self.dm.updateTimerCounterConfig(serial, int(timerClockBase), int(timerClockDivisor), int(pinOffset), int(counter0Enable), int(counter1Enable), timerSettings)
        return "Ok."

    def renderU3Templates(self, inputConnection):
        if inputConnection['fioNumber'] < 4 and inputConnection['device']['productName'].endswith("HV"):
            t = serve_file2("templates/u3-hv-analog-connection-dialog.tmpl")
            t.longSettling = bool(inputConnection['gainIndex'])
            t.quickSample = bool(inputConnection['settlingFactor'])
            return t.respond()
        else:
            t = serve_file2("templates/u3-connection-dialog.tmpl")
            t.longSettling = bool(inputConnection['gainIndex'])
            t.quickSample = bool(inputConnection['settlingFactor'])
            t.isHv = inputConnection['device']['productName'].endswith("HV")
            return t.respond()

    def renderU6Templates(self, inputConnection):
        if inputConnection['chType'] == ANALOG_TYPE:
            t = serve_file2("templates/u6-analog-connection-dialog.tmpl")
            t.inputConnection = inputConnection['label']
            t.isPro = inputConnection['device']['productName'].endswith("Pro")
            t.isEvenChannel = not bool(inputConnection['fioNumber'] % 2)
            t.inputConnectionPair = "AIN%s" % (inputConnection['fioNumber']+1)
            return t.respond()
        else:
            t = serve_file2("templates/u6-digital-connection-dialog.tmpl")
            return t.respond()

    def renderUE9Templates(self, inputConnection):
        if inputConnection['chType'] == ANALOG_TYPE:
            t = serve_file2("templates/ue9-analog-connection-dialog.tmpl")
            t.inputConnection = inputConnection['label']
            t.isPro = inputConnection['device']['productName'].endswith("Pro")
            return t.respond()
        else:
            t = serve_file2("templates/ue9-digital-connection-dialog.tmpl")
            return t.respond()

    @exposeJsonFunction
    def inputInfo(self, serial = None, inputNumber = 0):
        """ Returns a JSON of the current state of an input.
        """
        inputConnection = self.dm.getFioInfo(serial, int(inputNumber))
        
        if inputConnection['chType'] == "DAC":
            t = serve_file2("templates/dac.tmpl")
            t.dac = inputConnection
            inputConnection['html'] = t.respond()
        elif inputConnection['device']['devType'] == 3:
            inputConnection['html'] = self.renderU3Templates(inputConnection)
        elif inputConnection['device']['devType'] == 6:
            inputConnection['html'] = self.renderU6Templates(inputConnection)
        elif inputConnection['device']['devType'] == 9:
            inputConnection['html'] = self.renderUE9Templates(inputConnection)

        
        return inputConnection
        
    @exposeRawFunction
    def support(self, serial):
        dev = self.dm.getDevice(serial)
        
        print "Headers:", cherrypy.request.headers
        
        t = serve_file2("templates/support.tmpl")
        
        t.device = deviceAsDict(dev)
        
        if dev.devType == 3:
            t.supportUrl = "http://labjack.com/support/u3"
            t.supportUsersGuideUrl = "http://labjack.com/support/u3/users-guide"
        elif dev.devType == 6:
            t.supportUrl = "http://labjack.com/support/u6"
            t.supportUsersGuideUrl = "http://labjack.com/support/u6/users-guide"
        elif dev.devType == 9:
            t.supportUrl = "http://labjack.com/support/ue9"
            t.supportUsersGuideUrl = "http://labjack.com/support/ue9/users-guide"
        
        # Call the exportConfig function on the device.
        devDict, result = self.dm.callDeviceFunction(serial, "exportconfig", [], {})
        
        # exportConfig returns a ConfigParser object. We need it as a string.
        fakefile = StringIO.StringIO()
        result.write(fakefile)
        
        t.config = fakefile.getvalue()
        
        t.groundedVersion = CLOUDDOT_GROUNDED_VERSION
        #t.ljpVersion = LabJackPython.LABJACKPYTHON_VERSION
        t.ljpVersion = "5-18-2010"
        t.usbOrLJSocket = self.dm.usbOverride
        
        userAgent = cherrypy.request.headers['User-Agent']
        os = userAgent.split("(")[1]
        os = os.split(")")[0]
        os = os.split(";")[2].strip()
        t.os = os
        t.isWindows = (LabJackPython.os.name == 'nt')
        t.driverVersion = LabJackPython.GetDriverVersion()
        t.userAgent = userAgent
        
        return t.respond()

    @exposeJsonFunction
    def updateInputInfo(self, serial, inputNumber, chType, negChannel = None, state = None, gainIndex = None, resolutionIndex = None, settlingFactor = None ):
        """ For configuring an input.
            serial = serial number of device
            inputNumber = the row number of that input
            chType = ( analogIn, digitalIn, digitalOut )
            negChannel = the negative channel, only matters for analogIn type
            state = 1 for high, 0 for low. Only matters for digitalOut
            gainIndex = the gain index for the U6/UE9, LongSettling for U3.
            resolutionIndex = the resolution for U6/UE9, nothing on U3.
            settlingFactor = for settling time on U6/UE9, QuickSample on U3. 
        """
        if negChannel and int(negChannel) < 30 and self.dm.getDevice(serial).devType == 3:
            print "Setting %s to analog." % negChannel
            inputConnection = FIO( int(negChannel), "FIO%s" % negChannel, chType, state, 31 )
            self.dm.updateFio(serial, inputConnection)
        
            
        # Make a temp FIO with the new settings.
        inputConnection = FIO( int(inputNumber), "FIO%s" % inputNumber, chType, state, negChannel )
        if gainIndex is not None:
            inputConnection.gainIndex = int(gainIndex)
        if resolutionIndex is not None:
            inputConnection.resolutionIndex = int(resolutionIndex)
        if settlingFactor is not None:
            inputConnection.settlingFactor = int(settlingFactor)
        
        # Tells the device manager to update the input
        self.dm.updateFio(serial, inputConnection)
        
        return { "result" : 0 }
    
    @exposeRawFunction
    def toggleDigitalOutput(self, serial, inputNumber):
        """ Toggle a digital output line.
        """
        inputConnection = self.dm.getFioInfo(serial, int(inputNumber))
        chType = inputConnection["chType"]
        state = inputConnection["state"]
        if chType == "digitalOut":
            state = not state
            newInputConnection = FIO( int(inputNumber), "FIO%s" % inputNumber, chType, state )
            self.dm.updateFio(serial, newInputConnection)
            return self.scan(serial, noCache = True)

    @exposeJsonFunction
    def scan(self, serial = None, noCache = False):
        """ Scan reads all the inputs and such off the device. Renders the
            result as a JSON.
        """
        
        print "Scan: serial = %s" % serial
        serialNumber, results = self.dm.scan(serial, noCache)
        
        return results

    @exposeJsonFunction
    def connectToCloudDot(self, serial = None):
        print "Connecting %s to CloudDot." % serial
        
        self.dm.connectDeviceToCloudDot(serial)
        
        return {'result' : "connected"}
    

    # ---------------- Deprecated ----------------
    @exposeRawFunction
    def setFioState(self, serial = None, fioNumber = 0, state = 1):
        result = self.dm.setFioState(serial, fioNumber, state)
        yield self.header()
        yield "<p>FIO%s has been set to output %s</p>" % (fioNumber, result)
        yield self.footer()
    
    @exposeRawFunction
    def setName(self, serial = None, name = None):
        yield self.header()
        
        if name is not None:
            serialNumber, name = self.dm.setName(serial, name)
            yield "%s's name set to %s" % (serialNumber, name)
        
        yield self.footer()
    
    # ---------------- End Deprecated ----------------
    
    @exposeJsonFunction
    def setDefaults(self, serial = None):
        """ Makes the calls to set the current state of the device as the
            power-up default.
        """
        results = { 'state' : self.dm.setDefaults(serial) }
        
        return results
    
    @exposeRawFunction
    def importConfigFromFile(self, myFile, serial):
        """ Allows people to upload a config file which gets loaded onto 
            the device.
        """
        
        # loadConfig takes a ConfigParser object, so we need to make one.
        parserobj = ConfigParser.SafeConfigParser()
        parserobj.readfp(myFile.file)
        
        # Have to device load in the configuration.
        devDict, result = self.dm.callDeviceFunction(serial, "loadconfig", [parserobj], {})
        
        # Rebuild the FioList because settings could have changed.
        self.dm.remakeFioList(serial)
        
        # Redirect them away because there's nothing to be rendered.
        # TODO: Return JSON for Mike C.
        raise cherrypy.HTTPRedirect("/")


if IS_FROZEN:
    # All of this depends on us being 'frozen' in an executable.
    ZIP_FILE = zipfile.ZipFile(os.path.abspath(sys.executable), 'r')    

    def renderFromLocalFile(filepath):
        # Figure out the content type from the file extension.
        ext = ""
        i = filepath.rfind('.')
        if i != -1:
            ext = filepath[i:].lower()
        content_type = mimetypes.types_map.get(ext, None)
        
        # Set or remove the content type
        if content_type is not None:
            cherrypy.response.headers['Content-Type'] = content_type
        else:
            cherrypy.response.headers.pop('Content-Type')
        
        try:
            # Open up the file and read it into the response body
            f = open(filepath)
            cherrypy.response.body = "".join(f.readlines())
            f.close()
            print "Body set, returning true"
            
            # Tell CherryPy we got this one
            return True
        except Exception, e: 
            print "Got Exception in renderFromLocalFile: %s" % e
            
            # Tell CherryPy we didn't render and it should try.
            return False


    def renderFromZipFile():
        """ renderFromZipFile handles pulling static files out of the ZipFile
            and rendering them like nothing happened. 
        """
        print "renderFromZipFile got run: %s" % cherrypy.request.path_info
        
        # Get rid of the leading "/"
        filepath = cherrypy.request.path_info[1:]
        print "filepath: %s" % filepath
        
        # Check if the file being requested is in the ZipFile
        if filepath not in ZIP_FILE.namelist():
            print "%s not in name list." % filepath
            
            # Check if the file is local
            localAbsPath = os.path.join(current_dir,filepath)
            if filepath.startswith("logfiles") and os.path.exists(localAbsPath):
                return renderFromLocalFile(localAbsPath)
            else:
                # If it isn't then we pass the responsibility on.
                return False
        
        # Figure out the content type from the file extension.
        ext = ""
        i = filepath.rfind('.')
        if i != -1:
            ext = filepath[i:].lower()
        content_type = mimetypes.types_map.get(ext, None)
        
        # Set or remove the content type
        if content_type is not None:
            cherrypy.response.headers['Content-Type'] = content_type
        else:
            cherrypy.response.headers.pop('Content-Type')
        
        try:
            # Open up the file and read it into the response body
            f = ZIP_FILE.open(filepath)
            cherrypy.response.body = "".join(f.readlines())
            f.close()
            print "Body set, returning true"
            
            # Tell CherryPy we got this one
            return True
        except Exception, e: 
            print "Got Exception in renderFromZipFile: %s" % e
            
            # Tell CherryPy we didn't render and it should try.
            return False
    
    cherrypy.tools.renderFromZipFile = cherrypy._cptools.HandlerTool(renderFromZipFile)

def serve_file2(path):
    """ A slightly modified version of serve_file, to handle the case where
        we are running inside an executable.
    """
    if IS_FROZEN:
        f = ZIP_FILE.open(path)
        body = "".join(f.readlines())
        f.close()
        if path.endswith(".tmpl"):
            return Template(source=body)
        else:
            return body
    else:
        if path.endswith(".tmpl"):
            return Template(file=os.path.join(current_dir,path))
        else:
            return serve_file(os.path.join(current_dir,path))

class UsersPage:
    """ A class for handling all things /users/
    """
    def __init__(self, dm):
        self.dm = dm
    
    def header(self):
        return "<html><body>"
    
    def footer(self):
        return "</body></html>"

    @exposeRawFunction
    def index(self):
        """ Handles /users/, returns a JSON list of all known devices.
        """
        # Tell people (firefox) not to cash this page. 
        cherrypy.response.headers['Cache-Control'] = "no-cache"
        
        return serve_file2("html/user.html")
    
    @exposeJsonFunction
    def fetch(self):
        print "returning user info"
        
        return {'username' : self.dm.username, 'apikey' : self.dm.apikey}
    
    @exposeJsonFunction
    def check(self, label = None, username = None, apikey = None):
        """
        Checks for valid username and apikey
        """
        print "Check called..."
        print "label = %s, username = %s, apikey = %s" % (label, username, apikey)
        if label is None:
            return False
        elif label == "username":
            devurl = "http://cloudapi.labjack.com/%s/devices.json" % username
            h = httplib2.Http()
            resp, content = h.request(devurl, "GET")
            if resp['status'] != '200':
                return {'username' : 1}
            else:
                return {'username' : 0}
        elif label == "apikey":
            data = { 'userName' : username, "apiKey" : apikey}
            devurl = "http://cloudapi.labjack.com/%s/info.json?%s" % (username, urlencode(data))
            h = httplib2.Http()
            resp, content = h.request(devurl, "GET")
            if resp['status'] == '401':
                return {'username' : 0, 'apikey' : 1}
            elif resp['status'] != '200':
                return {'username' : 1, 'apikey' : 1}
            else:
                return {'username' : 0, 'apikey' : 0}
    
    @exposeRawFunction
    def update(self, username = None, apikey = None):
        """ Updates the saved username and API Key.
        """
        print "Update called: Username = %s, apikey = %s" % (username, apikey)
        
        self.dm.username = username
        self.dm.apikey = apikey
        
        raise cherrypy.HTTPRedirect("/users/")

class ConfigPage(object):
    """ A class for handling all things /config/
    """
    def __init__(self, dm):
        self.dm = dm
    
    def getConfigFiles(self, serial):
        l = []
        logfilesDir = os.path.join(current_dir,"configfiles/%s" % serial)
        try:
            files = sorted(os.listdir(logfilesDir), reverse = True, key = lambda x: os.stat(os.path.join(logfilesDir,x)).st_ctime)
        except OSError:
            return []
        for filename in files:
            newName = replaceUnderscoresWithColons(filename)
                     
            size = os.stat(os.path.join(logfilesDir,filename)).st_size
            size = float(size)/1024
            sizeStr = "%.2f KB" % size
            
            aLog = dict(name = newName, url= "/configfiles/%s/%s" % (serial, filename), loadurl = "/config/load/%s/%s" % (serial, filename), removeurl = "/config/remove/%s/%s" % (serial, filename), size = sizeStr)
            l.append(aLog)
        return l
        
    def getBasicConfigFiles(self, serial):
        l = []
        dev = self.dm.getDevice(serial)
        logfilesDir = os.path.join(current_dir,"configfiles/%s" % dev.deviceName)
        
        if not os.path.isdir(logfilesDir):
            os.mkdir(logfilesDir)
        
        files = sorted(os.listdir(logfilesDir), reverse = True, key = lambda x: os.stat(os.path.join(logfilesDir,x)).st_ctime)
        for filename in files:
            newName = filename
                     
            size = os.stat(os.path.join(logfilesDir,filename)).st_size
            size = float(size)/1024
            sizeStr = "%.2f KB" % size
            
            aLog = dict(name = newName, url= "/configfiles/%s/%s" % (dev.deviceName, filename), loadurl = "/config/load/%s/%s" % (serial, filename), size = sizeStr)
            l.append(aLog)
        return l

    @exposeRawFunction
    def filelist(self, serial):
        t = serve_file2("templates/config-file-list.tmpl")
        t.configfiles = self.getConfigFiles(serial)
        t.basicconfigfiles = self.getBasicConfigFiles(serial)
        
        return t.respond()
        
    @exposeRawFunction    
    def exportConfigToFile(self, serial):
        """ Allows people to download the configuration of their LabJack.
        """
        
        # Save current config as power-up default
        devDict, result = self.dm.callDeviceFunction(serial, "setdefaults", [], {})
        
        # Call the exportConfig function on the device.
        devDict, result = self.dm.callDeviceFunction(serial, "exportconfig", [], {})
        
        filename = "%%Y-%%m-%%d %%H__%%M %s conf.txt" % (sanitize(devDict['name']),)
        filename = datetime.now().strftime(filename)
        dirpath = "./configfiles/%s" % serial
        if not os.path.isdir(dirpath):
            os.mkdir(dirpath)
        filepath = "%s/%s" % (dirpath, filename)
        configfile = file(filepath, "w")
        result.write(configfile)
        configfile.close()
        
        return "Ok"
        
        # exportConfig returns a ConfigParser object. We need it as a string.
        #fakefile = StringIO.StringIO()
        #result.write(fakefile)
        
        # Set the headers
        #cherrypy.response.headers['Content-Type'] = "application/x-download"
        #cd = '%s; filename="%s"' % ("attachment", "labjack-%s-%s-conf.txt" % (devDict['productName'], devDict['serial']) )
        #cherrypy.response.headers["Content-Disposition"] = cd
        
        # Send the data
        #return fakefile.getvalue()
    
    @exposeRawFunction
    def load(self, serial, filename):
        configfileDir = os.path.join(current_dir,"configfiles/%s" % serial)
        path = os.path.join(configfileDir, filename)
        
        dev = self.dm.getDevice(serial)
        configfileDir = os.path.join(current_dir,"configfiles/%s" % dev.deviceName)
        basicpath = os.path.join(configfileDir, filename)
        
        try:
            try:
                configFile = file(path, 'r')
            except IOError:
                configFile = file(basicpath, 'r')
            
            # loadConfig takes a ConfigParser object, so we need to make one.
            parserobj = ConfigParser.SafeConfigParser()
            parserobj.readfp(configFile)
            
            # Have to device load in the configuration.
            devDict, result = self.dm.callDeviceFunction(serial, "loadconfig", [parserobj], {})
            
            # Save current config as power-up default
            devDict, result = self.dm.callDeviceFunction(serial, "setdefaults", [], {})
            
            # Rebuild the FioList because settings could have changed.
            self.dm.remakeFioList(serial)
            m = "File %s has been successfully loaded." % replaceUnderscoresWithColons(filename)
        except OSError:
            m = "Couldn't find a file named %s." % replaceUnderscoresWithColons(filename)
            
        #TODO: Do something else here. Maybe some sort of response for AJAX?
        return "Ok. %s" % m
    
    @exposeRawFunction
    def remove(self, serial, filename):
        logfileDir = os.path.join(current_dir,"configfiles/%s" % serial)
        path = os.path.join(logfileDir, filename)
        
        try:
            os.remove(path)
            m = "File %s has been successfully deleted." % replaceUnderscoresWithColons(filename)
        except OSError:
            m = "Couldn't find a file named %s." % replaceUnderscoresWithColons(filename)
            
        #TODO: Do something else here. Maybe some sort of response for AJAX?
        return "Ok."
        

class LoggingPage(object):
    """ A class for handling all things /logs/
    """
    def __init__(self, dm):
        self.dm = dm
        
        self.gd_client = None
        self.parser = ConfigParser.SafeConfigParser()
    
    def header(self):
        return "<html><body>"
    
    def footer(self):
        return "</body></html>"
    
    def loadSessionToken(self):
        self.parser.read(CLOUDDOT_GROUNDED_CONF)
        if self.parser.has_section("googledocs") and self.parser.has_option("googledocs", "session_token"):
            token = self.parser.get("googledocs", "session_token")
        
            print "token = %s" % token
        else:
            return None
        
        if token and len(token) > 0:
            return token
        else:
            return None
    
    @exposeRawFunction   
    def savetoken(self, filename, *args, **kwargs):
        singleUseToken = kwargs['token']
        self.gd_client.SetAuthSubToken(singleUseToken)
        self.gd_client.UpgradeToSessionToken()
        sessionToken = self.gd_client.GetAuthSubToken()
        self.parser.set("googledocs", "session_token", str(sessionToken))
        with open(CLOUDDOT_GROUNDED_CONF, 'wb') as configfile:
            self.parser.write(configfile)

        raise cherrypy.HTTPRedirect("/logs/upload/%s" % filename)
    
    @exposeRawFunction
    def upload(self, filename):
        if self.gd_client is None:
            self.gd_client = gdata.docs.service.DocsService()
            token = self.loadSessionToken()
            if token is None:
                next = '%s/logs/savetoken/%s' % (cherrypy.request.base, filename)
                auth_sub_url = gdata.service.GenerateAuthSubRequestUrl(next, GOOGLE_DOCS_SCOPE, secure=False, session=True)
                raise cherrypy.HTTPRedirect(auth_sub_url)
            else:
                self.gd_client.SetAuthSubToken(token, scopes=[GOOGLE_DOCS_SCOPE])
        
        googleDocName = replaceUnderscoresWithColons(filename)
        
        csvPath = os.path.join(current_dir,"logfiles/%s" % filename)
        csvStringIO = StringIO.StringIO(file(csvPath).read())
        virtual_media_source = gdata.MediaSource(file_handle=csvStringIO, content_type='text/csv', content_length=len(csvStringIO.getvalue()))
        db_entry = self.gd_client.Upload(virtual_media_source, googleDocName)
        
        message = urlencode({ "message" : "File %s has been successfully uploaded to google docs." % replaceUnderscoresWithColons(filename)})
        raise cherrypy.HTTPRedirect("/logs?%s" % message)

    def getLogFiles(self):
        activeFiles = {}
        for thread in self.dm.loggingThreads.values():
            activeFiles["%s" % thread.filename] = thread.serial
        print "activeFiles:", activeFiles
    
        l = []
        logfilesDir = os.path.join(current_dir,"logfiles")
        files = sorted(os.listdir(logfilesDir), reverse = True, key = lambda x: os.stat(os.path.join(logfilesDir,x)).st_ctime)
        for filename in files:
            newName = replaceUnderscoresWithColons(filename)
            
            active = False
            stopurl = ""
            if filename in activeFiles:
                print "%s is active" % filename
                active = True
                stopurl = "/logs/stop?serial=%s" % activeFiles[filename]
            
            size = os.stat(os.path.join(logfilesDir,filename)).st_size
            size = float(size)/1024
            sizeStr = "%.2f KB" % size
            
            uploadEnable = True
            if size > 1024:
                uploadEnable = False
            
            aLog = dict(name = newName, url= "/logfiles/%s" % filename, uploadurl = "/logs/upload/%s" % filename, uploadEnable = uploadEnable, removeurl = "/logs/remove/%s" % filename, size = sizeStr, active = active, stopurl = stopurl)
            l.append(aLog)
        return l

    @exposeRawFunction
    def index(self, message = ""):
        """ Handles /logs/
        """
        # Tell people (firefox) not to cache this page. 
        cherrypy.response.headers['Cache-Control'] = "no-cache"

        t = serve_file2("templates/index.tmpl")
        
        tMainContent = serve_file2("templates/logfiles.tmpl")
        tMainContent.logfiles = self.getLogFiles()
        tMainContent.message = message
        tMainContent.includeWrapper = True
        
        t.mainContent = tMainContent.respond()
        t.currentPage = "logs"
        t.title = "Logs | LabJack CloudDot Grounded"

        return t.respond()
        
    @exposeRawFunction
    def logFileList(self):
        """ Just the list of files. Used for AJAX updating.
        """
        cherrypy.response.headers['Cache-Control'] = "no-cache"

        tFileList = serve_file2("templates/logfiles.tmpl")
        tFileList.logfiles = self.getLogFiles()
        tFileList.message = ""
        tFileList.includeWrapper = False
        
        return tFileList.respond()

    @exposeRawFunction
    def remove(self, filename):
        logfileDir = os.path.join(current_dir,"logfiles")
        path = os.path.join(logfileDir, filename)
        
        try:
            os.remove(path)
            m = "File %s has been successfully deleted." % replaceUnderscoresWithColons(filename)
        except OSError:
            m = "Couldn't find a file named %s." % replaceUnderscoresWithColons(filename)
            
        message = urlencode({ "message" : m})
        raise cherrypy.HTTPRedirect("/logs?%s" % message)
    
    @exposeRawFunction
    def test(self):
        cherrypy.response.headers['Cache-Control'] = "no-cache"
        
        t = serve_file2("templates/testlog.tmpl")
        
        devs = list()
        for d in self.dm.devices.values():
            devs.append({"name" : d.getName(), "serial" : d.serialNumber})
        
        t.devices = devs

        return t.respond()

    @exposeRawFunction
    def loggingSummary(self):
        summaries = self.dm.makeLoggingSummary()
        
        t = serve_file2("templates/logging-summaries.tmpl")
        t.summaries = summaries
        
        return t.respond()
    
    @exposeRawFunction
    def start(self, serial = None, headers = None):
        if serial is None:
            print "serial is null"
            return False
        else:
            if headers:
                headers = headers.split(",")
            self.dm.startDeviceLogging(serial, headers = headers)

    @exposeRawFunction    
    def stop(self, serial = None):
        if serial is None:
            print "serial is null"
            if cherrypy.request.headers.has_key("Referer"):
                raise cherrypy.HTTPRedirect("/logs?%s" % message)
            else:
                return "%s" % cherrypy.request.__dict__
        else:
            self.dm.stopDeviceLogging(serial)
            return self.loggingSummary()
            #if cherrypy.request.headers.has_key("Referer"):
            #    print "redirecting to", cherrypy.request.headers["Referer"]
            #    raise cherrypy.HTTPRedirect(cherrypy.request.headers["Referer"])
            #else:
            #    raise cherrypy.HTTPRedirect("/logs")
    

class RootPage:
    """ The RootPage class handles showing index.html. If we can't connect to
        LJSocket then it shows connect.html instead.
    """
    def __init__(self, dm):
        # Keep a copy of the device manager
        self.dm = dm
        
        # Adds the DevicesPage child which handles all the device communication
        self.devices = DevicesPage(dm)
        
        self.logs = LoggingPage(dm)
        self.config = ConfigPage(dm)
        
        self.users = UsersPage(dm)
    
    @exposeRawFunction
    def index(self):
        """ if we can talk to LJSocket, renders index.html. Otherwise, 
            it renders connect.html """
        
        # Tell people (firefox) not to cache this page. 
        cherrypy.response.headers['Cache-Control'] = "no-cache"
        
        #Check for IE
        userAgent = cherrypy.request.headers['User-Agent']
        if userAgent.lower().find("msie") != -1:
            return serve_file2("html/choose-better.html")
            
        
        if self.dm.connected:
            t = serve_file2("templates/index.tmpl")
            
            tMainContent = serve_file2("templates/devices-main-content.tmpl")
            t.mainContent = tMainContent.respond()
            t.currentPage = "devices"
            t.title = "LabJack CloudDot Grounded"
            
            return t.respond()
        else:
            return serve_file2("html/connect.html")
    
    @exposeRawFunction
    def retry(self, address = "localhost", port = "6000", usbOverride = ""):
        """ The retry endpoint is for trying to connect to LJSocket.
            No matter what happens it will redirect you to '/'.
        """
        self.dm.address = address
        self.dm.port = port
        self.dm.usbOverride = bool(usbOverride)
        try:
            self.dm.updateDeviceDict()
            self.dm.connected = True
        except Exception,e:
            print "Retry got an exception:", e
        
        raise cherrypy.HTTPRedirect("/")


def openWebBrowser(host = "localhost", port = 8080):
    """ openWebBrowser handles the opening of a webbrowser for people.
        Makes a special effort to open firefox on Windows.
    """
    url = "http://%s:%s" % (host, port)
    
    if LabJackPython.os.name == 'nt':
        try:
            webbrowser.register("firefox", webbrowser.Mozilla)
            ff = webbrowser.get("firefox")
            ff.open_new_tab(url)
        except Exception, e:
            print "Firefox failed to start, pray the default browser isn't IE."
            webbrowser.open_new_tab(url)
    else:
        webbrowser.open_new_tab(url)

def quickstartWithBrowserOpen(root=None, script_name="", config=None):
    """ Code exactly as it appears in cherrypy.quickstart() only with a call
        to open web Browser in between the start() and the block()
    """
    if config:
        cherrypy._global_conf_alias.update(config)
    
    cherrypy.tree.mount(root, script_name, config)
    
    if hasattr(cherrypy.engine, "signal_handler"):
        cherrypy.engine.signal_handler.subscribe()
    if hasattr(cherrypy.engine, "console_control_handler"):
        cherrypy.engine.console_control_handler.subscribe()
    
    cherrypy.engine.start()
    
    openWebBrowser("localhost", cherrypy._global_conf_alias['server.socket_port'])
    
    cherrypy.engine.block()


# Main:
if __name__ == '__main__':
    dm = DeviceManager()
    
    if not os.path.isdir("./logfiles"):
        os.mkdir("./logfiles")
        
    if not os.path.isdir("./configfiles"):
        os.mkdir("./configfiles")
    
    if not IS_FROZEN:
        # not frozen: in regular python interpreter
        current_dir = os.path.dirname(os.path.abspath(__file__))
        configfile = os.path.join(current_dir, "cherryred.conf")
    else:
        # py2exe:
        current_dir = os.path.dirname(os.path.abspath(sys.executable))
        configfile = ZIP_FILE.open("cherryred.conf")
    

    root = RootPage(dm)
    root._cp_config = {'tools.staticdir.root': current_dir, 'tools.renderFromZipFile.on': IS_FROZEN}
    quickstartWithBrowserOpen(root, config=configfile)
