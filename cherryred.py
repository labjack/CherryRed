"""

Name: cherryred.py
Desc:

"""

# Imports
import cherrypy
from cherrypy.lib.static import serve_file

import os.path

import json

import LabJackPython, u3, u6, ue9
from Autoconvert import autoConvert

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

# Class Definitions
class FIO(object):
    def __init__(self, fioNumber, label = None , chType = "analogIn", state = None):
        self.fioNumber = fioNumber
        self.chType = chType
        self.label = None
        self.negChannel = None
        
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
        return { "fioNumber" : self.fioNumber, "chType" : self.chType, "label" : self.label, "negChannel" : self.negChannel, "state": self.state }
        
    def transform(self, dev, inputConnection):
        # Check if we're doing a A -> D or D -> A switch
        if inputConnection.chType == ANALOG_TYPE:
            self.negChannel = inputConnection.negChannel
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
            dev.writeRegister(6100 + self.fioNumber, 0)
            dev.writeRegister(6000 + self.fioNumber, self.state)
        else:
            dev.writeRegister(6100 + self.fioNumber, 1)
        
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
        
        # Set Negitive channel.
        # TODO
        
        self.chType = ANALOG_TYPE
        self.label = "AIN%s" % ( self.fioNumber )
    
    def readResult(self, dev):
        if self.chType == ANALOG_TYPE:
            return self.readAin(dev)
        else:
            return self.readFio(dev)

    def readAin(self, dev):
        state = dev.readRegister(self.fioNumber*2)
        infoDict = dict()
        infoDict['connection'] = self.label
        infoDict['state'] = "%0.5f" % state
        infoDict['value'] = "%0.5f" % state # Use state for 'state' and 'value'
        infoDict['chType'] = self.chType
        
        return infoDict

    def readFio(self, dev):
        fioDir = dev.readRegister(6100 + self.fioNumber)
        fioState = dev.readRegister(6000 + self.fioNumber)
        
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
        
        return dev.fioList[inputNumber].asDict()
        
    def updateFio(self, serial, inputConnection):
        dev = self.getDevice(serial)
        
        current = dev.fioList[ inputConnection.fioNumber ]
        current.transform(dev, inputConnection)
    
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
                d = u3.U3(LJSocket = ljsocketAddress, serial = dev['serial'])
                d.configU3()
                d.fioList = self.makeU3FioList(d)
                
            elif dev['prodId'] == 6:
                d = u6.U6(LJSocket = ljsocketAddress, serial = dev['serial'])
                d.configU6()
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
        
        for i in range(4):
            results.append({'connection' : "AIN%s" % i, 'state' : "%0.5f" % dev.readRegister(i*2)})
            
        for i in range(4):
            fioDir = dev.readRegister(6100 + i)
            fioState = dev.readRegister(6000 + i)
            
            if fioDir == 0:
                fioDir = "Input"
            else:
                fioDir = "Output"
                
            if fioState == 0:
                fioState = "Low"
            else:
                fioState = "High"
            
            results.append({'connection' : "FIO%s" % i, 'state' : "%s %s" % (fioDir, fioState) })
        
        
        results.append({'connection' : "DAC0", 'state' : "%0.5f" %  dev.readRegister(5000) })
        results.append({'connection' : "DAC1" , 'state' : "%0.5f" %  dev.readRegister(5002) })
        results.append({'connection' : "InternalTemp", 'state' : "%0.5f" %  (dev.readRegister(28) - 273.15) })
        
        
        return dev.serialNumber, results

    def listAll(self):
        devices = dict()
        for dev in self.devices.values():
            name = dev.getName()
            devices[str(dev.serialNumber)] = name
        
        return json.dumps(devices)
        
    def details(self, serial):
        dev = self.devices[serial]
        name = dev.getName()
        
        if dev.devType == 9:
            firmware = [dev.commFWVersion, dev.controlFWVersion]
        else:
            firmware = dev.firmwareVersion 
        
        return json.dumps({'devType' : dev.devType, 'name' : name, 'serial' : dev.serialNumber, 'productName' : dev.deviceName, 'firmware' : firmware, 'localId' : dev.localId})
        
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
        
        return dev.serialNumber, dev.__getattribute__(classDict[funcName])(*pargs, **kwargs)

class DevicesPage:
    def __init__(self, dm):
        self.dm = dm
    
    def header(self):
        return "<html><body>"
    
    def footer(self):
        return "</body></html>"

    def index(self):
        self.dm.updateDeviceDict()
        
        cherrypy.response.headers['content-type'] = "application/json"
        return self.dm.listAll()
        
    index.exposed = True
    
    
    def default(self, serial, cmd = None, *pargs, **kwargs):
        if cmd is None:
            cherrypy.response.headers['content-type'] = "application/json"
            yield self.dm.details(serial)
        else:
            yield self.header()
            yield "<p>serial = %s, cmd = %s</p>" % (serial, cmd)
            yield "<p>kwargs = %s, pargs = %s</p>" % (str(kwargs), str(pargs))
            yield "<p>%s</p>" % self.dm.callDeviceFunction(serial, cmd, pargs, kwargs)[1]
            yield self.footer()
    default.exposed = True
    
    def inputInfo(self, serial = None, inputNumber = 0):
        inputConnection = self.dm.getFioInfo(serial, int(inputNumber))
        cherrypy.response.headers['content-type'] = "application/json"
        yield json.dumps(inputConnection)
    
    inputInfo.exposed = True
    
    def updateInputInfo(self, serial, inputNumber, chType, negChannel = None, state = None ):
        inputConnection = FIO( int(inputNumber), "FIO%s" % inputNumber, chType, state )
        self.dm.updateFio(serial, inputConnection)
    updateInputInfo.exposed = True
    
    def scan(self, serial = None):
        #yield self.header()
        
        print "Scan: serial = %s" % serial
        serialNumber, results = self.dm.scan(serial)
        
        cherrypy.response.headers['content-type'] = "application/json"
        yield json.dumps(results)
        
            
    scan.exposed = True

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
    
    def setDefaults(self, serial = None):
        results = { 'state' : self.dm.setDefaults(serial) }
        
        cherrypy.response.headers['content-type'] = "application/json"
        yield json.dumps(results)
    setDefaults.exposed = True
        

class RootPage:
    def __init__(self, dm):
        self.dm = dm
        self.devices = DevicesPage(dm)
    
    def index(self):
        if self.dm.connected:
            return serve_file(os.path.join(current_dir , "html/index.html"))
        else:
            return serve_file(os.path.join(current_dir , "html/connect.html"))
    index.exposed = True
    
    def retry(self, address = "localhost", port = "6000"):
        self.dm.address = address
        self.dm.port = port
        
        try:
            self.dm.updateDeviceDict()
            self.dm.connected = True
        except:
            pass
        
        raise cherrypy.HTTPRedirect("/")
    retry.exposed = True

# Main:
if __name__ == '__main__':
    dm = DeviceManager()

    current_dir = os.path.dirname(os.path.abspath(__file__))

    root = RootPage(dm)
    root._cp_config = {'tools.staticdir.root': current_dir}
    cherrypy.quickstart(root, config="cherryred.conf")
