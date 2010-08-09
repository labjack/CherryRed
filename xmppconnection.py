# Makes connections for a device over XMPP
import threading
import sleekxmpp
import logging

from time import sleep

import base64
from xml.etree.cElementTree import Element, dump
import struct

logging.basicConfig(level=logging.DEBUG, format='%(levelname)-8s %(message)s')

class CloudDotIQ(object):
    def __init__(self, xml):
        self._xml = xml
        
        self.layout = dict()
        self.data = None
        self.numReturnBytes = None
        
        self.parseXML()
    
    def _strElement(self, element, indent = 0):
        e = self.layout[element]
        reprStr = "%s<%s" % (" " * (indent * 2),element)
        for key, value in e['attrs'].items():
            reprStr += " %s='%s'" % (key, value)
        
        if e['text'] is None:
            reprStr += ">\n"
            for child in e['children']:
                reprStr += self._strElement(child, indent+1)
            reprStr +=  "\n%s</%s>" % (" " * (indent * 2),element)
        else:
            reprStr += ">%s</%s>" % (e['text'], element)
        
        return reprStr
            
            
    
    def __repr__(self):
        return self._strElement("iq")
    
    def stripNS(self, tag):
        n = tag
        try:
            i = tag.index("}")
            n = tag[(i+1):]
        except ValueError:
            pass
        
        return str(n)
        
    def parseXML(self):
        for e in self._xml.getiterator():
            attributes = e.attrib
            children = []
            for c in e.getchildren():
                children.append(self.stripNS(c.tag))
            text = e.text
            
            self.layout[self.stripNS(e.tag)] = { "attrs" : attributes, "children" : children, "text" : text }
        
        self.data = base64.b64decode(self.layout['data']['text'])
        self.data = [ ord(c) for c in self.data ]
        self.numReturnBytes = int(self.layout['data']['attrs']['numReturnBytes'])
        

class CloudDotConnection(sleekxmpp.ClientXMPP):
    def __init__(self, jid, password, serial, dm):
        sleekxmpp.ClientXMPP.__init__(self, jid, password)
        self.add_event_handler("session_start", self.start)
        self.add_event_handler("message", self.message)
        self.add_handler("<iq xmlns='jabber:client'><query xmlns='jabber:iq:clouddot' />*</iq>", self.iq_handler)
        self.serial = serial
        self.dm = dm
        
        self.registerPlugin('xep_0199')
        self.looping = True
        
        self.heartbeatThread = threading.Thread(target = self.pingLoop)
        self.shutdownEvent = threading.Event()

    def getDevice(self):
        return self.dm.getDevice(self.serial)

    device = property(getDevice)

    def pingLoop(self):
        print "Started pingLoop"
        while self.looping:
            print "Sleeping for 14 seconds."
            self.shutdownEvent.wait(14)
            if self.shutdownEvent.isSet():
                break
            print "Sending ping."
            self.plugin['xep_0199'].sendPing("beanstalk@cloud.labjack.com")
        print "Finished pingLoop"
    
    def start(self, event):
        self.getRoster()
        self.sendPresence()
        
        self.heartbeatThread.start()
        
    def stop(self):
        print "Called CloudDotConnection stop"
        self.looping = False
        self.shutdownEvent.set()
        self.disconnect()
    
    def message(self, msg):
        print "Got msg:", msg
        #msg.reply("Thanks for sending\n%(body)s" % msg).send()
    
    def iq_handler(self, xml):
        iq = CloudDotIQ(xml)
        print "Got IQ", type(iq), iq
        
        data = iq.data
        print "Data:", repr(data)
        numBytes = iq.numReturnBytes
        
        # Set the DM's flag that we're using the device.
        # This is definitely incorrect, but it may be good enough.
        self.dm.scanEvent.wait()
        try:
            self.dm.scanEvent.clear()
            self.device.write(data, modbus = True, checksum=False)
            result = self.device.read(numBytes)
            result = struct.pack("B" * len(result), *result)
        finally:
            self.dm.scanEvent.set()
        
        # We have the result, send it back in the response.
        etIq = self.Iq(xml = xml)
        result = base64.b64encode(result)
        reply = etIq.reply()
        dataElem = Element("data")
        dataElem.text = result
        qt = Element("query", {"xmlns" : 'jabber:iq:clouddot' })
        qt.append(dataElem)
        print "qt", qt
        
        reply.appendxml(qt)
        print "etIq.reply() redux:", reply
        
        reply.send(block=False)
        
class XmppThread(threading.Thread):
    def __init__(self, device, dm, password = "XXXXXXXXXXXXXXXXXXXX"):
        threading.Thread.__init__(self)
        self.xmpp = CloudDotConnection("private-%s@cloud.labjack.com" % device.serialNumber, password, str(device.serialNumber), dm)
        #self.xmpp.registerPlugin('xep_0004')
        self.xmpp.registerPlugin('xep_0030')
        #self.xmpp.registerPlugin('xep_0060')
        self.xmpp.registerPlugin('xep_0199')
        
    def stop(self):
        print "Called XmppThread stop"
        self.xmpp.stop()
        
    def run(self):
        if self.xmpp.connect():
            self.xmpp.process(threaded=False)
            print "done"
        else:
            print "Unable to connect."
        