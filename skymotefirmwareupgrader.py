# Defines a class that knows how to upgrade a Skymote's firmware.
import threading
import skymotefirmwareutils
from datetime import datetime
from time import sleep
import sys
import struct
from LabJackPython import LabJackException

class SkymoteFirmwareUpgraderThread(threading.Thread):
    def __init__(self, bridge, fwFilename, upgradeMotes = False, recovery = False):
        threading.Thread.__init__(self)
        self.daemon = True
        self.bridge = bridge
        self.fwFilename = fwFilename
        self.upgradeMotes = upgradeMotes
        self.recovery = recovery
        
        self.running = False
        
        # All print statements will be added as entries in this list.
        self.statusList = []
        
    def log(self, msg):
        print msg
        self.statusList.append(msg)
        
    def run(self):
        self.running = True
        
        self.log("Step 1: Choose a firmware file")

        fwFile = skymotefirmwareutils.FirmwareFile(self.fwFilename)
        self.log("%s version %s (%s)" % (fwFile.intendedDevice, fwFile.providedVersion, self.fwFilename))
        
        #fwFile = skymotefirmwareutils.FirmwareFile("./SMBUSB_firmware_080_09092010.bin")
        #fwFile = skymotefirmwareutils.FirmwareFile("./SMTLB_firmware_037_09132010.bin")
        #fwFile = skymotefirmwareutils.FirmwareFile("./SMB_firmware_031_09132010.bin")
        #print "%s provides %s version %s." % (fwFile.filename, fwFile.intendedDevice, fwFile.providedVersion)
        
        self.log("\nStep 2: Open a Skymote Bridge")
        b = self.bridge
        
        if not self.recovery:
            b.mainFirmwareVersion()
            b.usbFirmwareVersion()
            b.ethernetFirmwareVersion()
            
        self.log("Found a bridge:\n  Serial Number: %s" % b.serialNumber)
        self.log("  Main (Jennic) firmware: %s" % b.mainFWVersion)
        self.log("  USB firmware: %s" % b.usbFWVersion)
        self.log("  Ethernet firmware: %s" % b.ethernetFWVersion)
        
        if not self.upgradeMotes:
            self.log("Doing firmware upgrade on bridge.")
            
            if not self.recovery:
                fwFile.checkCompatibility(b)
            
            b.debug = False
            
            device = b
            
            if fwFile.firmwareType == skymotefirmwareutils.MAIN_FW_TYPE:
                self.sendMainFirmware(device, fwFile)
            elif fwFile.firmwareType == skymotefirmwareutils.USB_FW_TYPE:
                self.sendUsbFirmware(device, fwFile, self.recovery)
            elif fwFile.firmwareType == skymotefirmwareutils.ETHERNET_FW_TYPE:
                self.sendEthernetFirmware(device, fwFile, self.recovery)
            
        else:
            for mote in b.motes:
                self.log("Doing firmware upgrade on mote with unit id = %s" % mote.unitId)
                selectedMote = mote
                
                selectedMote.bridge.debug = False
                
                # Set the device to high power mode:
                selectedMote.writeRegister(59989, 5)
                
                self.log("Waiting for mote to rejoin...")
                sleep(5)
                self.log("Trying to read firmware")
                
                # Read current firmware version
                selectedMote.mainFirmwareVersion()
                self.log("Current Mote firmware = %s" % selectedMote.mainFWVersion)
                
                # Check the device is compatible with the firmware
                fwFile.checkCompatibility(selectedMote)
                
                self.sendMainFirmware(selectedMote, fwFile)
        
        self.running = False

    def sendMainFirmware(self, device, fwFile):
        start = datetime.now()
        
        # Set the flash key
        self.log("Writing Flash Key...")
        device.writeRegister(59000, [0xBAE8, 0xEF64])
        self.log("Done.")
        
        # Erase Flash blocks
        self.log("Erasing Flash...")
        for i in range(23):
            #self.log(str(i)+" ")
            #sys.stdout.flush()
            try:
                device.writeRegister(59074, [0xAA55, 0xC33C, 0x0, i])
            except LabJackException:
                self.log("\nFlash erase failed, retrying...")
                device.writeRegister(59074, [0xAA55, 0xC33C, 0x0, i])
                self.log("Done.")
        self.log("\nDone.")
        
        self.log("Writing Flash...")
        imageLength = len(fwFile.fwImage)
        bytesWritten = 0
        timesThrough = 0
        for address, data in fwFile.image():
            if timesThrough % 10 == 0:
                self.log("Writing Flash bytes %s of %s" % (bytesWritten, imageLength))
            #self.log(str(address)+" ")
            #sys.stdout.flush()
            success = False
            while not success:
                try:
                    device.writeRegister(59020, [0xAA55, 0xC33C, 0x0, address] + data)
                    bytesWritten += 32
                    timesThrough += 1
                    success = True
                except LabJackException:
                    self.log("Write failed, retrying...")
        self.log("Writing Flash bytes %s of %s" % (imageLength, imageLength))
        self.log("Done.")
        
        self.log("Setting start, length, and SHA-1...")
        imageStart = 0
        imageLength = fwFile.imageLength
        imageLength = list(struct.unpack(">HH", struct.pack(">I", imageLength)))
        sha1 = fwFile.imageSHA1
        sha1 = list(struct.unpack(">"+"H"*10, sha1))
            
        device.writeRegister(59080, [0,imageStart] + imageLength + sha1)
        self.log("Done.")
        
        end = datetime.now()
        self.log("Programming complete.")
        self.log("Time to send image: %s" % (end-start))
        
        
        self.log("Resetting Device...")
        device.writeRegister(59999, 0x4c4a)
        self.log("Done.")
        
        self.log("Sleeping for 10 seconds to allow device to finish updating.")
        for i in reversed(range(10)):
            self.log(str(i+1)+" ")
            sys.stdout.flush()
            sleep(1)
        self.log( "")
     
    def sendUsbFirmware(self, device, fwFile, recovery):
        self.log("Upgrading USB Firmware...")
        
        self.log("Jumping to flash mode...")
        if not recovery:
            device.writeRegister(57998, 0x4C4A)
        self.log("Done.")
        
        self.log("Re-opening device handle only...")
        if not recovery:
            device.handle.modbusSocket.send("crh6")
            sleep(10)
        self.log("Done.")
        
        self.log("Erasing Pages...")
        for i in range(10, 32):
            self.log(str(i)+" ")
            sys.stdout.flush()
            try:
                device.writeRegister(57902, [0x0000, i])
            except LabJackException:
                self.log("\nFlash erase failed, retrying...")
                device.writeRegister(57902, [0x0000, i])
                self.log("Done.")
        self.log("\nDone.")
        
        self.log("Writing Pages...")
        for address, data in fwFile.image():
            self.log(str(address)+" ")
            sys.stdout.flush()
            success = False
            while not success:
                try:
                    device.writeRegister(57906, [0x0000, address] + data)
                    success = True
                except LabJackException:
                    self.log("Write failed, retrying...")
        self.log("Done")
        
        self.log("Resetting...")
        device.writeRegister(57999, 0x4C4A)
        if recovery:
            device.close()
            sleep(5)
            device.open(LJSocket = None, handleOnly = True)
        else:
            device.handle.modbusSocket.send("rst5")
            sleep(6)
        self.log("Done")
        
    def sendEthernetFirmware(self, device, fwFile, recovery):
        self.log("Upgrading Ethernet firmware...")
        
        self.log("Jumping to flash mode...")
        try:
            device.writeRegister(56998, 0x4C4A)
            sleep(6)
        except Exception, e:
            if not recovery:
                raise e
            else:
                pass
        self.log("Done.")
        
        self.log("Erasing Pages...")
        for i in range(10, 52):
            self.log(str(i)+" ")
            sys.stdout.flush()
            try:
                device.writeRegister(56902, [0x0000, i])
            except LabJackException:
                self.log("\nFlash erase failed, retrying...")
                device.writeRegister(56902, [0x0000, i])
                self.log("Done.")
        self.log("\nDone.")
        
        self.log("Writing Pages...")
        for address, data in fwFile.image():
            self.log(str(address)+" ")
            sys.stdout.flush()
            success = False
            while not success:
                try:
                    device.writeRegister(56906, [0x0000, address] + data)
                    success = True
                except LabJackException:
                    self.log("Write failed, retrying...")
        self.log("Done")
        
        self.log("Resetting...")
        device.writeRegister(56999, 0x4C4A)
        sleep(5)
        self.log("Done")
            