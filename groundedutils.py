import re

U3_MIN_FIRMWARE_VERSION = 1.26
U6_MIN_FIRMWARE_VERSION = 1.15
UE9_MIN_FIRMWARE_VERSION = (2.13, 1.5)

# Driver Versions:
UD_DRIVER_REQUIREMENT = 3.15
EXODRIVER_REQUIREMENT = 2.0

LJSOCKET_ADDRESS = "localhost"
LJSOCKET_PORT = "6000"

ANALOG_TYPE = "analogIn"
DIGITAL_OUT_TYPE = "digitalOut"
DIGITAL_IN_TYPE = "digitalIn"

FLOAT_FORMAT = "%0.3f"

DAC_DICT = { 5000: "DAC0", 5002: "DAC1" } 

GOOGLE_DOCS_SCOPE = 'https://docs.google.com/feeds/'

def sanitize(name):
    """
    >>> sanitize("My U3-HV")
    'My U3-HV'
    >>> sanitize("My U3-HV%$#@!")
    'My U3-HV'
    >>> sanitize("My_Underscore_Name")
    'My_Underscore_Name'
    """
    p = re.compile('[^a-zA-Z0-9_ -]')
    return p.sub('', name)

def kelvinToFahrenheit(value):
    """Converts Kelvin to Fahrenheit"""
    # F = K * (9/5) - 459.67
    return value * (9.0/5.0) - 459.67

def internalTempDict(kelvinTemp):
    # Returns Kelvin, converting to Fahrenheit
    # F = K * (9/5) - 459.67
    internalTemp = kelvinToFahrenheit(kelvinTemp)
    return {'connection' : "Internal Temperature", 'state' : (FLOAT_FORMAT + " &deg;F") % internalTemp, 'value' : FLOAT_FORMAT % internalTemp, 'chType' : "internalTemp", "disabled" : True}
    
    
def createTimerChoicesList(devType):
    """
    Given a device type, returns which pins are valid to start timers.
    """
    if devType == 9:
        return ((0, 'FIO0'), )
    elif devType == 3:
        return ((4, "FIO4"), (5, "FIO5"), (6, "FIO6"), (7, "FIO7"), (8, "EIO0"))
    else:
        return ((0, "FIO0"), (1, "FIO1"), (2, "FIO2"), (3, "FIO3"), (4, "FIO4"), (5, "FIO5"), (6, "FIO6"), (7, "FIO7"), (8, "EIO0"))


def createTimerModeToHelpUrlList(devType):
    """
    Given a device type, returns a list of urls pointing to the user's guide
    for timer modes.
    """
    urllist = []
    if devType == 9:
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.1")
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.2")
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.3")
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.3")
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.4")
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.5")
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.6")
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.7")
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.8")
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.9")
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.10")
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.10")
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.11")
        urllist.append("http://labjack.com/support/ue9/users-guide/2.10.1.11")
    elif devType == 6:
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.1")
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.2")
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.3")
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.3")
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.4")
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.5")
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.6")
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.7")
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.8")
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.9")
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.10")
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.10")
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.11")
        urllist.append("http://labjack.com/support/u6/users-guide/2.9.1.11")
    else:
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.1")
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.2")
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.3")
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.3")
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.4")
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.5")
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.6")
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.7")
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.8")
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.9")
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.10")
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.10")
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.11")
        urllist.append("http://labjack.com/support/u3/users-guide/2.9.1.11")
    
    return urllist

def deviceAsDict(dev):
    """ Returns a dictionary representation of a device.
    """
    returnDict = {'devType' : dev.devType, 'serial' : dev.serialNumber, 'productName' : dev.deviceName, 'firmware' : None, 'localId' : dev.localId, 'meetsFirmwareRequirements' : dev.meetsFirmwareRequirements}
    
    if dev.devType == 9:
        returnDict['DHCPEnabled'] = dev.DHCPEnabled
        returnDict['ipAddress'] = dev.ipAddress
        returnDict['subnet'] = dev.subnet
        returnDict['gateway'] = dev.gateway
        returnDict['portA'] = dev.portA
        returnDict['portB'] = dev.portB
        returnDict['macAddress'] = dev.macAddress
        
        name = dev.getName()
        firmware = [dev.commFWVersion, dev.controlFWVersion]
    elif dev.devType == 0x501:
        firmware = [dev.ethernetFWVersion, dev.usbFWVersion, dev.mainFWVersion]
        returnDict['unitId'] = dev.unitId
        returnDict['numMotes'] = len(dev.motes)
        name = dev.nameCache
    else:
        name = dev.getName()
        firmware = dev.firmwareVersion
        
    returnDict['name'] = name
    returnDict['firmware'] = firmware
    
    return returnDict


def replaceUnderscoresWithColons(filename):
    """
    Takes a name, and replaces "__" with ":". Used for logfiles and
    configfiles so they'll look pretty.
    """
    splitFilename = filename.split(" ")
    if len(splitFilename) > 1:
        replacedFilename = splitFilename[1].replace("__", ":").replace("__", ":")
        splitFilename[1] = replacedFilename
        newName = " ".join(splitFilename)
        return newName
    else:
        return filename