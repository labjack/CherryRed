"""

Name: cherryred.py
Desc:

"""

# Imports
import cherrypy
import cherrypy.lib
from cherrypy.lib.static import serve_file
from Cheetah.Template import Template

from threading import Lock

import xmppconnection, logger
from fio import FIO

import os, os.path, zipfile

import json, httplib2
from urllib import urlencode

import sys, time

import cStringIO as StringIO, ConfigParser

import LabJackPython, u3, u6, ue9
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

def deviceAsDict(dev):
    """ Returns a dictionary representation of a device.
    """
    name = dev.getName()
    
    if dev.devType == 9:
        firmware = [dev.commFWVersion, dev.controlFWVersion]
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
        self.loggingThreads = dict()
        
        self.loggingThreadLock = Lock()
        
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
            loggingList.append({ "devName" : thread.name, "headers" : ", ".join(headers), "filename" : thread.filename, "serial" : serial, "logname" : replaceUnderscoresWithColons(thread.filename)})
        
        return loggingList
    
    def startDeviceLogging(self, serial, headers = None):
        d = self.getDevice(serial)
        returnValue = False
        
        try:
            self.loggingThreadLock.acquire()
            if str(d.serialNumber) not in self.loggingThreads:
                lt = logger.LoggingThread(self, d.serialNumber, d.getName(), headers)
                lt.start()
                self.loggingThreads[str(d.serialNumber)] = lt
                
                returnValue = True
            else:
                sn = str(d.serialNumber)
                if self.loggingThreads[sn].headers != headers:
                    lt = self.loggingThreads[sn]
                    lt.stop()
                    if headers:
                        lt = logger.LoggingThread(self, d.serialNumber, d.getName(), headers)
                        lt.start()
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
            
        for s, thread in self.loggingThreads.items():
            thread.stop()
    
    def getFioInfo(self, serial, inputNumber):
        dev = self.getDevice(serial)
        
        if inputNumber in DAC_DICT.keys():
            returnDict = { "state" : dev.readRegister(inputNumber), "label" : DAC_DICT[inputNumber], "connectionNumber" : inputNumber }
            t = serve_file2("templates/dac.tmpl")
            t.dac = returnDict
            returnDict['html'] = t.respond()
        else:
            returnDict = dev.fioList[inputNumber].asDict()
        
        # devType, productName
        returnDict['device'] = deviceAsDict(dev)
        
        return returnDict
        
    def updateFio(self, serial, inputConnection):
        dev = self.getDevice(serial)
        
        current = dev.fioList[ inputConnection.fioNumber ]
        current.transform(dev, inputConnection)
        
        if dev.devType == 6:
            remakeU6AnalogCommandList(dev)
    
    def remakeFioList(self, serial):
        dev = self.getDevice(serial)
        
        dev.fioList = self.makeU3FioList(dev)
        
        self.devices[str(dev.serialNumber)] = dev
    
    def remakeU6AnalogCommandList(dev):
        analogCommandList = list()
        for i in range(14):
            ain = dev.fioList[i]
            analogCommandList.append( u6.AIN24(i, ResolutionIndex = ain.resolutionIndex, GainIndex = ain.gainIndex, SettlingFactor = ain.settlingFactor, Differential = ain.negChannel) )
        
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
            fios.append( FIO(i, label % (i + labelOffset), (DIGITAL_IN_TYPE if fioDir == 0 else DIGITAL_OUT_TYPE), fioState) )
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
        
            if i < 16 and (( analog >> i) & 1):
                fios.append( FIO(i) )
            else:
                fioDir = dev.readRegister(6100 + i)
                fioState = dev.readRegister(6000 + i)
                
                fios.append( FIO(i, label % (i + labelOffset), (DIGITAL_IN_TYPE if fioDir == 0 else DIGITAL_OUT_TYPE), fioState) )
            
        return fios
        
    
    def updateDeviceDict(self):
    
        if self.usbOverride:
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
                
            print devs
                
        else:
            ljsocketAddress = "%s:%s" % (self.address, self.port)
            devs = LabJackPython.listAll(ljsocketAddress, 200)
        
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
                except Exception, e:
                    raise Exception( "Error with configU3: %s" % e )
                    
                try:
                    #d.debug = True
                    d.fioList = self.makeU3FioList(d)
                except Exception, e:
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
            else:
                raise Exception("Unknown device type")
            
            d.scanCache = (0, None)
            self.devices["%s" % dev['serial']] = d
        
        # Remove the disconnected devices
        for serial in self.devices.keys():
            if serial not in serials:
                print "Removing device with serial = %s" % serial
                self.devices[str(serial)].close()
                self.devices.pop(str(serial))

    def scan(self, serial = None):
        dev = self.getDevice(serial)
        now = int(time.time())
        if (now - dev.scanCache[0]) >= 1:
            if dev.devType == 3:
                result = self.u3Scan(dev)
            elif dev.devType == 6:
                result = self.u6Scan(dev)
            elif dev.devType == 9:
                result = self.ue9Scan(dev)
                
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

    def u3Scan(self, dev):
        fioAnalog = dev.readRegister(50590)
        eioAnalog = dev.readRegister(50591)
        
        results = list()
        
        for fio in dev.fioList:
            results.append( fio.readResult(dev) )
        
        ioResults = dev.configIO()
        for i in range(ioResults['NumberOfTimersEnabled']):
            results.append( self.readTimer(dev, i) )
            
        if ioResults['EnableCounter0']:
            results.append( self.readCounter(dev, 0) )
            
        if ioResults['EnableCounter1']:
            results.append( self.readCounter(dev, 1) )

        for register, label in DAC_DICT.items():
            dacState = dev.readRegister(register)
            results.append({'connection' : label, 'connectionNumber' : register, 'state' : "%0.5f" % dacState, 'value' : "%0.5f" % dacState})
        
        # Returns Kelvin, converting to Fahrenheit
        # F = K * (9/5) - 459.67
        internalTemp = kelvinToFahrenheit(dev.readRegister(60))
        results.append({'connection' : "InternalTemp", 'state' : "%0.5f" % internalTemp, 'value' : "%0.5f" % internalTemp, 'chType' : "internalTemp"}) 

        if str(dev.serialNumber) in self.loggingThreads:
            headers = self.loggingThreads[str(dev.serialNumber)].headers
        else:
            headers = []
            
        for result in results:
            if result['connection'] in headers:
                result['logging'] = True
            else:
                result['logging'] = False
        
        return dev.serialNumber, results

    def u6Scan(self, dev):
        results = list()
        
        analogInputs = dev.getFeedback( dev.analogCommandList )
        
        for i, value in enumerate(analogInputs):
            fio = dev.fioList[i]
            v = dev.binaryToCalibratedAnalogVoltage(fio.gainIndex, value)
            
            results.append(fio.parseAinResults(v))
        
        digitalDirections, digitalStates = dev.getFeedback( dev.digitalCommandList )
        
        
        for i in range(dev.numberOfDigitalIOs):
            fio = dev.fioList[ i + dev.numberOfAnalogIn ]
            
            direction = ((digitalDirections[fio.label[:3]]) >> int(fio.label[3:])) & 1
            state = ((digitalStates[fio.label[:3]]) >> int(fio.label[3:])) & 1
            
            results.append( fio.parseFioResults(direction, state) )
        
        for register, label in DAC_DICT.items():
            dacState = dev.readRegister(register)
            results.append({'connection' : label, 'connectionNumber' : register, 'state' : "%0.5f" % dacState, 'value' : "%0.5f" % dacState})
        
        internalTemp = kelvinToFahrenheit(dev.readRegister(28))
        results.append({'connection' : "InternalTemp", 'state' : "%0.5f" % internalTemp, 'value' : "%0.5f" % internalTemp, 'chType' : "internalTemp"})
        
        if str(dev.serialNumber) in self.loggingThreads:
            headers = self.loggingThreads[str(dev.serialNumber)].headers
        else:
            headers = []
            
        for result in results:
            if result['connection'] in headers:
                result['logging'] = True
            else:
                result['logging'] = False
        
        return dev.serialNumber, results

    def listAll(self):
        devices = dict()
        for dev in self.devices.values():
            name = dev.getName()
            devices[str(dev.serialNumber)] = name
        
        return devices
        
    def details(self, serial):
        dev = self.devices[serial]
        
        return deviceAsDict(dev)
        
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
        
        devices['html'] = t.respond()
        
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

    @exposeJsonFunction
    def inputInfo(self, serial = None, inputNumber = 0):
        """ Returns a JSON of the current state of an input.
        """
        inputConnection = self.dm.getFioInfo(serial, int(inputNumber))
        return inputConnection

    @exposeJsonFunction
    def updateInputInfo(self, serial, inputNumber, chType, negChannel = None, state = None ):
        """ For configuring an input.
            serial = serial number of device
            inputNumber = the row number of that input
            chType = ( analogIn, digitalIn, digitalOut )
            negChannel = the negative channel, only matters for analogIn type
            state = 1 for high, 0 for low. Only matters for digitalOut
        """
        if negChannel and int(negChannel) < 30:
            print "Setting %s to analog." % negChannel
            inputConnection = FIO( int(negChannel), "FIO%s" % negChannel, chType, state, 31 )
            self.dm.updateFio(serial, inputConnection)
            
        # Make a temp FIO with the new settings.
        inputConnection = FIO( int(inputNumber), "FIO%s" % inputNumber, chType, state, negChannel )
        
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
            return self.scan(serial)

    @exposeJsonFunction
    def scan(self, serial = None):
        """ Scan reads all the inputs and such off the device. Renders the
            result as a JSON.
        """
        
        print "Scan: serial = %s" % serial
        serialNumber, results = self.dm.scan(serial)
        
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
    
    @exposeRawFunction    
    def exportConfigToFile(self, serial):
        """ Allows people to download the configuration of their LabJack.
        """
        
        # Call the exportConfig function on the device.
        devDict, result = self.dm.callDeviceFunction(serial, "exportconfig", [], {})
        
        # exportConfig returns a ConfigParser object. We need it as a string.
        fakefile = StringIO.StringIO()
        result.write(fakefile)
        
        # Set the headers
        cherrypy.response.headers['Content-Type'] = "application/x-download"
        cd = '%s; filename="%s"' % ("attachment", "labjack-%s-%s-conf.txt" % (devDict['productName'], devDict['serial']) )
        cherrypy.response.headers["Content-Disposition"] = cd
        
        # Send the data
        return fakefile.getvalue()


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
        activeFiles = []
        for thread in self.dm.loggingThreads.values():
            activeFiles.append({ "%s" % thread.filename : thread.serial)
    
        l = []
        logfilesDir = os.path.join(current_dir,"logfiles")
        files = sorted(os.listdir(logfilesDir), reverse = True, key = lambda x: os.stat(os.path.join(logfilesDir,x)).st_ctime)
        for filename in files:
            newName = replaceUnderscoresWithColons(filename)
            
            active = False
            stopurl = ""
            if filename in activeFiles:
                active = True
                stopurl = "/logs/stop?serial=%s" % activeFiles[filename]
            
            size = os.stat(os.path.join(logfilesDir,filename)).st_size
            size = float(size)/1024
            
            aLog = dict(name = newName, url= "/logfiles/%s" % filename, uploadurl = "/logs/upload/%s" % filename, removeurl = "/logs/remove/%s" % filename, size = "%.2f" % size, active = active, stopurl = stopurl)
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
        
        t.mainContent = tMainContent.respond()

        return t.respond()
        
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
            return False
        else:
            self.dm.stopDeviceLogging(serial)
    

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
        
        self.users = UsersPage(dm)
    
    @exposeRawFunction
    def index(self):
        """ if we can talk to LJSocket, renders index.html. Otherwise, 
            it renders connect.html """
        
        # Tell people (firefox) not to cache this page. 
        cherrypy.response.headers['Cache-Control'] = "no-cache"
        
        if self.dm.connected:
            t = serve_file2("templates/index.tmpl")
            
            tMainContent = serve_file2("templates/devices-main-content.tmpl")
            t.mainContent = tMainContent.respond()
            
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
