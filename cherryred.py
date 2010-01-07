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

# Class Definitions
class DeviceManager(object):
    """
    The DeviceManager class will manage all the open connections to LJSocket
    """
    def __init__(self):
        self.devices = dict()
        
        self.updateDeviceDict()
        
        print self.devices
    
    def updateDeviceDict(self):
        devs = LabJackPython.listAll("localhost:6000", 200)
        
        serials = list()
        
        for dev in devs:
            if dev['serial'] in self.devices:
                continue
            
            serials.append(str(dev['serial']))
            
            if dev['prodId'] == 3:
                d = u3.U3(LJSocket = "localhost:6000", serial = dev['serial'])
                d.configU3()
            elif dev['prodId'] == 6:
                d = u6.U6(LJSocket = "localhost:6000", serial = dev['serial'])
                d.configU6()
            elif dev['prodId'] == 9:
                d = ue9.UE9(LJSocket = "localhost:6000", serial = dev['serial'])
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
        if serial is None:
            dev = self.devices.values()[0]
        else:
            dev = self.devices[serial]
        
        
        if dev.devType == 3:
            return self.u3Scan(dev)
        elif dev.devType == 6:
            return self.u6Scan(dev)
        elif dev.devType == 9:
            return self.ue9Scan(dev)

    def u3Scan(self, dev):
        fioAnalog = dev.readRegister(50590)
        
        results = dict()
        
        for i in range(8):
            if (( fioAnalog >> i) & 1):
                results["AIN%s" % i] = "%0.5f" % dev.readRegister(i*2)
            else:
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
                
                results["FIO%s" % i] = "%s %s" % (fioDir, fioState)
                
        results["DAC0"] = "%0.5f" %  dev.readRegister(5000)
        results["DAC1"] = "%0.5f" %  dev.readRegister(5002)
        results["InternalTemp"] = "%0.5f" %  (dev.readRegister(28) - 273.15)
        
        return dev.serialNumber, results

    def u6Scan(self, dev):
        results = dict()
        
        for i in range(4):
            results["AIN%s" % i] = "%0.5f" % dev.readRegister(i*2)
            
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
            
            results["FIO%s" % i] = "%s %s" % (fioDir, fioState)
        
        results["DAC0"] = "%0.5f" %  dev.readRegister(5000)
        results["DAC1"] = "%0.5f" %  dev.readRegister(5002)
        results["InternalTemp"] = "%0.5f" %  (dev.readRegister(28) - 273.15)
        
        return dev.serialNumber, results

    def listAll(self):
        devices = dict()
        for dev in self.devices.values():
            name = dev.getName()
            devices[str(dev.serialNumber)] = name
            #devices.append({'devType' : devType, 'name' : name, 'serial' : dev.serialNumber, 'productName' : dev.deviceName})
        
        return json.dumps(devices)
        
    def details(self, serial):
        dev = self.devices[serial]
        name = dev.getName()
        return json.dumps({'devType' : dev.devType, 'name' : name, 'serial' : dev.serialNumber, 'productName' : dev.deviceName})
        
    def setFioState(self, serial, fioNumber, state):
        if serial is None:
            dev = self.devices.values()[0]
        else:
            dev = self.devices[serial]
            
        dev.writeRegister(6000 + int(fioNumber), int(state))
        
        if int(state) == 0:
            return "Low"
        else:
            return "High"
            
    def setName(self, serial, name):
        if serial is None:
            dev = self.devices.values()[0]
        else:
            dev = self.devices[serial]
            
        dev.setName(name)
        
        return dev.serialNumber, name
        
        
    def callDeviceFunction(serial, funcName, kwargs):
        if serial is None:
            dev = self.devices.values()[0]
        else:
            dev = self.devices[serial]
        
        if dev.devType == 3:
            classDict = u3Dict
        elif dev.devType == 6:
            classDict = u6Dict
        elif dev.devType == 9:
            classDict = ue9Dict
        
        return dev.serialNumber, dev.__getattribute__(classDict[funcName])(**kwargs)

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
    
    
    def default(self, serial, cmd = None, **kwargs):
        if cmd is None:
            cherrypy.response.headers['content-type'] = "application/json"
            return self.dm.details(serial)
        else:
            pass
            #yield self.header()
            #yield "<p>serial = %s, cmd = %s</p>" % (serial, cmd)
            #yield "<p>kwargs = %s</p>" % str(kwargs)
            #yield self.footer()
    default.exposed = True
    
    def scan(self, serial = None):
        yield self.header()
        
        serialNumber, results = self.dm.scan(serial)
        
        yield "<h2>Scan of %s</h2>" % serialNumber
        yield "<ul>"
        
        for key, value in results.items():
            yield "<li>%s: %s</li>" % (key, value)
        
        yield "</ul>"
        yield self.footer()
            
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

class RootPage:
    def __init__(self, dm):
        self.devices = DevicesPage(dm)
    
    def index(self):
        return serve_file(os.path.join(current_dir , "html/index.html"))
    index.exposed = True



# Main:
if __name__ == '__main__':
    dm = DeviceManager()

    current_dir = os.path.dirname(os.path.abspath(__file__))

    # CherryPy always starts with app.root when trying to map request URIs
    # to objects, so we need to mount a request handler root. A request
    # to '/' will be mapped to HelloWorld().index().
    cherrypy.quickstart(RootPage(dm), config="cherryred.conf")