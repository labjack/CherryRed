"""

Name: grounded.py
Desc: A cross-platform program for getting started with your LabJack.

"""

# Local Imports
from devicemanager import DeviceManager
from skymotemanager import SkyMoteManager
from fio import FIO, UE9FIO
from groundedutils import *

# Required Packages Imports
# - CherryPy
import cherrypy
import cherrypy.lib
from cherrypy.lib.static import serve_file
from Cheetah.Template import Template

# - LabJackPython
import LabJackPython

# - gdata
import gdata.docs.service
import gdata.service

# Standard Library Imports
from datetime import datetime
import os, os.path, zipfile
import json, httplib2
from urllib import urlencode, quote, unquote
import sys, socket

import cStringIO as StringIO, ConfigParser

import webbrowser

import sys
import traceback

# Mimetypes helps select the correct type based on extension.
import mimetypes
mimetypes.init()
mimetypes.types_map['.dwg']='image/x-dwg'
mimetypes.types_map['.ico']='image/x-icon'
mimetypes.types_map['.bz2']='application/x-bzip2'
mimetypes.types_map['.gz']='application/x-gzip'
mimetypes.types_map['.csv']='text/plain'


# Global Constants
CLOUDDOT_GROUNDED_VERSION = "0.01"

CLOUDDOT_GROUNDED_CONF = "./clouddotgrounded.conf"


if not getattr(sys, 'frozen', ''):
    # not frozen: in regular python interpreter
    IS_FROZEN = False
else:
    # py2exe: running in an executable
    IS_FROZEN = True

# Global Utility Functions
# - Create some decorator methods for functions.
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
        return json.dumps(result)+"\n"
        
    jsonFunction.exposed = True
    return jsonFunction


# Class Definitions

class DevicesPage(object):
    """ A class for handling all things /devices/
    """
    def __init__(self, dm):
        self.dm = dm
    
    @exposeJsonFunction
    def index(self):
        """ Handles /devices/, returns a JSON list of all known devices.
        """
        self.dm.updateDeviceDict()
        
        devices = self.dm.listAll()
        
        t = serve_file2("templates/devices.tmpl")
        t.devices = devices
        t.hashPrefix = "d"

        t2 = serve_file2("templates/device-summary-list.tmpl")
        t2.UE9_MIN_FIRMWARE = UE9_MIN_FIRMWARE_VERSION
        t2.U6_MIN_FIRMWARE = U6_MIN_FIRMWARE_VERSION
        t2.U3_MIN_FIRMWARE = U3_MIN_FIRMWARE_VERSION
        t2.devices = [ deviceAsDict(d) for d in  self.dm.devices.values() ]
        
        devices['html'] = t.respond()
        devices['htmlSummaryList'] = t2.respond()

        if self.dm.usbOverride:
            t3  = serve_file2("templates/usb-only.tmpl")
            devices['usbOverride'] = t3.respond()

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
            
            if not returnDict['meetsFirmwareRequirements']:
                returnDict['html'] = """<div>Device doesn't meet firmware requirements</div>"""
                returnDict['htmlScanning'] = ""
            
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
    def timerCounterConfig(self, serial, counterSelected = False):
        devType = self.dm.getDevice(serial).devType
        currentConfig = self.dm.readTimerCounterConfig(serial.encode("ascii", "replace"))
        
        print currentConfig
        
        t = serve_file2("templates/device-configureTimerCounter.tmpl")
        t.devType = devType
        t.timerModeUrls = createTimerModeToHelpUrlList(devType)
        t.updateUrl = "/devices/updateTimerCounterConfig/%s" % serial
        t.currentConfig = currentConfig
        t.offsetChoices = createTimerChoicesList(devType)
        tcPinLocationHtml = self.tcPinLocationSummary(serial)

        returnDict = dict(html = t.respond(), serial = serial, counterSelected = counterSelected, tcPinLocationHtml = tcPinLocationHtml)        
        return returnDict

    def offsetToLabel(self, offset):
        if offset < 8:
            return "FIO%i" % offset
        else:
            return "EIO%i" % (offset - 8)

    @exposeRawFunction
    def tcPinLocationSummary(self, serial, timerClockBase = 0, timerClockDivisor = 1, pinOffset = 0, counter0Enable = 0, counter1Enable = 0, **timerSettings):
        t = serve_file2("templates/tc-pin-location-summary.tmpl")
        
        pinOffset = int(pinOffset)
        timerClockBase = int(timerClockBase)
        counter0Enable = int(counter0Enable)
        counter1Enable = int(counter1Enable)
        
        tcPins = []
        numTimersEnabled = 0
        for i in range(6):
            if "timer%iEnabled" % i in timerSettings:
                if int(timerSettings["timer%iEnabled" % i]):
                    tcPins.append((self.offsetToLabel(pinOffset), "Timer %i" % i))
                    pinOffset += 1
            else:
                break
        
        if counter0Enable:
            tcPins.append((self.offsetToLabel(pinOffset), "Counter 0"))
            pinOffset += 1
            
        if counter1Enable:
            tcPins.append((self.offsetToLabel(pinOffset), "Counter 1"))
            pinOffset += 1
        
        t.tcPins = tcPins
        return t.respond()

    @exposeRawFunction
    def resetCounter(self, serial, inputNumber = 0):
        self.dm.resetCounter(serial, int(inputNumber))
        
        return self.scan(serial, noCache = True)

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
        t.ljpVersion = LabJackPython.LABJACKPYTHON_VERSION
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
        
        if results:
            return results
        else:
            raise cherrypy.HTTPError(404)
    
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
        #print "filepath: %s" % filepath
        
        # Check if the file being requested is in the ZipFile
        if filepath not in ZIP_FILE.namelist():
            #print "%s not in name list." % filepath
            
            # Check if the file is local
            localAbsPath = os.path.join(current_dir,filepath)
            #print "localAbsPath: ", localAbsPath
            if (filepath.startswith("logfiles") or filepath.startswith("configfiles")) and os.path.exists(localAbsPath):
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

class CloudDotPage:
    """ A class for handling all things /clouddot/
    """
    def __init__(self, dm):
        self.dm = dm
        self.parser = ConfigParser.SafeConfigParser()
        
        self.readConfigFile()
        
    def readConfigFile(self):
        """ Reads in the username and API Key from the grounded config file and
            saves them to the device manager.
        """
        self.parser.read(CLOUDDOT_GROUNDED_CONF)
        
        if self.parser.has_section("CloudDot"):
            if self.parser.has_option("CloudDot", "username"):
                self.dm.username = self.parser.get("CloudDot", "username")
                
            if self.parser.has_option("CloudDot", "api key"):
                self.dm.apikey = self.parser.get("CloudDot", "api key")
                
    def saveConfigFile(self):
        """ Takes the username and API Key saved in the device manager and 
            writes them out to the grounded config file.
        """
        self.parser.read(CLOUDDOT_GROUNDED_CONF)
        
        if not self.parser.has_section("CloudDot"):
            self.parser.add_section("CloudDot")
        
        self.parser.set("CloudDot", "username", self.dm.username)
        self.parser.set("CloudDot", "api key", self.dm.apikey)
        
        with open(CLOUDDOT_GROUNDED_CONF, 'wb') as configfile:
            self.parser.write(configfile)

    @exposeJsonFunction
    def info(self, serial):
        """ Handles /clouddot/info/<serial>
        """
        # Tell people (firefox) not to cash this page. 
        cherrypy.response.headers['Cache-Control'] = "no-cache"
        
        return self._buildInfoDict(serial)
        
    def _buildInfoDict(self, serial):
        returnDict = {}
        
        if self.dm.username is None or self.dm.apikey is None:
            t = serve_file2("templates/clouddot-user-page.tmpl")
            returnDict['html'] = t.respond()
            returnDict['type'] = "user-page"
            returnDict['connected'] = False
        else:
            t = serve_file2("templates/clouddot-connect.tmpl")
            t.username = self.dm.username
            t.device = deviceAsDict(self.dm.getDevice(serial))
            
            returnDict['html'] = t.respond()
            returnDict['type'] = "connect-page"
            returnDict['connected'] = (str(serial) in self.dm.xmppThreads)
            
        
        return returnDict
    
    @exposeJsonFunction
    def connect(self, serial):
        print "Connecting %s to CloudDot." % serial
        
        self.dm.connectDeviceToCloudDot(serial)
        
        return {'result' : "connected"}
    
    @exposeJsonFunction
    def disconnect(self, serial):
        print "Disconnecting %s from CloudDot." % serial
        
        self.dm.disconnectDeviceFromCloudDot(serial)
        
        return {'result' : "disconnected"}
    
    @exposeJsonFunction
    def fetch(self):
        print "returning user info"
        
        return {'username' : self.dm.username, 'apikey' : self.dm.apikey}
    
    
    @exposeJsonFunction
    def ping(self, serial):
        dev = self.dm.getDevice(serial)
        data = { 'userName' : self.dm.username, "apiKey" : self.dm.apikey}
        
        pingurl = "http://cloudapi.labjack.com/%s/devices/%s/ping.json" % (self.dm.username, serial)
        pingurl += "?%s" % urlencode(data)
        
        h = httplib2.Http()
        resp, content = h.request(pingurl, "GET")
        
        if resp['status'] != '200':
            return { "message" : "The device %s has not been added CloudDot. Please add it." % serial}
        else:
            result = json.loads(content)
            if result['connected']:
                return { "message" : "%s is connected to CloudDot." % dev.name}
            else:
                return { "message" : "%s is not connected to CloudDot. Please try disconnecting and reconnecting." % dev.name}
    
    @exposeJsonFunction
    def check(self, label = None, username = None, apikey = None):
        """
        Checks for valid username and apikey
        """
        print "Check called..."
        print "label = %s, username = %s, apikey = %s" % (label, username, apikey)
        return self._checkUsernameAndApiKey(label, username, apikey)
        
    def _checkUsernameAndApiKey(self, label = None, username = None, apikey = None):
        if label is None:
            return False
        elif label == "username":
            devurl = "http://cloudapi.labjack.com/%s/devices.json" % username
            h = httplib2.Http()
            resp, content = h.request(devurl, "GET")
            if resp['status'] != '200':
                return {'username-valid' : 0}
            else:
                return {'username-valid' : 1}
        elif label == "apikey":
            data = { 'userName' : username, "apiKey" : apikey}
            devurl = "http://cloudapi.labjack.com/%s/info.json?%s" % (username, urlencode(data))
            h = httplib2.Http()
            resp, content = h.request(devurl, "GET")
            if resp['status'] == '401':
                return {'username-valid' : 1, 'apikey-valid' : 0}
            elif resp['status'] != '200':
                return {'username-valid' : 0, 'apikey-valid' : 0}
            else:
                return {'username-valid' : 1, 'apikey-valid' : 1}
    
    @exposeJsonFunction
    def update(self, serial = None, username = None, apikey = None):
        """ Updates the saved username and API Key.
        """
        print "Update called: Username = %s, apikey = %s" % (username, apikey)
        results = self._checkUsernameAndApiKey("apikey", username, apikey)
        
        if results['username-valid'] and results['username-valid']:
            self.dm.username = username
            self.dm.apikey = apikey
            
            self.saveConfigFile()
            #raise cherrypy.HTTPRedirect("/")
        else:
            print "Username or API Key was invaild."
        
        infoDict = self._buildInfoDict(serial)
        infoDict.update(results)
        
        return infoDict

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
        dev = self.dm.getDevice(serial)
        t.productName = dev.deviceName
        
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
        dirpath = os.path.join(current_dir,"configfiles/%s" % serial)
        if not os.path.isdir(dirpath):
            os.mkdir(dirpath)
        filepath = "%s/%s" % (dirpath, filename)
        configfile = file(filepath, "w")
        result.write(configfile)
        configfile.close()
        m = "Configuration &quot;%s&quot; saved." % replaceUnderscoresWithColons(filename)
        
        return m
        
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
        print "Regular path: ", path
        
        dev = self.dm.getDevice(serial)
        configfileDir = os.path.join(current_dir,"configfiles/%s" % dev.deviceName)
        basicpath = os.path.join(configfileDir, filename)
        print "Basic path: ", path
        
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
            m = "Configuration &quot;%s&quot; loaded." % replaceUnderscoresWithColons(filename)
        except OSError:
            m = "Couldn't find a file named &quot;%s&quot;." % replaceUnderscoresWithColons(filename)
            
        return m
    
    @exposeRawFunction
    def remove(self, serial, filename):
        logfileDir = os.path.join(current_dir,"configfiles/%s" % serial)
        path = os.path.join(logfileDir, filename)
        
        try:
            os.remove(path)
            m = "Configuration &quot;%s&quot; deleted." % replaceUnderscoresWithColons(filename)
        except OSError:
            m = "Couldn't find a file named &quot;%s&quot;." % replaceUnderscoresWithColons(filename)
            
        #TODO: Do something else here. Maybe some sort of response for AJAX?
        return m
        

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
        self.parser.add_section("googledocs")
        self.parser.set("googledocs", "session_token", str(sessionToken))
        with open(CLOUDDOT_GROUNDED_CONF, 'wb') as configfile:
            self.parser.write(configfile)

        raise cherrypy.HTTPRedirect("/logs/upload/%s" % unquote(filename))
    
    @exposeRawFunction
    def upload(self, filename):
        if self.gd_client is None:
            self.gd_client = gdata.docs.service.DocsService()
            token = self.loadSessionToken()
            
            if not token:
                next = '%s/logs/savetoken/%s' % (cherrypy.request.base, quote(filename))
                
                print "next: ", next
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
    

class FormsPage(object):
    """ A class for handling all things /forms/
        Renders forms for the javascript.
    """
    def __init__(self, dm):
        self.dm = dm
        
    @exposeRawFunction
    def editCommConfigForm(self):
        t = serve_file2("templates/form-edit-commConfig.tmpl")
        
        return t.respond()
        
    @exposeRawFunction
    def editLocalIdForm(self):
        t = serve_file2("templates/form-edit-localId.tmpl")
        
        return t.respond()

class SkyMotePage(object):
    """ For the SkyMote page.
    """
    def __init__(self, smm):
        self.smm = smm
        
    @exposeJsonFunction
    def bridges(self):
        """ Returns the html for the main page like /devices/, only for bridges
        """
        bridges = self.smm.findBridges()
        
        returnDict = dict()
        
        t = serve_file2("templates/devices.tmpl")
        
        nameDict = dict()
        for serial, bridge in bridges.items():
            nameDict[serial] = bridge.nameCache
        t.devices = nameDict
        t.hashPrefix = "sm"

        t2 = serve_file2("templates/device-summary-list.tmpl")
        t2.UE9_MIN_FIRMWARE = UE9_MIN_FIRMWARE_VERSION
        t2.U6_MIN_FIRMWARE = U6_MIN_FIRMWARE_VERSION
        t2.U3_MIN_FIRMWARE = U3_MIN_FIRMWARE_VERSION
        t2.devices = [ deviceAsDict(d) for d in  bridges.values() ]
        
        returnDict['html'] = t.respond()
        returnDict['htmlSummaryList'] = t2.respond()

        return returnDict
        
    @exposeRawFunction
    def index(self):
        """ Handles /skymote/
        """
        # Tell people (firefox) not to cache this page. 
        cherrypy.response.headers['Cache-Control'] = "no-cache"

        t = serve_file2("templates/index.tmpl")
        
        tMainContent = serve_file2("templates/skymote/index.tmpl")
        tMainContent.bridges = self.smm.findBridges()
        tMainContent.includeWrapper = True
        
        t.mainContent = tMainContent.respond()
        t.currentPage = "SkyMote"
        t.title = "SkyMote | LabJack CloudDot Grounded"

        return t.respond()
    
    @exposeJsonFunction
    def default(self, serial):
        """ Handles URLs like: /skymote/<serial number>/
        """
        b = self.smm.getBridge(serial)
        returnDict = dict(serial = serial)

        t = serve_file2("templates/skymote/overview.tmpl")
        t.device = b

        tScanning = serve_file2("templates/skymote/scanning.tmpl")
        tScanning.device = b

        returnDict['html'] = t.respond()

        returnDict['htmlScanning'] = tScanning.respond()

        return returnDict

    @exposeJsonFunction
    def config(self, serial, unitId = 0):
        ''' /skymote/config/<serial number>?unitId=<unit id> '''
        b = self.smm.getBridge(serial)
        returnDict = dict(serial = serial)

        t = serve_file2("templates/skymote/config-mote.tmpl")
        t.device = b

        returnDict['html'] = t.respond()

        return returnDict

    @exposeJsonFunction 
    def scan(self):
        return self.smm.scan()
        
    @exposeJsonFunction 
    def scanBridge(self, serial = None):
        if serial is not None:
            results = self.smm.scanBridge(str(serial))
            b = self.smm.getBridge(serial)

            for unitId, m in results['Connected Motes'].items():
                t = serve_file2("templates/skymote/overview-one-mote.tmpl")
                t.device = b
                t.m = m

                m['html'] = t.respond()

            return results


        else:
            print "No serial specified."
            return {}

class RootPage:
    """ The RootPage class handles showing index.html. If we can't connect to
        LJSocket then it shows connect.html instead.
    """
    def __init__(self, dm, smm):
        # Keep a copy of the device manager
        self.dm = dm
        # and SkyMote manager
        self.smm = smm

        # Adds the DevicesPage child which handles all the device communication
        self.devices = DevicesPage(dm)
        
        self.logs = LoggingPage(dm)
        self.config = ConfigPage(dm)
        
        self.clouddot = CloudDotPage(dm)
        
        self.forms = FormsPage(dm)
        
        self.skymote = SkyMotePage(smm)

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
        
        
        driverIsGood = False
        try:
            if LabJackPython.os.name == 'nt':
                driverIsGood = float(LabJackPython.GetDriverVersion()) >= UD_DRIVER_REQUIREMENT
            else:
                driverIsGood = float(LabJackPython.GetDriverVersion()) >= EXODRIVER_REQUIREMENT
        except:
            driverIsGood = True
        
        if self.dm.connected and driverIsGood:
            t = serve_file2("templates/index.tmpl")
            
            tMainContent = serve_file2("templates/devices-main-content.tmpl")
            t.mainContent = tMainContent.respond()
            t.currentPage = "devices"
            t.title = "LabJack CloudDot Grounded"
            
            return t.respond()
        elif not driverIsGood:
            t = serve_file2("templates/bad-driver-version.tmpl")
            t.currentVersion = LabJackPython.GetDriverVersion()
            if LabJackPython.os.name == 'nt':
                t.isWindows = True
                t.minVersion = UD_DRIVER_REQUIREMENT
            else:
                t.isWindows = False
                t.minVersion = EXODRIVER_REQUIREMENT
            
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

def quickstartWithBrowserOpen(root=None, script_name="", config=None, portOverride = None):
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
    
    if portOverride is not None:
        cherrypy._global_conf_alias['server.socket_port'] = portOverride
    
    # Check the port we want to start on isn't already in use. 
    skt = socket.socket()
    while True:
        port = cherrypy._global_conf_alias['server.socket_port']
        try:
            skt.bind(("0.0.0.0", cherrypy._global_conf_alias['server.socket_port']))
            skt.close()
            break
        except socket.error:
            print "Port %s in use, trying %s" % (port, port+1)
            cherrypy._global_conf_alias['server.socket_port'] += 1
    
    cherrypy.engine.start()
    
    openWebBrowser("localhost", cherrypy._global_conf_alias['server.socket_port'])
    
    cherrypy.engine.block()


# Main:
if __name__ == '__main__':
    dm = None
    smm = None
    try:
        portOverride = None
        ljsaddress = LJSOCKET_ADDRESS
        ljsport = LJSOCKET_PORT
        if os.path.exists(CLOUDDOT_GROUNDED_CONF):
            # Check local config file for a different port to bind to.
            parser = ConfigParser.SafeConfigParser()
            parser.read(CLOUDDOT_GROUNDED_CONF)
            
            if parser.has_section("General"):
                if parser.has_option("General", "port"):
                    portOverride = parser.getint("General", "port")
            
            if parser.has_section("LJSocket"):
                if parser.has_option("LJSocket", "address"):
                    ljsaddress = parser.get("LJSocket", "address")
                if parser.has_option("LJSocket", "port"):
                    ljsport = parser.getint("LJSocket", "port")
        print "Using address = %s, port = %s" % (ljsaddress, ljsport)
        dm = DeviceManager(address = ljsaddress, port = ljsport)
        smm = SkyMoteManager(address = ljsaddress, port = ljsport)
        
        # Register the shutdownThreads method, so we can kill our threads when
        # CherryPy is shutting down.
        cherrypy.engine.subscribe('stop', dm.shutdownThreads)
        cherrypy.engine.subscribe('stop', smm.shutdownThreads)
        
        # Ensure there is a logfiles directory
        if not os.path.isdir("./logfiles"):
            os.mkdir("./logfiles")
        
        # Ensure there is a configfiles directory
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
    
        root = RootPage(dm, smm)
        root._cp_config = {'tools.staticdir.root': current_dir, 'tools.renderFromZipFile.on': IS_FROZEN}
        quickstartWithBrowserOpen(root, config=configfile, portOverride = portOverride)
    except Exception, e:
        cla, exc, trbk = sys.exc_info()
        print "Error: %s: %s" % (cla, exc)
        print traceback.print_tb(trbk, 6)
         
        if dm is not None:
            dm.shutdownThreads()
            
        if smm is not None:
            smm.shutdownThreads()
            
        raw_input("An error occured that prevented this program from starting correctly. Please send a copy of the output above when asking for help.\nPress any key to exit... ")