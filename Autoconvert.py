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
        elif isinstance(r, float) and s.count(".") > 1:
            # The parsePythonValues function seems to hate strings with multiple
            # "." in them. It seems to think these are floats. We say no. 
            return s
        else:
            return r
    except Exception, e:
        #print type(e), e
        return s  # Can't parse it, let it pass through.  It's probably a bare string.

