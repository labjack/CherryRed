import logging
import logging.handlers

LOG_FILENAME = "./logfiles/grounded.log"

# Set up a specific logger with our desired output level
my_logger = logging.getLogger('MyLogger')
my_logger.setLevel(logging.DEBUG)

# Add the log message handler to the logger
handler = logging.handlers.RotatingFileHandler(
          LOG_FILENAME, maxBytes=1000000, backupCount=5)
formatter = logging.Formatter("[%(asctime)s] - %(funcName)s - %(message)s")
handler.setFormatter(formatter)
my_logger.addHandler(handler)
    
def log(*message):
    """
    log accepts multiple arguments, which it converts
    to a space and joins with a string.
    """
    realMessage = ''
    for i in message:
        try:
            realMessage = realMessage + ' ' + str(i.encode("utf-8"))+' '
        except:
            realMessage = realMessage + ' ' + str(i).encode("utf-8")+' '
    my_logger.debug(realMessage)