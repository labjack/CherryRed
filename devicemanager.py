# devicemanager.py - because the device manager had grown too big.

# Local Imports
import xmppconnection, logger, scheduler
from fio import FIO, UE9FIO
from groundedutils import *

# Required Packages Imports
# - PyParsing
from Autoconvert import autoConvert

# - LabJackPython
import LabJackPython, u3, u6, ue9

# Standard Library Imports
from threading import Lock, Event
import time

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

# Maps all the functions of a device class to lower case.
u3Dict = buildLowerDict(u3.U3)
u6Dict = buildLowerDict(u6.U6)
ue9Dict = buildLowerDict(ue9.UE9)

class DeviceManager(object):
    """
    The DeviceManager class will manage all the open connections to LJSocket.
    
    It is also responsible for knowing which devices are logging and connected
    to CloudDot. On shutdown, it must insure those threads get killed.
    """
    def __init__(self):
        # The address and port to try to connect to LJSocket
        self.address = LJSOCKET_ADDRESS
        self.port = LJSOCKET_PORT
        
        # For connecting devices to CloudDot
        self.username = None
        self.apikey = None
        
        # Dictionary of all open devices. Key = Serial, Value = Object.
        self.devices = dict()
        
        # Dictionary of all devices connected to CloudDot.
        # Key = Serial, Value = Thread
        self.xmppThreads = dict()
        
        # A Scheduler to insure that logging is done at regular intervals.
        self.loggingScheduler = scheduler.Scheduler()
        
        # Dictionary of all devices which are logging.
        # Key = Serial, Value = Thread
        self.loggingThreads = dict()
        
        # Used to prevent race conditions with updating the loggingThreads dict
        self.loggingThreadLock = Lock()
        
        # There are times when we need to pause scans for a moment.
        self.scanEvent = Event()
        self.scanEvent.set()
        
        # Use Direct USB instead of LJSocket.
        self.usbOverride = False
        
        try:
            self.updateDeviceDict()
            self.connected = True
        except Exception:
            try:
                self.usbOverride = True
                self.updateDeviceDict()
                self.connected = True
            except Exception:
                self.connected = False
            
        
        print self.devices
    
    def getDevice(self, serial):
        """
        You give it a serial, you get a device.
        """
        if serial is None:
            return self.devices.values()[0]
        elif isinstance(serial, LabJackPython.Device):
            return serial
        else:
            return self.devices[serial]
    
    def makeLoggingSummary(self):
        """
        Builds a list of dictionaries which contain information about what a
        device is logging.
        
        Contains the following keys:
        devName, the device's name.
        headers, a string of all the channels being logged.
        filename, the file being logged to.
        serial, the device's serial number.
        logname, the pretty version of filename.
        stopurl, a url that will stop the device from logging.
        """
        loggingList = []
        
        for serial, thread in self.loggingThreads.items():
            headers = list(thread.headers)
            headers.remove("Timestamp")
            loggingList.append({ "devName" : thread.name, "headers" : ", ".join(headers), "filename" : thread.filename, "serial" : serial, "logname" : replaceUnderscoresWithColons(thread.filename), "stopurl" : "/logs/stop?serial=%s" % serial})
        
        return loggingList
    
    def startDeviceLogging(self, serial, headers = None):
        d = self.getDevice(serial)
        returnValue = False
        
        try:
            self.loggingThreadLock.acquire()
            if str(d.serialNumber) not in self.loggingThreads:
                lt = logger.LoggingThread(self, d.serialNumber, d.getName(), headers)
                e = self.loggingScheduler.addReschedulingEvent(1, lt.log)
                lt.event = e
                self.loggingThreads[str(d.serialNumber)] = lt
                
                returnValue = True
            else:
                sn = str(d.serialNumber)
                if self.loggingThreads[sn].headers != headers:
                    lt = self.loggingThreads[sn]
                    lt.stop()
                    if headers:
                        lt = logger.LoggingThread(self, d.serialNumber, d.getName(), headers)
                        e = self.loggingScheduler.addReschedulingEvent(1, lt.log)
                        lt.event = e
                        self.loggingThreads[str(d.serialNumber)] = lt
                        returnValue = True
                    else:
                        self.loggingThreads.pop(sn)
                        returnValue = True
                else:
                     returnValue =  False
        finally:
            self.loggingThreadLock.release()
        
        return returnValue    
        
    def stopDeviceLogging(self, serial):
        d = self.getDevice(serial)
        returnValue = False
        
        try:
            self.loggingThreadLock.acquire()
            if str(d.serialNumber) in self.loggingThreads:
                lt = self.loggingThreads.pop(str(d.serialNumber))
                lt.stop()
                returnValue = True
            else:
                returnValue = False
        finally:
            self.loggingThreadLock.release()
        
        return returnValue
    
    def connectDeviceToCloudDot(self, serial):
        """
        Spawns a thread to connect a device to CloudDot. If the device is 
        already connected, the function returns false.
        """
        d = self.getDevice(serial)
        
        if str(d.serialNumber) not in self.xmppThreads:
            xt = xmppconnection.XmppThread(d, self, password = self.apikey)
            xt.start()
            self.xmppThreads[str(d.serialNumber)] = xt
            
            return True
        else:
            return False
            
    def disconnectDeviceFromCloudDot(self, serial):
        """
        Stops the thread connecting a device to CloudDot. If the device is 
        not connected, the function returns false.
        """
        d = self.getDevice(serial)
        
        if str(d.serialNumber) in self.xmppThreads:
            xt = self.xmppThreads.pop(str(d.serialNumber))
            xt.stop()
            return True
        else:
            return False
        
    def shutdownThreads(self):
        """
        Called when cherrypy starts shutting down, shutdownThreads stops all the
        logging and xmpp threads.
        """
        for s, thread in self.xmppThreads.items():
            thread.stop()
            
        self.loggingScheduler.shutdown()
    
    def getFioInfo(self, serial, inputNumber):
        dev = self.getDevice(serial)
        
        if inputNumber in DAC_DICT.keys():
            returnDict = { "state" : dev.readRegister(inputNumber), "label" : DAC_DICT[inputNumber], "connectionNumber" : inputNumber, "chType" : "DAC" }
        elif dev.devType == 9:
            returnDict = UE9FIO.getFioInfo(dev, inputNumber)
        else:
            returnDict = dev.fioList[inputNumber].asDict()
        
        # devType, productName
        returnDict['device'] = deviceAsDict(dev)
        
        return returnDict
        
    def updateFio(self, serial, inputConnection):
        dev = self.getDevice(serial)
        try:
            self.scanEvent.clear()
            if dev.devType == 9:
                UE9FIO.updateFIO(dev, inputConnection)
            else:
                current = dev.fioList[ inputConnection.fioNumber ]
                current.transform(dev, inputConnection)    
                self.remakeFioList(dev)
        finally:
            self.scanEvent.set()
    
    def remakeFioList(self, serial):
        dev = self.getDevice(serial)
        
        if dev.devType == 3:
            fioList, fioFeedbackCommands = self.makeU3FioList(dev)
            dev.fioList = fioList
            dev.fioFeedbackCommands = fioFeedbackCommands
        elif dev.devType == 6:
            self.remakeU6AnalogCommandList(dev)
    
    def remakeU6AnalogCommandList(self, dev):
        analogCommandList = list()
        for i in range(14):
            ain = dev.fioList[i]
            analogCommandList.append( ain.makeFeedbackCommand(dev) )
        
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
            fios.append( FIO(i+14, label = label % (i + labelOffset), chType = (DIGITAL_IN_TYPE if fioDir == 0 else DIGITAL_OUT_TYPE), state = fioState) )
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
        
            if i < 16 and (( analog >> (i + labelOffset)) & 1):
                fios.append( FIO(i) )
            else:
                fioDir = dev.readRegister(6100 + i)
                fioState = dev.readRegister(6000 + i)
                
                fios.append( FIO(i, label % (i + labelOffset), (DIGITAL_IN_TYPE if fioDir == 0 else DIGITAL_OUT_TYPE), fioState) )
        
        fioFeedbackCommands = list()
        for fio in fios:
            fioFeedbackCommands.append(fio.makeFeedbackCommand(dev))
        
        return fios, fioFeedbackCommands
        
    def _addTimerModesToDevice(self, dev, numberOfTimerModes):
        dev.timerModes = [ 10 ] * numberOfTimerModes
        if dev.meetsFirmwareRequirements:
            for i in range(dev.readRegister(50501)):
                dev.timerModes[i] = dev.readRegister(7100, format=">HH")[0]
    
    def updateDeviceDict(self):
        try:
            if self.usbOverride:
                self.scanEvent.wait()
                self.scanEvent.clear()
                ljsocketAddress = None
                devs = list()
                
                devCount = LabJackPython.deviceCount(None)
                
                for serial, dev in self.devices.items():
                    dev.close()
                    self.devices.pop(str(serial))
                
                devsObj = LabJackPython.listAll(3)
                for dev in devsObj.values():
                    devs.append({"serial" : dev["serialNumber"], "prodId" : dev["devType"]})
                
                devsObj = LabJackPython.listAll(6)
                for dev in devsObj.values():
                    devs.append({"serial" : dev["serialNumber"], "prodId" : dev["devType"]})
                
                devsObj = LabJackPython.listAll(9)
                for dev in devsObj.values():
                    devs.append({"serial" : dev["serialNumber"], "prodId" : dev["devType"]})
                    
                print "usbOverride:",devs
                    
            else:
                ljsocketAddress = "%s:%s" % (self.address, self.port)
                devs = LabJackPython.listAll(ljsocketAddress, LabJackPython.LJ_ctLJSOCKET)
            
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
                        d.getCalibrationData()
                        
                        d.meetsFirmwareRequirements = True
                        if float(d.firmwareVersion) < U3_MIN_FIRMWARE_VERSION:
                            d.meetsFirmwareRequirements = False
                        
                    except Exception, e:
                        raise Exception( "Error with configU3: %s" % e )
                        
                    try:
                        #d.debug = True
                        fioList, fioFeedbackCommands = self.makeU3FioList(d)
                        d.fioList = fioList
                        d.fioFeedbackCommands = fioFeedbackCommands
                        
                        self._addTimerModesToDevice(d, 2)
                    except Exception, e:
                        print "making u3 fio list: %s" % e
                        raise Exception( "making u3 fio list: %s" % e )
                    
                elif dev['prodId'] == 6:
                    try:
                        d = u6.U6(LJSocket = ljsocketAddress, serial = dev['serial'])
                        d.configU6()
                        d.getCalibrationData()
                        
                        d.meetsFirmwareRequirements = True
                        if float(d.firmwareVersion) < U6_MIN_FIRMWARE_VERSION:
                            d.meetsFirmwareRequirements = False
                        
                        fios, analogCommandList, digitalCommandList = self.makeU6FioList(d)
                        d.fioList = fios
                        d.analogCommandList = analogCommandList
                        d.digitalCommandList = digitalCommandList
                        self._addTimerModesToDevice(d, 4)
                    except Exception, e:
                        print "In opening a U6: %s" % e
                    
                elif dev['prodId'] == 9:
                    d = ue9.UE9(LJSocket = ljsocketAddress, serial = dev['serial'])
                    d.commConfig()
                    d.controlConfig()
                    
                    d.meetsFirmwareRequirements = True
                    if float(d.controlFWVersion) < UE9_MIN_FIRMWARE_VERSION[0]:
                        d.meetsFirmwareRequirements = False
                    elif float(d.commFWVersion) < UE9_MIN_FIRMWARE_VERSION[1]:
                        d.meetsFirmwareRequirements = False
                    
                    self._addTimerModesToDevice(d, 6)
                    
                    UE9FIO.setupNewDevice(d)
                elif dev['prodId'] == 0x501:
                    continue
                else:
                    raise Exception("Unknown device type")
                
                d.scanCache = (0, None)
                d.timerCounterCache = None
                self.devices["%s" % dev['serial']] = d
            
            # Remove the disconnected devices
            for serial in self.devices.keys():
                if serial not in serials:
                    print "Removing device with serial = %s" % serial
                    self.devices[str(serial)].close()
                    self.devices.pop(str(serial))
        except Exception, e:
            print type(e), e
            raise e
        finally:
            self.scanEvent.set()
                   
    def closeDevice(self, dev):
        serial = str(dev.serialNumber)
        self.stopDeviceLogging(serial)
        self.disconnectDeviceFromCloudDot(serial)
        
        dev.close()
        self.devices.pop(serial)

    def scan(self, serial = None, noCache = False):
        self.scanEvent.wait()
        dev = self.getDevice(serial)
        
        if not dev.meetsFirmwareRequirements:
            return (False, False)
        
        now = int(time.time())
        if noCache or (now - dev.scanCache[0]) >= 1:
            try:
                self.scanEvent.clear()
                if dev.devType == 3:
                    result = self.u3Scan(dev)
                elif dev.devType == 6:
                    result = self.u6Scan(dev)
                elif dev.devType == 9:
                    result = self.ue9Scan(dev)
                    
                dev.scanCache = (now, result)
                return result
            except LabJackPython.LabJackException, e:
                print "Caught LabJackException:\n%s" % e
                self.closeDevice(dev)
                return serial, []
            finally:
                self.scanEvent.set()
        else:
            return dev.scanCache[1]
    

    def readTimer(self, dev, timerNumber):
        timer = None
        timerString = None
        
        if dev.timerModes[timerNumber] == 8:
            # 8 is Quadrature, which is a signed value.
            timer = dev.readRegister(7200 + (2 * timerNumber), format=">i")
        elif dev.timerModes[timerNumber] in [0, 1]:
            # 0 and 1 are PWM so we will show Duty Cycle
            timer = dev.readRegister(7100 + (2 * timerNumber), format=">HH")
            timer = float(65536 - timer[1]) / 65536
            timerString = "%.2f%%" % (timer*100) 
        else:
            timer = dev.readRegister(7200 + (2 * timerNumber))
            
        # Reset value
        if dev.timerModes[timerNumber] in [2, 3, 12, 13]:
            dev.writeRegister(7200 + (2 * timerNumber), 0)
        
        if timerString is None:
            timerString = timer
        
        infoDict = {'connection' : "Timer %s" % timerNumber, 'state' : "%s" % timerString, 'value' : "%s" % timer}
        infoDict['chType'] = ("timer")
        
        return infoDict
        
    def readCounter(self, dev, counterNumber):
        counter = dev.readRegister(7300 + (2 * counterNumber))
        infoDict = {'connection' : "Counter %s" % counterNumber, 'state' : "%s" % counter, 'value' : "%s" % counter}
        infoDict['chType'] = ("counter")
        
        return infoDict

    def _insertTimersAndCountersIntoScanResults(self, dev, results, offset, numTimers, readCounter0, readCounter1, fioLabelOffset = 0):
        for i in range(numTimers):
            results[offset] = self.readTimer(dev, i)
            results[offset]['connectionNumber'] = i
            results[offset]['connection'] += " (FIO%i)" % (offset - fioLabelOffset)
            offset += 1
            
        if readCounter0:
            results[offset] = self.readCounter(dev, 0)
            results[offset]['connectionNumber'] = 0
            results[offset]['connection'] += " (FIO%i)" % (offset - fioLabelOffset)
            offset += 1
        
        if readCounter1:
            results[offset] = self.readCounter(dev, 1)
            results[offset]['connectionNumber'] = 1
            results[offset]['connection'] += " (FIO%i)" % (offset - fioLabelOffset)
            offset += 1

    def _appendDacsToScanResults(self, dev, results):
        for register, label in DAC_DICT.items():
            dacState = dev.readRegister(register)
            results.append({'connection' : label, 'connectionNumber' : register, 'state' : FLOAT_FORMAT % dacState, 'value' : FLOAT_FORMAT % dacState})

    def _appendExtraDataToScanResults(self, dev, results):
        if str(dev.serialNumber) in self.loggingThreads:
            headers = self.loggingThreads[str(dev.serialNumber)].headers
        else:
            headers = []
            
        for result in results:
            result['devType'] = dev.devType
            if "disabled" not in result:
                result['disabled'] = False
            
            if result['connection'] in headers:
                result['logging'] = True
            else:
                result['logging'] = False
                
        return results

    def ue9Scan(self, dev):
        results = list()
        
        feedbackResults = dev.feedback(AINMask = 0xef, AIN14ChannelNumber = dev.AIN14ChannelNumber, AIN15ChannelNumber = dev.AIN15ChannelNumber, Resolution = dev.Resolution, SettlingTime = dev.SettlingTime, AIN1_0_BipGain = dev.AIN1_0_BipGain, AIN3_2_BipGain = dev.AIN3_2_BipGain, AIN5_4_BipGain  = dev.AIN5_4_BipGain, AIN7_6_BipGain = dev.AIN7_6_BipGain, AIN9_8_BipGain = dev.AIN9_8_BipGain, AIN11_10_BipGain = dev.AIN11_10_BipGain, AIN13_12_BipGain = dev.AIN13_12_BipGain)
        
        for i in range(14):
            c = "AIN%s" % i
            v = feedbackResults[c]
            results.append({'connection' : c, 'state' : FLOAT_FORMAT % v, 'value' : FLOAT_FORMAT % v, 'chType' : ANALOG_TYPE, 'connectionNumber' : i})
            
        dirs = feedbackResults["FIODir"]
        states = feedbackResults["FIOState"]
        for i in range(8):
            f = FIO(i+14, label = "FIO%s" % i)
            d = (dirs >> i) & 1
            s = (states >> i) & 1
            
            results.append(f.parseFioResults(d, s))
            
        dirs = feedbackResults["EIODir"]
        states = feedbackResults["EIOState"]
        for i in range(8):
            f = FIO(i+14+8, label = "EIO%s" % i)
            d = (dirs >> i) & 1
            s = (states >> i) & 1
            
            results.append(f.parseFioResults(d, s))
            
        dirs = feedbackResults["CIODir"]
        states = feedbackResults["CIOState"]
        for i in range(4):
            f = FIO(i+14+16, label = "CIO%s" % i)
            d = (dirs >> i) & 1
            s = (states >> i) & 1
            
            results.append(f.parseFioResults(d, s))
            
        dirs = feedbackResults["MIODir"]
        states = feedbackResults["MIOState"]
        for i in range(3):
            f = FIO(i+34, label = "MIO%s" % i)
            d = (dirs >> i) & 1
            s = (states >> i) & 1
            
            results.append(f.parseFioResults(d, s))
            
        nte, cm = dev.readRegister(50501, numReg = 2)
        offset = 14
        
        for i in range(nte):
            if i < 3:
                timer = feedbackResults["Timer%s" % (('A', 'B', 'C')[i]) ]
                results[offset] = {'connection' : "Timer %s" % i, 'state' : "%s" % timer, 'value' : "%s" % timer, "chType" : "timer", 'connectionNumber' : i}
            else:
                results[offset] = self.readTimer(dev, i)
            results[offset]['connection'] += " (FIO%i)" % (offset-14)
            offset += 1
                
        # Counter 0
        if bool(cm & 1):
            counter = feedbackResults["Counter0"]
            results[offset] = {'connection' : "Counter 0", 'state' : "%s" % counter, 'value' : "%s" % counter, "chType" : "counter", 'connectionNumber' : 0}
            results[offset]['connection'] += " (FIO%i)" % (offset-14)
            offset += 1
        
        # Counter 1
        if bool(cm & 2):
            counter = feedbackResults["Counter1"]
            results[offset] = {'connection' : "Counter 1", 'state' : "%s" % counter, 'value' : "%s" % counter, "chType" : "counter", 'connectionNumber' : 1}
            results[offset]['connection'] += " (FIO%i)" % (offset-14)
            offset += 1
        
        # DAC values
        self._appendDacsToScanResults(dev, results)
        
        results.append(internalTempDict(dev.readRegister(266)))
        
        return dev.serialNumber, self._appendExtraDataToScanResults(dev, results)

    def u3Scan(self, dev):
        fioAnalog = dev.readRegister(50590)
        eioAnalog = dev.readRegister(50591)
        
        results = list()
        
        rawResponse = dev.getFeedback(dev.fioFeedbackCommands)
        for i, bits in enumerate(rawResponse):
            fio = dev.fioList[i]
            
            if fio.chType == ANALOG_TYPE:
                isLowVoltage = True
                if dev.deviceName.endswith("HV") and i < 4:
                    isLowVoltage = False
                
                isSingleEnded = True
                isSpecialChannel = False
                if fio.negChannel == 32:
                    isSpecialChannel = True
                elif fio.negChannel != 31:
                    isSingleEnded = False
                    
                value = dev.binaryToCalibratedAnalogVoltage(bits, isLowVoltage, isSingleEnded, isSpecialChannel, i)
                results.append( fio.parseAinResults(value) )
            elif fio.chType == DIGITAL_IN_TYPE:
                #value = bits["%ss" % (fio.label[:3])]
                #value = (value >> int(fio.label[3:])) & 1
                results.append( fio.parseFioResults(0, bits) )
            else:
                #value = bits["%ss" % (fio.label[:3])]
                #value = (value >> int(fio.label[3:])) & 1
                results.append( fio.parseFioResults(1, bits) )
        
        # Timer/Counter values
        ioResults = dev.configIO()
        offset = ioResults['TimerCounterPinOffset']
        self._insertTimersAndCountersIntoScanResults(dev, results, offset, ioResults['NumberOfTimersEnabled'], ioResults['EnableCounter0'], ioResults['EnableCounter1'])

        # DAC values
        self._appendDacsToScanResults(dev, results)
        
        results.append(internalTempDict(dev.readRegister(60)))
        
        return dev.serialNumber, self._appendExtraDataToScanResults(dev, results)

    def u6Scan(self, dev):
        results = list()
        
        # If the timerCounterCache is empty, fill it.
        if dev.timerCounterCache is None:
            self.readTimerCounterConfig(dev)
        
        # Read and convert all the AINs
        analogInputs = dev.getFeedback( dev.analogCommandList )
        for i, value in enumerate(analogInputs):
            fio = dev.fioList[i]
            v = dev.binaryToCalibratedAnalogVoltage(fio.gainIndex, value)
            
            results.append(fio.parseAinResults(v))
        
        # Read all the FIOs' states and directions
        digitalDirections, digitalStates = dev.getFeedback( dev.digitalCommandList )
        for i in range(dev.numberOfDigitalIOs):
            fio = dev.fioList[ i + dev.numberOfAnalogIn ]
            
            direction = ((digitalDirections[fio.label[:3]]) >> int(fio.label[3:])) & 1
            state = ((digitalStates[fio.label[:3]]) >> int(fio.label[3:])) & 1
            
            dioDict = fio.parseFioResults(direction, state)
            
            results.append( dioDict )
        
        # Replace FIOs if there are timers enabled.
        offset = dev.timerCounterCache['offset'] + dev.numberOfAnalogIn
        timers = self._convertTimerSettings(dev.timerCounterCache, onlyEnabled = True)
        self._insertTimersAndCountersIntoScanResults(dev, results, offset, len(timers), dev.timerCounterCache['counter0Enabled'], dev.timerCounterCache['counter1Enabled'], fioLabelOffset = dev.numberOfAnalogIn)
                
        # DAC values
        self._appendDacsToScanResults(dev, results)
        
        results.append(internalTempDict(dev.readRegister(28)))
        
        return dev.serialNumber, self._appendExtraDataToScanResults(dev, results)

    def listAll(self):
        devices = dict()
        for dev in self.devices.values():
            if dev.meetsFirmwareRequirements:
                name = dev.getName()
                devices[str(dev.serialNumber)] = name
        
        return devices
        
    def details(self, serial):
        dev = self.devices[serial]
        
        if dev.devType == 3:
            dev.configU3()
        elif dev.devType == 6:
            dev.configU6()
        elif dev.devType == 9:
            dev.commConfig()
        
        return deviceAsDict(dev)
        

    def readTimerCounterConfig(self, serial):
        dev = self.getDevice(serial)
        
        returnDict = dict()
         
        TYPE_TO_NUM_TIMERS_MAPPING = { '3' : 2, '6' : 4, '9' : 6 }
        returnDict['totalTimers'] = TYPE_TO_NUM_TIMERS_MAPPING[str(dev.devType)]
        for i in range(returnDict['totalTimers']):
            returnDict["timer%iEnabled" % i] = False
            returnDict["timer%iMode" % i] = 10
            returnDict["timer%iValue" % i] = 0
        
        tcb, divisor = dev.readRegister(7000, numReg = 4)
        returnDict['timerClockBase'] = tcb
        returnDict['timerClockDivisor'] = divisor
        
        counter = dev.readRegister(50502)
        counter0Enabled = bool(counter & 1)
        counter1Enabled = bool((counter >> 1) & 1)
        returnDict['counter0Enabled'] = counter0Enabled
        returnDict['counter1Enabled'] = counter1Enabled
        
        offset = dev.readRegister(50500)
        returnDict['offset'] = offset
        
        numTimers = dev.readRegister(50501)
        returnDict['numTimers'] = offset
        
        for i in range(numTimers):
            mode, value = dev.readRegister(7100 + 2*i, format = ">HH", numReg = 2)
            returnDict["timer%iEnabled" % i] = True
            returnDict["timer%iMode" % i] = mode
            returnDict["timer%iValue" % i] = value
        
        dev.timerCounterCache = returnDict
        
        return returnDict
        
    def _convertTimerSettings(self, timerSettings, onlyEnabled = False):
        timers = []
        for i in range(6):
            if "timer%iEnabled" % i in timerSettings:
                if onlyEnabled and timerSettings["timer%iEnabled" % i]:
                    timers.append({"enabled" : int(timerSettings["timer%iEnabled" % i]), "mode" : int(timerSettings["timer%iMode" % i]), "value" : float(timerSettings["timer%iValue" % i])})
                elif not onlyEnabled:
                    timers.append({"enabled" : int(timerSettings["timer%iEnabled" % i]), "mode" : int(timerSettings["timer%iMode" % i]), "value" : float(timerSettings["timer%iValue" % i])})
            else:
                break
        return timers
        
    def updateTimerCounterConfig(self, serial, timerClockBase, timerClockDivisor, pinOffset, counter0Enable, counter1Enable, timerSettings):
        dev = self.getDevice(serial)
        
        currentSettings = dev.timerCounterCache
        
        if timerClockBase != currentSettings['timerClockBase'] or timerClockDivisor != currentSettings['timerClockDivisor']:
            self.setupClock(dev, timerClockBase, timerClockDivisor)
            currentSettings['timerClockBase'] = timerClockBase
            currentSettings['timerClockDivisor'] = timerClockDivisor
        
        print "Old timers:"
        oldTimers = self._convertTimerSettings(currentSettings)
        print "New Timers"
        newTimers = self._convertTimerSettings(timerSettings)
        if pinOffset != currentSettings['offset'] or oldTimers != newTimers:
            self.setupTimers(dev, newTimers, pinOffset)
            
        if counter0Enable and currentSettings['timerClockBase'] > 2:
            # Raise an error, this is an invalid configuration
            raise Exception("When a clock with a divisor is used, Counter0 is unavailable.")
            
        if counter0Enable != currentSettings['counter0Enabled'] or counter1Enable != currentSettings['counter1Enabled']:
            self.setupCounter(dev, bool(counter0Enable), bool(counter1Enable))
            currentSettings['counter0Enabled'] = bool(counter0Enable)
            currentSettings['counter1Enabled'] = bool(counter1Enable)
            
        self.readTimerCounterConfig(dev)
        
    def resetCounter(self, serial, counterNumber):
        dev = self.getDevice(serial)
        
        dev.writeRegister(7300 + (counterNumber * 2), 0)
    
    def setupClock(self, dev, timerClockBase = 0, divisor = 0):       
        dev.writeRegister(7000, timerClockBase)
        dev.writeRegister(7002, divisor)
        
    def setupCounter(self, dev, enableCounter0 = False, enableCounter1 = False):        
        value = (int(enableCounter1) << 1) + int(enableCounter0)
        
        dev.writeRegister(50502, value)
    
    def setupTimers(self, dev, timers = [], offset = 0):
        print "setupTimers:"
        print "timers =", timers
        print "offset =", offset
        
        numTimers = 0
        for t in timers:
            if t['enabled']:
                numTimers += 1
        
        dev.writeRegister(50500, offset)
        dev.writeRegister(50501, numTimers)
        
        for i, timer in enumerate(timers):
            dev.timerModes[i] = timer['mode']
            # NOTE: Code is good, just need to change the default for PWM to 0.5
            #if timer['mode'] in [0, 1]:
            #    timer['value'] = int(65536 - (timer['value'] * 65536))
            #    print "Writing PWM value =", timer['value']
            dev.writeRegister(7100 + 2*i, [timer['mode'], int(timer['value'])])
        
    
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
