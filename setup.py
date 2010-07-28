# A setup file for creating an executable on Windows.

from distutils.core import setup
import py2exe

import os
import glob
from py2exe.build_exe import py2exe as build_exe

CONTENT_DIRS = [ "css", "html", "js", "templates", "Microsoft.VC90.CRT", "img" ]
EXTRA_FILES = [ "./cherryred.conf", "./liblabjackusb.dll" ]

class MediaCollector(build_exe):
    def addDirectoryToZip(self, folder):    
        full = os.path.join(self.collect_dir, folder)
        if not os.path.exists(full):
            self.mkpath(full)
    
        for f in glob.glob("%s/*" % folder):
            if os.path.isdir(f):
                self.addDirectoryToZip(f)
            else:
                name = os.path.basename(f)
                self.copy_file(f, os.path.join(full, name))
                self.compiled_files.append(os.path.join(folder, name))

    def copy_extensions(self, extensions):
        #super(MediaCollector, self).copy_extensions(extensions)
        build_exe.copy_extensions(self, extensions)
        
        for folder in CONTENT_DIRS:
            self.addDirectoryToZip(folder)
        
        for fileName in EXTRA_FILES:
            name = os.path.basename(fileName)
            self.copy_file(fileName, os.path.join(self.collect_dir, name))
            self.compiled_files.append(name)



setup(
    console=['grounded.py'],
    options={
        "py2exe":{
            "bundle_files" : 1,
            "excludes" : ["Tkinter", "Tkconstants", "tcl", "doctest", "pdb", "unittest", "difflib"],
            'packages': ['dns', "Cheetah", "sleekxmpp" ]
        }
    },
    cmdclass={'py2exe': MediaCollector},
    zipfile = None


)
