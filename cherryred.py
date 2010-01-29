"""

Name: cherryred.py
Desc:

"""

# Imports
import cherrypy
from cherrypy.lib.static import serve_file

import os.path, zipfile

import json

import sys

import StringIO, ConfigParser

import LabJackPython, u3, u6, ue9
from Autoconvert import autoConvert

import webbrowser

import mimetypes
mimetypes.init()
mimetypes.types_map['.dwg']='image/x-dwg'
mimetypes.types_map['.ico']='image/x-icon'
mimetypes.types_map['.bz2']='application/x-bzip2'
mimetypes.types_map['.gz']='application/x-gzip'


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

# Map all the functions to lower case.
u3Dict = buildLowerDict(u3.U3)
u6Dict = buildLowerDict(u6.U6)
ue9Dict = buildLowerDict(ue9.UE9)

LJSOCKET_ADDRESS = "localhost"
LJSOCKET_PORT = "6000"

ANALOG_TYPE = "analogIn"
DIGITAL_OUT_TYPE = "digitalOut"
DIGITAL_IN_TYPE = "digitalIn"
    
if not getattr(sys, 'frozen', ''):
    # not frozen: in regular python interpreter
    IS_FROZEN = False
else:
    # py2exe: running in an executable
    IS_FROZEN = True

def deviceAsDict(dev):
    """ Returns a dictionary representation of a device.
    """
    name = dev.getName()
    
    if dev.devType == 9:
        firmware = [dev.commFWVersion, dev.controlFWVersion]
    else:
        firmware = dev.firmwareVersion 
    
    return {'devType' : dev.devType, 'name' : name, 'serial' : dev.serialNumber, 'productName' : dev.deviceName, 'firmware' : firmware, 'localId' : dev.localId}

# Class Definitions
class FIO(object):
    """
    The FIO Class represents a single input. Helps keep track of state.
    """
    def __init__(self, fioNumber, label = None , chType = "analogIn", state = None):
        self.fioNumber = fioNumber
        self.chType = chType
        self.label = None
        self.negChannel = False
        self.gainIndex = 0
        self.resolutionIndex = 1
        self.settleingFactor = 0
        
        if state is not None:
            self.state = int(state)
        else:
            self.state = None
        
        if self.chType == ANALOG_TYPE:
            self.negChannel = 31
            self.label = "AIN%s" % self.fioNumber
        else:
            self.label = "FIO%s" % self.fioNumber
            
        if label != None:
            self.label = label
    
    def asDict(self):
        """ Returns a dictionary representation of a FIO
        """
        return { "fioNumber" : self.fioNumber, "chType" : self.chType, "label" : self.label, "negChannel" : self.negChannel, "state": self.state, 'gainIndex' : self.gainIndex, 'resolutionIndex' : self.resolutionIndex, 'settleingFactor' : self.settleingFactor }
        
    def transform(self, dev, inputConnection):
        """ Converts a FIO to match a given FIO
        """
        if inputConnection.chType == ANALOG_TYPE:
            self.negChannel = inputConnection.negChannel
            self.gainIndex = 0
            self.resolutionIndex = 1
            self.settleingFactor = 0
            self.setSelfToAnalog(dev)
        elif inputConnection.chType == DIGITAL_OUT_TYPE:
            self.state = inputConnection.state
            self.setSelfToDigital(dev, DIGITAL_OUT_TYPE) 
        else:
            self.setSelfToDigital(dev, DIGITAL_IN_TYPE)
    
    
    def setSelfToDigital(self, dev, chType):
        # FIO or EIO
        if self.fioNumber < 16:
            if self.fioNumber < 8:
                reg = 50590
                self.label = "FIO%s" % self.fioNumber
            else:
                reg = 50591
                self.label = "EIO%s" % ( self.fioNumber % 8 )
            
            analog = dev.readRegister(reg)  
            
            digitalMask = 0xffff - ( 1 << (self.fioNumber % 8) )
            
            analog = analog & digitalMask
            
            # Set pin to digital.
            dev.writeRegister(reg, analog)
        else:
            self.label = "CIO%s" % ( self.fioNumber % 16 )
        
        if chType == DIGITAL_OUT_TYPE:
            dev.writeRegister(6100 + self.fioNumber, 1)
            dev.writeRegister(6000 + self.fioNumber, self.state)
        else:
            dev.writeRegister(6100 + self.fioNumber, 0)
        
        print "Setting self to be %s" % chType
        self.chType = chType
    
    def setSelfToAnalog(self, dev):
        # FIO or EIO
        if self.fioNumber < 8:
            reg = 50590
        else:
            reg = 50591
            
        analog = dev.readRegister(reg)
            
        analog |= (1 << (self.fioNumber % 8))
        
        # Set pin to Analog.
        dev.writeRegister(reg, analog)
        
        # Set Negative channel.
        if self.negChannel == 32:
            dev.writeRegister(3000 + self.fioNumber, 30)
        else:
            dev.writeRegister(3000 + self.fioNumber, self.negChannel)
        
        self.chType = ANALOG_TYPE
        self.label = "AIN%s" % ( self.fioNumber )
    
    def readResult(self, dev):
        if self.chType == ANALOG_TYPE:
            return self.readAin(dev)
        else:
            return self.readFio(dev)

    def readAin(self, dev):
        state = dev.readRegister(self.fioNumber*2)
        if self.negChannel == 32:
            state += 2.4
        
        return self.parseAinResults(state)
        
    def parseAinResults(self, state):
        infoDict = dict()
        infoDict['connection'] = self.label
        infoDict['state'] = "%0.5f" % state
        infoDict['value'] = "%0.5f" % state # Use state for 'state' and 'value'
        infoDict['chType'] = self.chType
        
        return infoDict

    def readFio(self, dev):
        fioDir = dev.readRegister(6100 + self.fioNumber)
        fioState = dev.readRegister(6000 + self.fioNumber)
        
        return self.parseFioResults(fioDir, fioState)
        
    def parseFioResults(self, fioDir, fioState):
        if fioDir == 0:
            fioDirText = "Input"
        else:
            fioDirText = "Output"
            
        if fioState == 0:
            fioStateText = "Low"
        else:
            fioStateText = "High"
        
        infoDict = {'connection' : self.label, 'state' : "%s %s" % (fioDirText, fioStateText), 'value' : "%s" % fioState}
        infoDict['chType'] = (DIGITAL_IN_TYPE if fioDir == 0 else DIGITAL_OUT_TYPE)
        
        return infoDict

class DeviceManager(object):
    """
    The DeviceManager class will manage all the open connections to LJSocket
    """
    def __init__(self):
        self.address = LJSOCKET_ADDRESS
        self.port = LJSOCKET_PORT
    
        self.devices = dict()
        
        try:
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
    
    def getFioInfo(self, serial, inputNumber):
        dev = self.getDevice(serial)
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
            analogCommandList.append( u6.AIN24(i, ResolutionIndex = ain.resolutionIndex, GainIndex = ain.gainIndex, SettlingFactor = ain.settleingFactor, Differential = ain.negChannel) )
        
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
        ljsocketAddress = "%s:%s" % (self.address, self.port)
        devs = LabJackPython.listAll(ljsocketAddress, 200)
        
        serials = list()
        
        for dev in devs:
            if dev['serial'] in self.devices:
                continue
            
            serials.append(str(dev['serial']))
            
            if dev['prodId'] == 3:
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
                    raise Exception( "makign u3 fio list: %s" % e )
                
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
            
            self.devices["%s" % dev['serial']] = d
        
        # Remove the disconnected devices
        for serial in self.devices.keys():
            if serial not in serials:
                self.devices[str(serial)].close()
                self.devices.pop(str(serial))

    def scan(self, serial = None):
        dev = self.getDevice(serial)
        
        if dev.devType == 3:
            return self.u3Scan(dev)
        elif dev.devType == 6:
            return self.u6Scan(dev)
        elif dev.devType == 9:
            return self.ue9Scan(dev)
    

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
        
        dac0State = dev.readRegister(5000)
        dac1State = dev.readRegister(5002)
        results.append({'connection' : "DAC0", 'state' : "%0.5f" % dac0State, 'value' : "%0.5f" % dac0State})
        results.append({'connection' : "DAC1", 'state' : "%0.5f" % dac1State, 'value' : "%0.5f" % dac1State})
        
        internalTemp = dev.readRegister(60) - 273.15
        results.append({'connection' : "InternalTemp", 'state' : "%0.5f" % internalTemp, 'value' : "%0.5f" % internalTemp, 'chType' : "internalTemp"}) 
        
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
        
        dac0State = dev.readRegister(5000)
        dac1State = dev.readRegister(5002)
        results.append({'connection' : "DAC0", 'state' : "%0.5f" % dac0State, 'value' : "%0.5f" % dac0State})
        results.append({'connection' : "DAC1", 'state' : "%0.5f" % dac1State, 'value' : "%0.5f" % dac1State})
        
        internalTemp = dev.readRegister(28) - 273.15
        results.append({'connection' : "InternalTemp", 'state' : "%0.5f" % internalTemp, 'value' : "%0.5f" % internalTemp, 'chType' : "internalTemp"})
        
        
        return dev.serialNumber, results

    def listAll(self):
        devices = dict()
        for dev in self.devices.values():
            name = dev.getName()
            devices[str(dev.serialNumber)] = name
        
        return json.dumps(devices)
        
    def details(self, serial):
        dev = self.devices[serial]
        
        return json.dumps( deviceAsDict(dev) )
        
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

class DevicesPage:
    """ A class for handling all things /devices/
    """
    def __init__(self, dm):
        self.dm = dm
    
    def header(self):
        return "<html><body>"
    
    def footer(self):
        return "</body></html>"

    def index(self):
        """ Handles /devices/, returns a JSON list of all known devices.
        """
        self.dm.updateDeviceDict()
        
        cherrypy.response.headers['content-type'] = "application/json"
        return self.dm.listAll()
        
    index.exposed = True
    
    
    def default(self, serial, cmd = None, *pargs, **kwargs):
        """ Handles URLs like: /devices/<serial number>/
            if the URL is just /devices/<serial number>/ it returns the
            "details" of that device.
            
            if the URL is more like /devices/<serial number>/<command>, it runs
            that command on the device.
        """
        if cmd is None:
            cherrypy.response.headers['content-type'] = "application/json"
            yield self.dm.details(serial)
        else:
            # TODO: Make this return a JSON
            yield self.header()
            yield "<p>serial = %s, cmd = %s</p>" % (serial, cmd)
            yield "<p>kwargs = %s, pargs = %s</p>" % (str(kwargs), str(pargs))
            yield "<p>%s</p>" % self.dm.callDeviceFunction(serial, cmd, pargs, kwargs)[1]
            yield self.footer()
    default.exposed = True
    
    def inputInfo(self, serial = None, inputNumber = 0):
        """ Returns a JSON of the current state of an input.
        """
        inputConnection = self.dm.getFioInfo(serial, int(inputNumber))
        cherrypy.response.headers['content-type'] = "application/json"
        yield json.dumps(inputConnection)
    
    inputInfo.exposed = True
    
    def updateInputInfo(self, serial, inputNumber, chType, negChannel = None, state = None ):
        """ For configuring an input.
            serial = serial number of device
            inputNumber = the row number of that input
            chType = ( AnalogIn, DigitalIn, DigitalOut )
            negChannel = the negative channel, only matters for AnalogIN type
            state = 1 for high, 0 for low. Only matters for DigitalOut
        """
        
        # Make a temp FIO with the new settings.
        inputConnection = FIO( int(inputNumber), "FIO%s" % inputNumber, chType, state )
        
        # Tells the device manager to update the input
        self.dm.updateFio(serial, inputConnection)
    updateInputInfo.exposed = True
    
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
    toggleDigitalOutput.exposed = True

    def scan(self, serial = None):
        """ Scan reads all the inputs and such off the device. Renders the
            result as a JSON.
        """
        
        print "Scan: serial = %s" % serial
        serialNumber, results = self.dm.scan(serial)
        
        cherrypy.response.headers['content-type'] = "application/json"
        yield json.dumps(results)
    scan.exposed = True



    # ---------------- Deprecated ----------------
    def setFioState(self, serial = None, fioNumber = 0, state = 1):
        result = self.dm.setFioState(serial, fioNumber, state)
        yield self.header()
        yield "<p>FIO%s has been set to output %s</p>" % (fioNumber, result)
        yield self.footer()
        
    setFioState.exposed = True
    
    def setName(self, serial = None, name = None):
        yield self.header()
        
        if name is not None:
            serialNumber, name = self.dm.setName(serial, name)
            yield "%s's name set to %s" % (serialNumber, name)
        
        yield self.footer()
    setName.exposed = True
    
    # ---------------- End Deprecated ----------------
    
    def setDefaults(self, serial = None):
        """ Makes the calls to set the current state of the device as the
            power-up default.
        """
        results = { 'state' : self.dm.setDefaults(serial) }
        
        cherrypy.response.headers['content-type'] = "application/json"
        yield json.dumps(results)
    setDefaults.exposed = True
    
    
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
        
    importConfigFromFile.exposed = True
        
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

    exportConfigToFile.exposed = True

if IS_FROZEN:
    # All of this depends on us being 'frozen' in an executable.
    ZIP_FILE = zipfile.ZipFile(os.path.abspath(sys.executable), 'r')    

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
            print "%s not in name list."
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
        return body
    else:
        return serve_file(os.path.join(current_dir,path))

class RootPage:
    """ The RootPage class handles showing index.html. If we can't connect to
        LJSocket then it shows connect.html instead.
    """
    def __init__(self, dm):
        # Keep a copy of the device manager
        self.dm = dm
        
        # Adds the DevicesPage child which handles all the device communication
        self.devices = DevicesPage(dm)
    
    def index(self):
        """ if we can talk to LJSocket, renders index.html. Otherwise, 
            it renders connect.html """
        
        # Tell people (firefox) not to cash this page. 
        cherrypy.response.headers['Cache-Control'] = "no-cache"
        
        if self.dm.connected:
            return serve_file2("html/index.html")
        else:
            return serve_file2("html/connect.html")
    index.exposed = True
    
    def retry(self, address = "localhost", port = "6000"):
        """ The retry endpoint is for trying to connect to LJSocket.
            No matter what happens it will redirect you to '/'.
        """
        self.dm.address = address
        self.dm.port = port
        
        try:
            self.dm.updateDeviceDict()
            self.dm.connected = True
        except Exception,e:
            print "Retry got an exception:", e
        
        raise cherrypy.HTTPRedirect("/")
    retry.exposed = True


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
