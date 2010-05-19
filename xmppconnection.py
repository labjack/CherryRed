# Makes connections for a device over XMPP
import threading
import sleekxmpp
import logging

import base64
from xml.etree.cElementTree import Element, dump
import struct

logging.basicConfig(level=logging.DEBUG, format='%(levelname)-8s %(message)s')

class CloudDotConnection(sleekxmpp.ClientXMPP):
    def __init__(self, jid, password, dev):
        sleekxmpp.ClientXMPP.__init__(self, jid, password)
        self.add_event_handler("session_start", self.start)
        self.add_event_handler("message", self.message)
        self.add_handler("<iq xmlns='jabber:client'><query xmlns='jabber:iq:clouddot' />*</iq>", self.iq_handler)
        self.device = dev
    
    def start(self, event):
        self.getRoster()
        self.sendPresence()
        
    def stop(self):
        print "Called CloudDotConnection stop"
        self.disconnect()
    
    def message(self, msg):
        print "Got msg:", msg
        #msg.reply("Thanks for sending\n%(body)s" % msg).send()
    
    def iq_handler(self, xml):
        iq = self.Iq(xml = xml)
        print "Got IQ", type(iq), iq
        dataElem = xml.getchildren()[0].getchildren()[0]
        print "children[0][0].items():",dataElem.items()
        print "children[0][0].text", dataElem.text
        data = base64.b64decode(dataElem.text)
        data = [ ord(c) for c in data ]
        print "Data:", repr(data)
        numBytes = int(dataElem.items()[0][1])
        
        self.device.write(data, modbus = True, checksum=False)
        result = self.device.read(numBytes)
        result = struct.pack("B" * len(result), *result)
        
        # We have the result, send it back in the response.
        result = base64.b64encode(result)
        reply = iq.reply()
        dataElem = Element("data")
        dataElem.text = result
        qt = Element("query", {"xmlns" : 'jabber:iq:clouddot' })
        qt.append(dataElem)
        print "qt", qt
        
        reply.appendxml(qt)
        print "iq.reply() redux:", reply
        
        reply.send(block=False)
        
class XmppThread(threading.Thread):
    def __init__(self, device, password = "XXXXXXXXXXXXXXXXXXXX"):
        threading.Thread.__init__(self)
        self.xmpp = CloudDotConnection("private-%s@cloud.labjack.com" % device.serialNumber, password, device)
        #self.xmpp.registerPlugin('xep_0004')
        #self.xmpp.registerPlugin('xep_0030')
        #self.xmpp.registerPlugin('xep_0060')
        #self.xmpp.registerPlugin('xep_0199')
        
    def stop(self):
        print "Called XmppThread stop"
        self.xmpp.stop()
        
    def run(self):
        if self.xmpp.connect():
            self.xmpp.process(threaded=False)
            print "done"
        else:
            print "Unable to connect."
        