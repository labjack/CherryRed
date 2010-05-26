"""

Name: cherryred.py
Desc:

"""

# Imports
import cherrypy
import cherrypy.lib
from cherrypy.lib.static import serve_file
from Cheetah.Template import Template

import xmppconnection, logger
from fio import FIO

import os, os.path, zipfile

import json, httplib2
from urllib import urlencode

import sys, time

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
        
        cherrypy.engine.subscribe('stop', self.shutdownThreads)
        
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
    
    def startDeviceLogging(self, serial):
        d = self.getDevice(serial)
        
        if str(d.serialNumber) not in self.loggingThreads:
            lt = logger.LoggingThread(self, d.serialNumber)
            lt.start()
            self.loggingThreads[str(d.serialNumber)] = lt
            
            return True
        else:
            return False
            
    def stopDeviceLogging(self, serial):
        d = self.getDevice(serial)
        
        if str(d.serialNumber) in self.loggingThreads:
            lt = self.loggingThreads.pop(str(d.serialNumber))
            lt.stop()
            return True
        else:
            return False
    
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
                self.devices[str(serial)].close()
                self.devices.pop(str(serial))

    def scan(self, serial = None):
        dev = self.getDevice(serial)
        
        if (int(time.time()) - dev.scanCache[0]) >= 1:
            if dev.devType == 3:
                result = self.u3Scan(dev)
            elif dev.devType == 6:
                result = self.u6Scan(dev)
            elif dev.devType == 9:
                result = self.ue9Scan(dev)
                
            dev.scanCache = (int(time.time()), result)
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
            chType = ( analogIn, digitalIn, digitalOut )
            negChannel = the negative channel, only matters for analogIn type
            state = 1 for high, 0 for low. Only matters for digitalOut
        """
        # Make a temp FIO with the new settings.
        inputConnection = FIO( int(inputNumber), "FIO%s" % inputNumber, chType, state, negChannel )
        
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


    def connectToCloudDot(self, serial = None):
        print "Connecting %s to CloudDot." % serial
        
        self.dm.connectDeviceToCloudDot(serial)
        
        yield json.dumps({'result' : "connected"})
    
    connectToCloudDot.exposed = True

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

    def index(self):
        """ Handles /users/, returns a JSON list of all known devices.
        """
        # Tell people (firefox) not to cash this page. 
        cherrypy.response.headers['Cache-Control'] = "no-cache"
        
        return serve_file2("html/user.html")
        
    index.exposed = True
    
    def fetch(self):
        print "returning user info"
        
        yield json.dumps({'username' : self.dm.username, 'apikey' : self.dm.apikey})
    
    fetch.exposed = True
    
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
                return json.dumps({'username' : 1})
            else:
                return json.dumps({'username' : 0})
        elif label == "apikey":
            data = { 'userName' : username, "apiKey" : apikey}
            devurl = "http://cloudapi.labjack.com/%s/info.json?%s" % (username, urlencode(data))
            h = httplib2.Http()
            resp, content = h.request(devurl, "GET")
            if resp['status'] == '401':
                return json.dumps({'username' : 0, 'apikey' : 1})
            elif resp['status'] != '200':
                return json.dumps({'username' : 1, 'apikey' : 1})
            else:
                return json.dumps({'username' : 0, 'apikey' : 0})
    check.exposed = True
    
    def update(self, username = None, apikey = None):
        """ Updates the saved username and API Key.
        """
        print "Update called: Username = %s, apikey = %s" % (username, apikey)
        
        self.dm.username = username
        self.dm.apikey = apikey
        
        raise cherrypy.HTTPRedirect("/users/")
    update.exposed = True

class LoggingPage(object):
    """ A class for handling all things /log/
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
            
    def savetoken(self, filename, *args, **kwargs):
        singleUseToken = kwargs['token']
        self.gd_client.SetAuthSubToken(singleUseToken)
        self.gd_client.UpgradeToSessionToken()
        sessionToken = self.gd_client.GetAuthSubToken()
        self.parser.set("googledocs", "session_token", str(sessionToken))
        with open(CLOUDDOT_GROUNDED_CONF, 'wb') as configfile:
            self.parser.write(configfile)

        raise cherrypy.HTTPRedirect("/logs/upload/%s" % filename)
        #return "called savetoken. filename = %s, sessionToken = %s" % (filename, sessionToken)
        
        
    savetoken.exposed = True
    
    def upload(self, filename):
        if self.gd_client is None:
            self.gd_client = gdata.docs.service.DocsService()
            token = self.loadSessionToken()
            if token is None:
                myHost =  cherrypy.config.get('server.socket_host')
                if myHost == "0.0.0.0":
                    myHost = "localhost"
                myPort = cherrypy.config.get('server.socket_port')
                next = 'http://%s:%s/logs/savetoken/%s' % (myHost, myPort, filename)
                auth_sub_url = gdata.service.GenerateAuthSubRequestUrl(next, GOOGLE_DOCS_SCOPE, secure=False, session=True)
                raise cherrypy.HTTPRedirect(auth_sub_url)
            else:
                self.gd_client.SetAuthSubToken(token, scopes=[GOOGLE_DOCS_SCOPE])
        
        csvPath = os.path.join(current_dir,"logfiles/%s" % filename)
        csvFile = file(csvPath)
        virtual_media_source = gdata.MediaSource(file_handle=csvFile, content_type='text/csv', content_length=os.path.getsize(csvPath))
        db_entry = self.gd_client.UploadSpreadsheet(virtual_media_source, filename)
        return "Upload: filename = %s" % filename
    
    upload.exposed = True

    def getLogFiles(self):
        l = []
        files = os.listdir(os.path.join(current_dir,"logfiles"))
        for filename in files:
            aLog = dict(name = filename, url= "/logfiles/%s" % filename, uploadurl = "/logs/upload/%s" % filename)
            l.append(aLog)
        return l

    def index(self):
        """ Handles /logs/
        """
        # Tell people (firefox) not to cache this page. 
        cherrypy.response.headers['Cache-Control'] = "no-cache"
        
        t = serve_file2("templates/logfiles.tmpl")
        t.logfiles = self.getLogFiles()

        return t.respond()
        #return serve_file2("html/log.html")
        
    index.exposed = True
    
    def start(self, serial = None):
        if serial is None:
            print "serial is null"
            return False
        else:
            self.dm.startDeviceLogging(serial)
    start.exposed = True
    
    def stop(self, serial = None):
        if serial is None:
            print "serial is null"
            return False
        else:
            self.dm.stopDeviceLogging(serial)
    stop.exposed = True

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
