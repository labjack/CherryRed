# Defines a class that knows how to upgrade a Skymote's firmware.
import threading
import skymotefirmwareutils
from datetime import datetime
from time import sleep
import sys
import struct
from LabJackPython import LabJackException

def sendUsbFirmware(device, fwFile, recovery):
    print "Go go USB upgrade..."
    
    print "Jumping to flash mode..."
    if not recovery:
        device.writeRegister(57998, 0x4C4A)
    print "Done."
    
    print "Re-opening device handle only..."
    if not recovery:
        device.handle.modbusSocket.send("crh6")
        sleep(10)
    print "Done."
    
    print "Erasing Pages..."
    for i in range(10, 32):
        print str(i)+" ",
        sys.stdout.flush()
        try:
            device.writeRegister(57902, [0x0000, i])
        except LabJackException:
            print "\nFlash erase failed, retrying..."
            device.writeRegister(57902, [0x0000, i])
            print "Done."
    print "\nDone."
    
    print "Writing Pages..."
    for address, data in fwFile.image():
        print str(address)+" ",
        sys.stdout.flush()
        success = False
        while not success:
            try:
                device.writeRegister(57906, [0x0000, address] + data)
                success = True
            except LabJackException:
                print "Write failed, retrying..."
    print "Done"
    
    print "Resetting..."
    device.writeRegister(57999, 0x4C4A)
    if recovery:
        device.close()
        sleep(5)
        device.open(LJSocket = None, handleOnly = True)
    else:
        device.handle.modbusSocket.send("rst5")
        sleep(6)
    print "Done"

def sendEthernetFirmware(device, fwFile, recovery):
    print "Go go Ethernet upgrade..."
    
    print "Jumping to flash mode..."
    try:
        device.writeRegister(56998, 0x4C4A)
        sleep(6)
    except Exception, e:
        if not recovery:
            raise e
        else:
            pass
    print "Done."
    
    print "Erasing Pages..."
    for i in range(10, 52):
        print str(i)+" ",
        sys.stdout.flush()
        try:
            device.writeRegister(56902, [0x0000, i])
        except LabJackException:
            print "\nFlash erase failed, retrying..."
            device.writeRegister(56902, [0x0000, i])
            print "Done."
    print "\nDone."
    
    print "Writing Pages..."
    for address, data in fwFile.image():
        print str(address)+" ",
        sys.stdout.flush()
        success = False
        while not success:
            try:
                device.writeRegister(56906, [0x0000, address] + data)
                success = True
            except LabJackException:
                print "Write failed, retrying..."
    print "Done"
    
    print "Resetting..."
    device.writeRegister(56999, 0x4C4A)
    sleep(5)
    print "Done"


def sendMainFirmware(device, fwFile):
    start = datetime.now()
    
    # Set the flash key
    print "Writing Flash Key..."
    device.writeRegister(59000, [0xBAE8, 0xEF64])
    print "Done."
    
    # Erase Flash blocks
    print "Erasing Flash..."
    for i in range(23):
        print str(i)+" ",
        sys.stdout.flush()
        try:
            device.writeRegister(59074, [0xAA55, 0xC33C, 0x0, i])
        except LabJackException:
            print "\nFlash erase failed, retrying..."
            device.writeRegister(59074, [0xAA55, 0xC33C, 0x0, i])
            print "Done."
    print "\nDone."
    
    print "Writing Flash..."
    for address, data in fwFile.image():
        print str(address)+" ",
        sys.stdout.flush()
        success = False
        while not success:
            try:
                device.writeRegister(59020, [0xAA55, 0xC33C, 0x0, address] + data)
                success = True
            except LabJackException:
                print "Write failed, retrying..."
    print "Done."
    
    print "Setting start, length, and SHA-1..."
    imageStart = 0
    imageLength = fwFile.imageLength
    imageLength = list(struct.unpack(">HH", struct.pack(">I", imageLength)))
    sha1 = fwFile.imageSHA1
    sha1 = list(struct.unpack(">"+"H"*10, sha1))
        
    device.writeRegister(59080, [0,imageStart] + imageLength + sha1)
    print "Done."
    
    end = datetime.now()
    print "Programming complete."
    print "Time to send image:", end-start
    
    
    print "Resetting Device..."
    device.writeRegister(59999, 0x4c4a)
    print "Done."
    
    print "Sleeping for 10 seconds to allow device to finish updating."
    for i in reversed(range(10)):
        print str(i+1)+" ",
        sys.stdout.flush()
        sleep(1)
    print ""

class SkymoteFirmwareUpgraderThread(threading.Thread):
    def __init__(self, bridge, fwFilename, upgradeMotes = False, recovery = False):
        threading.Thread.__init__(self)
        self.daemon = True
        self.bridge = bridge
        self.fwFilename = fwFilename
        self.upgradeMotes = upgradeMotes
        self.recovery = recovery
        
        # All print statements will be added as entries in this list.
        self.statusList = []
        
    def log(self, msg):
        self.statusList.append(msg)
        
    def run(self):        
        print "Step 1: Choose a firmware file"
        

        fwFile = skymotefirmwareutils.FirmwareFile(self.fwFilename)
        print "%s version %s (%s)" % (fwFile.intendedDevice, fwFile.providedVersion, self.fwFilename)
        
        #fwFile = skymotefirmwareutils.FirmwareFile("./SMBUSB_firmware_080_09092010.bin")
        #fwFile = skymotefirmwareutils.FirmwareFile("./SMTLB_firmware_037_09132010.bin")
        #fwFile = skymotefirmwareutils.FirmwareFile("./SMB_firmware_031_09132010.bin")
        #print "%s provides %s version %s." % (fwFile.filename, fwFile.intendedDevice, fwFile.providedVersion)
        
        print "\nStep 2: Open a Skymote Bridge"
        b = self.bridge
        
        if not self.recovery:
            b.mainFirmwareVersion()
            b.usbFirmwareVersion()
            b.ethernetFirmwareVersion()
            
        print "Found a bridge:\n  Serial Number: %s" % b.serialNumber
        print "  Main (Jennic) firmware: %s" % b.mainFWVersion
        print "  USB firmware: %s" % b.usbFWVersion
        print "  Ethernet firmware: %s" % b.ethernetFWVersion
        
        if not self.upgradeMotes:
            print "Doing firmware upgrade on bridge."
            
            if not self.recovery:
                fwFile.checkCompatibility(b)
            
            b.debug = False
            
            device = b
            
            if fwFile.firmwareType == skymotefirmwareutils.MAIN_FW_TYPE:
                sendMainFirmware(device, fwFile)
            elif fwFile.firmwareType == skymotefirmwareutils.USB_FW_TYPE:
                sendUsbFirmware(device, fwFile, self.recovery)
            elif fwFile.firmwareType == skymotefirmwareutils.ETHERNET_FW_TYPE:
                sendEthernetFirmware(device, fwFile, self.recovery)
            
        else:
            for mote in b.motes:
                print "Doing firmware upgrade on mote with unit id =", selectedUnitId
                selectedMote = mote
                
                selectedMote.bridge.debug = False
                
                # Set the device to high power mode:
                selectedMote.writeRegister(59989, 5)
                
                print "Waiting for mote to rejoin..."
                sleep(5)
                print "Trying to read firmware"
                
                # Read current firmware version
                selectedMote.mainFirmwareVersion()
                print "Current Mote firmware =", selectedMote.mainFWVersion
                
                # Check the device is compatible with the firmware
                fwFile.checkCompatibility(selectedMote)
                
                sendMainFirmware(selectedMote, fwFile)
            