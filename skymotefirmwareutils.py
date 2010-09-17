# Helper functions
import struct
from LabJackPython import hexWithoutQuotes
import itertools
from hashlib import sha1

BRIDGE_PRODUCT_ID = 1000
TLB_PRODUCT_ID = 2000
DVM_PRODUCT_ID = 2001

MAIN_FW_TYPE = 0
USB_FW_TYPE = 1
USB_BL_FW_TYPE = 2
ETHERNET_FW_TYPE = 3
ETHERNET_BL_FW_TYPE = 4

DEBUG = False

def onePacketAtATime(i):
    return i[0]/32
    #return i[0]/42 max

def parseInt(bytes):
    return struct.unpack('>I', struct.pack("BBBB", *bytes))[0]

class FirmwareFile(object):
    def __init__(self, filename):
        self.filename = filename
        self.fwfile = open(self.filename, 'rb')
        
        # The product this firmware in intended for.
        self.productId = None
        
        # 0 = Main, 1 = USB, 2 = USB BL, 3 = Ethernet, 4 = Ethernet Bl
        self.firmwareType = None
        
        # The version this file provides
        self.providedVersion = None
        
        # The bytes of the FW image
        self.fwImage = None
        
        # A text description of the intended description
        self.intendedDevice = None
        
        # Offset to begin writing
        self.imageOffset = None
        
        self.loadFirmwareFile()

    def checkCompatibility(self, device):
        productId = device.readRegister(65000)
        
        if productId != self.productId:
            raise Exception("Product IDs don't match")
        
    def image(self):
        groups = itertools.groupby(enumerate(self.fwImage), onePacketAtATime)
        address = self.imageOffset
        for i, l in groups:
            data = [ j[1] for j in l ]
            dataLen = len(data)
            values = list(struct.unpack(">"+"H"*(dataLen/2), struct.pack("B"*dataLen, *data)))
            yield address, values
            address += dataLen
        raise StopIteration
    
    def _read(self, numBytes):
        result = self.fwfile.read(numBytes)
        return list(struct.unpack("B"*len(result), result))

    def _loadFirmwareHeader(self):
        headerBytes = self._read(128)
        
        if DEBUG: print "Header: ", hexWithoutQuotes(headerBytes)
        
        if len(headerBytes) != 128:
            raise Exception("Didn't read all of the header")
        
        # Bytes 0-3: 0x4C4A4658
        if headerBytes[:4] != [0x4C, 0x4A, 0x46, 0x58]:
            raise Exception("Error in header's header")
            
        # Bytes 4-7: Intended device
        fwid = parseInt(headerBytes[4:8])
        self.intendedDevice = self.getIntendedDeviceFromFWID(fwid)
        if DEBUG: print "Intended device: ", fwid, self.intendedDevice
        
        #Bytes 8-11: Contained version (reserved, reserved, H, L)
        self.providedVersion = float("%s.%02d" % (headerBytes[10], headerBytes[11]))
        if DEBUG: print "Provides FW:", self.providedVersion
        
        #Bytes 12-15: Required upgrader version (reserved, reserved, H, L)
        #Bytes 16-17: Image number version
        #Bytes 18-19: # of images version
        #Bytes 20-23: Start of next image version
        
        #Bytes 24-27: Length of this image version
        self.imageLength = parseInt(headerBytes[24:28])
        if DEBUG: print "Image length: ", self.imageLength
        
        #Bytes 28-31: Image offset
        self.imageOffset = parseInt(headerBytes[28:32])
        if DEBUG: print "Image offset: ", self.imageLength
        #Bytes 32-35: Number of bytes to include in the SHA.
        #Bytes 36-95: Reserved
        
        #Bytes 96-115: SHA-1 of firmware image
        self.imageSHA1 = struct.pack("B"*len(headerBytes[96:116]), *headerBytes[96:116])
        if DEBUG: print "SHA-1: " , repr(self.imageSHA1)
        
        #Bytes 116-123: Reserved
        #Bytes 124-127: Header checksum
        headerString = struct.pack("B"*124, *headerBytes[:124])
        sha1Hash = sha1(headerString).digest()
        if DEBUG: print "SHA-1 of the Header in hex:", hexWithoutQuotes(struct.unpack("B"*len(sha1Hash), sha1Hash))

    def loadFirmwareFile(self):        
        # self.__fileGetHeader()
        self._loadFirmwareHeader()
        
        # self.__fileGetImage()
        self.fwImage = self._read(self.imageLength)
        
        if len(self.fwImage) != self.imageLength:
            raise Exception("Didn't read whole image.")
        
        imageSha1 = sha1(struct.pack("B"*self.imageLength, *self.fwImage)).digest()
        if imageSha1 != self.imageSHA1:
            if DEBUG: print "Calculated SHA-1 for firmware file:", hexWithoutQuotes(struct.unpack("B"*len(imageSha1), imageSha1))
            if DEBUG: print "Provided SHA-1 from firmware file:", hexWithoutQuotes(struct.unpack("B"*len(self.imageSHA1), self.imageSHA1))
            raise Exception("SHA-1s don't match.")
            
        #print "Firmware image loaded. %s bytes total." % self.imageLength
   
    def getIntendedDeviceFromFWID(self, fwid):
        if fwid == 101000000:
            self.productId = BRIDGE_PRODUCT_ID
            self.firmwareType = MAIN_FW_TYPE
            return "Bridge Main (Jennic) Firmware"
        elif fwid == 101000010:
            self.productId = BRIDGE_PRODUCT_ID
            self.firmwareType = ETHERNET_FW_TYPE
            return "Bridge Ethernet Firmware"
        elif fwid == 101000011:
            self.productId = BRIDGE_PRODUCT_ID
            self.firmwareType = ETHERNET_BL_FW_TYPE
            return "Bridge Ethernet BL Firmware"
        elif fwid == 101000020:
            self.productId = BRIDGE_PRODUCT_ID
            self.firmwareType = USB_FW_TYPE
            return "Bridge USB Firmware"
        elif fwid == 101000021:
            self.productId = BRIDGE_PRODUCT_ID
            self.firmwareType = USB_BL_FW_TYPE
            return "Bridge USB BL Firmware"
        elif fwid == 102000000:
            self.productId = TLB_PRODUCT_ID
            self.firmwareType = MAIN_FW_TYPE
            return "SkyMote TLB Firmware"
        elif fwid == 102001000:
            self.productId = DVM_PRODUCT_ID
            self.firmwareType = MAIN_FW_TYPE
            return "SkyMote DVM Firmware"
