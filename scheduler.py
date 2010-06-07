# An idea for a scheduler using threading module
import threading, heapq
import time

class Event(object):
    """
    A class for holding all information related to events.
    """
    def __init__(self, interval, function, pargs = [], kwargs = {}, reschedule = True):
        self.interval = interval
        self.function = function
        self.pargs = pargs
        self.kwargs = kwargs
        self.reschedule = reschedule
        
    def run(self, offset = 0):
        """
        Creates a thread to call self.function, sleeps, the starts the thread.
        """
        t = threading.Thread(target=self.function, args = self.pargs, kwargs = self.kwargs)
        time.sleep(offset)
        t.start()

class Scheduler(object):
    """
    A class for reliable, cross-platform scheduling.
    """
    
    def __init__(self):
        self.queueLock = threading.Lock()
        self.newEventEvent = threading.Event()
        self.queue = []
        self.running = True
        self.schedulerThread = threading.Thread(target=self.scheduleLoop)
        self.schedulerThread.start()
    
    def shutdown(self):
        """
        Stops the internal thread from scheduling any more events. This must be
        called before the main thread exits.
        """
        self.running = False
        self.newEventEvent.set()
    
    def _pushNewEventToHeap(self, timeEventTuple):
        self.queueLock.acquire()
        heapq.heappush(self.queue, timeEventTuple)
        self.queueLock.release()
        self.newEventEvent.set()
        
    def _convertInputToTime(self, timeinput):
        if isinstance(timeinput, str):
            nextTime = time.time() + float(timeinput)
        else:
            nextTime = timeinput
            
        if nextTime < time.time():
            nextTime = time.time()
            
        return nextTime
    
    def scheduleLoop(self):
        """
        Internals of the scheduler.
        """
        while self.running:
            # Check if the queue is empty.
            if len(self.queue) == 0:
                # Wait till we get an event to schedule
                self.newEventEvent.wait()
                self.newEventEvent.clear()
                continue
            
            self.queueLock.acquire()
            eventTime, event = heapq.heappop(self.queue)
            self.queueLock.release()
            
            diff = eventTime - time.time()
            #print "diff", diff
            if diff > 0.001:
                self.queueLock.acquire()
                heapq.heappush(self.queue, (eventTime, event))
                self.queueLock.release()
                self.newEventEvent.wait(eventTime - time.time())
                self.newEventEvent.clear()
            elif diff < 0:
                # missed
                #print "Diff was negitive"
                if event.reschedule:
                    self.queueLock.acquire()
                    nextTime = time.time()+(eventTime - time.time())+event.interval
                    heapq.heappush(self.queue, (nextTime, event))
                    self.queueLock.release()
                event.run()
            else:
                if event.reschedule:
                    self.queueLock.acquire()
                    nextTime = time.time()+event.interval-(eventTime - time.time())
                    #nextTime = time.time()+event.interval
                    heapq.heappush(self.queue, (nextTime, event))
                    self.queueLock.release()
                event.run(diff)
            
             
        
    def addReschedulingEvent(self, interval, function, pargs = [], kwargs = {}, start = None, now = True):
        """
        Name: Scheduler.addReschedulingEvent(interval, function, pargs = [],
                                            kwargs = {}, start = None,
                                            now = True)
        
        Args: interval, how many seconds between calls. Can be a float.
              function, the function to be called.
              pargs, positional args to pass to the function.
              kwargs, key word args to pass to the function.
              start, string representing how many seconds in the future to run
                     -- Or -- The epoch seconds of the time to run the event.
              now, runs the function immediately before scheduling.

        
        Desc: Adds an event which will be run every interval seconds.
        
        Example:
        >>> import scheduler
        >>> import time
        >>> from datetime import datetime
        >>> def printTime():
        >>>   print "++++++++++ Recurring event run at %s" % datetime.now()
        >>> s = scheduler.Scheduler()
        >>> print "Start: %s" % datetime.now()
        Start: 2010-05-28 17:03:32.970529
        >>> s.addReschedulingEvent(1, printTime)
        ++++++++++ Recurring event run at 2010-05-28 17:03:32.970723
        >>> time.sleep(5)
        ++++++++++ Recurring event run at 2010-05-28 17:03:33.970861
        ++++++++++ Recurring event run at 2010-05-28 17:03:34.970796
        ++++++++++ Recurring event run at 2010-05-28 17:03:35.970855
        ++++++++++ Recurring event run at 2010-05-28 17:03:36.970920
        ++++++++++ Recurring event run at 2010-05-28 17:03:37.970912
        >>> print "Finish: %s" % datetime.now()
        Finish: 2010-05-28 17:03:37.970759
        >>> s.shutdown()
        
        """
        e = Event(interval, function, pargs, kwargs)
        if start:
            nextTime = self._convertInputToTime(start)
        else:
            nextTime = time.time()+interval
        
        if now:
            e.run()
        
        self._pushNewEventToHeap((nextTime, e))
        
        return e
        
    def addSingleEvent(self, start, function, pargs = [], kwargs = {}):
        """
        Name: Scheduler.addSingleEvent(start, function, pargs = [], kwargs = {})
        
        Args: start, string representing how many seconds in the future to run
                     -- Or -- The epoch seconds of the time to run the event.
              function, the function to be called.
              pargs, positional args to pass to the function.
              kwargs, key word args to pass to the function.
        
        Desc: Adds an event to be run once in the future.
        
        Example showing the string method:
        >>> import scheduler
        >>> import time
        >>> from datetime import datetime
        >>> def printSingle():
        >>>   print "++++++++++ Single event run at %s" % datetime.now()
        >>> s = scheduler.Scheduler()
        >>> s.addSingleEvent("+2", printSingle)
        >>> print "Start: %s" % datetime.now()
        Start: 2010-05-28 16:53:45.452292
        >>> time.sleep(5)
        ++++++++++ Single event run at 2010-05-28 16:53:47.452748
        >>> print "Finish: %s" % datetime.now()
        Finish: 2010-05-28 16:53:50.452397
        >>> s.shutdown()
        
        Example showing the epoch second method:
        >>> import scheduler
        >>> import time
        >>> from datetime import datetime
        >>> def printSingle():
        >>>   print "++++++++++ Single event run at %s" % datetime.now()
        >>> s = scheduler.Scheduler()
        >>> s.addSingleEvent((time.time()+2), printSingle)
        >>> print "Start: %s" % datetime.now()
        Start: 2010-05-28 16:53:45.452292
        >>> time.sleep(5)
        ++++++++++ Single event run at 2010-05-28 16:53:47.452748
        >>> print "Finish: %s" % datetime.now()
        Finish: 2010-05-28 16:53:50.452397
        >>> s.shutdown()
        
        """
        nextTime = self._convertInputToTime(start)
        e = Event(0, function, pargs, kwargs, False)
        self._pushNewEventToHeap((nextTime, e))
                     
if __name__ == '__main__':
    from datetime import datetime
    from time import sleep
    
    print "Testing ReschedulingTimer:"
    
    OLD_TIME = datetime.now()
    def printTime():
        global OLD_TIME
        now = datetime.now()
        print "Now: %s, The difference is %s" % (now, (now-OLD_TIME))
        OLD_TIME = now
        
    def printSingle():
        print "++++++++++ I AM A SINGLE EVENT!!!!!!"
    
    s = Scheduler()
    print "Start: %s" % datetime.now()
    s.addReschedulingEvent(0.5, printTime)
    try:
        sleep(3)
        s.addSingleEvent("+0.5", printSingle)
        sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        #print "not calling shutdown"
        s.shutdown()
    
     