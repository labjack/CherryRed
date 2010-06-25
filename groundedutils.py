import re

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
