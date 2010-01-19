from parsePythonValue import parsePythonValue
from pyparsing import ParseResults

def autoConvert(s):
    """
    Autoconvert using Pyparsing: http://pyparsing.wikispaces.com/
    """
    if s == "True":
        return True
    elif s == "False":
        return False
    
    try:
        r = parsePythonValue(s)
        if type(r) == ParseResults:
            return r._ParseResults__toklist
        else:
            return r
    except Exception, e:
        #print type(e), e
        return s  # Can't parse it, let it pass through.  It's probably a bare string.

