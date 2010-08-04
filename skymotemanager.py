# SkyMote Manager
from groundedutils import *
import LabJackPython, skymote

class SkyMoteManager(object):
    def __init__(self):
        # The address and port to try to connect to LJSocket
        self.address = LJSOCKET_ADDRESS
        self.port = LJSOCKET_PORT

        # Dictionary of all open bridges. Key = Serial, Value = Object.
        self.bridges = dict()
        
        # Use Direct USB instead of LJSocket.
        self.usbOverride = True
    
    def findBridges(self):
        devs = []
        ljsocketAddress = None
        
        devsObj = LabJackPython.listAll(0x501)
        for dev in devsObj.values():
            devs.append({"serial" : dev["serialNumber"], "prodId" : dev["devType"]})
        
        for dev in devs:
            if dev['prodId'] != 0x501:
                continue
            elif str(dev['serial']) in self.bridges:
                continue
            
            print "Got a bridge... opening."
            d = skymote.Bridge(LJSocket = ljsocketAddress, serial = dev['serial'])
            try:
                d.ethernetFirmwareVersion()
            except:
                d.ethernetFWVersion = "(No Ethernet)"
            d.usbFirmwareVersion()
            d.mainFirmwareVersion()
            d.productName = "SkyMote Bridge"
            
            self.bridges["%s" % dev['serial']] = d
        
        for b in self.bridges.values():
            try:
                b.motes = b.listMotes()
            except LabJackPython.LabJackException:
                print "Removing %s from bridges list" % b.serialNumber
                b.close()
                self.bridges.pop(str(b.serialNumber))
                continue
            
            for mote in b.motes:
                mote.nickname = mote.name
                mote.mainFirmwareVersion()
                mote.devType = mote.readRegister(65000)
                if mote.devType == 2000:
                    mote.productName = "SkyMote TLB"
                else:
                    mote.productName = "SkyMote Unknown Type"
        
        return self.bridges

    def scan(self):
        results = dict()
        
        for b in self.bridges.values():
            for mote in b.listMotes():
                results[str(mote.moteId)] = mote.sensorSweep()
                
        return results



















