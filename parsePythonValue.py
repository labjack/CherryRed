# parsePythonValue.py
#
# Copyright, 2006, by Paul McGuire
#
# Found on http://pyparsing.wikispaces.com/Examples


from pyparsing import *

cvtInt = lambda toks: int(toks[0])
cvtReal = lambda toks: float(toks[0])
cvtTuple = lambda toks : tuple(toks.asList())
cvtDict = lambda toks: dict(toks.asList())

# define punctuation as suppressed literals
lparen,rparen,lbrack,rbrack,lbrace,rbrace,colon = \
    map(Suppress,"()[]{}:")

integer = Combine(Optional(oneOf("+ -")) + Word(nums))\
    .setName("integer")\
    .setParseAction( cvtInt )
real = Combine(Optional(oneOf("+ -")) + Optional(Word(nums)) + "." +
               Optional(Word(nums)) +
               Optional(oneOf("e E")+Optional(oneOf("+ -")) +Word(nums)))\
    .setName("real")\
    .setParseAction( cvtReal )
tupleStr = Forward()
listStr = Forward()
dictStr = Forward()

listItem = real|integer|quotedString.setParseAction(removeQuotes)| \
            Group(listStr) | tupleStr | dictStr

tupleStr << ( Suppress("(") + Optional(delimitedList(listItem)) + 
            Optional(Suppress(",")) + Suppress(")") )
tupleStr.setParseAction( cvtTuple )

listStr << (lbrack + Optional(delimitedList(listItem) + 
            Optional(Suppress(","))) + rbrack)

dictEntry = Group( listItem + colon + listItem )
dictStr << (lbrace + Optional(delimitedList(dictEntry) + \
    Optional(Suppress(","))) + rbrace)
dictStr.setParseAction( cvtDict )

def parsePythonValue(s):
    return listItem.parseString(s)[0]

if __name__ == '__main__':
    tests = """['a', 100, ('A', [101,102]), 3.14, [ +2.718, 'xyzzy', -1.414] ]
               [{0: [2], 1: []}, {0: [], 1: [], 2: []}, {0: [1, 2]}]
               { 'A':1, 'B':2, 'C': {'a': 1.2, 'b': 3.4} }
               3.14159
               42
               6.02E23
               6.02e+023
               1.0e-7
               .7
               'a quoted string'""".split("\n")

    for test in tests:
        print "Test:", test.strip()
        result = listItem.parseString(test)[0]
        print "Result:", result
        try:
            for dd in result:
                if isinstance(dd,dict): print dd.items()
        except TypeError,te:
            pass
        print
