# Copyright 2006-2015 Mark Diekhans
from __future__ import print_function
import os
import sys
import unittest
import difflib
import threading
import errno
import re
import glob
import logging
import six

xrange = six.moves.builtins.range

try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    MAXFD = 256


def rmTree(root):
    "remove a file hierarchy, root can be a file or a directory"
    if os.path.isdir(root):
        for dir, subdirs, files in os.walk(root, topdown=False):
            for f in files:
                os.unlink(dir + "/" + f)
            os.rmdir(dir)
    else:
        if os.path.lexists(root):
            os.unlink(root)


def ensureDir(dir):
    """Ensure that a directory exists, creating it (and parents) if needed."""
    try:
        os.makedirs(dir)
    except OSError as ex:
        if ex.errno != errno.EEXIST:
            raise ex


def ensureFileDir(fname):
    """Ensure that the directory for a file exists, creating it (and parents) if needed.
    Returns the directory path"""
    dir = os.path.dirname(fname)
    if len(dir) > 0:
        ensureDir(dir)
        return dir
    else:
        return "."


class TestLogging():
    """test logger that logs to memory, each instance has a new logger"""
    def __init__(self, level=logging.DEBUG):
        self.logger = logging.getLogger(str(id(self)))
        self.logger.setLevel(level)
        self.__buffer = six.StringIO()
        self.logger.addHandler(logging.StreamHandler(self.__buffer))

    @property
    def data(self):
        return self.__buffer.getvalue()


class TestCaseBase(unittest.TestCase):
    """Base class for test case with various test support functions"""

    def __init__(self, methodName):
        """initialize, removing old output files associated with the class"""
        super(TestCaseBase, self).__init__(methodName=methodName)
        clId = self.getClassId()
        od = self.getOutputDir()
        for f in glob.glob("{}/{}.*".format(od, clId)) + glob.glob("{}/tmp.*{}.*".format(od, clId)):
            rmTree(f)

    def getClassId(self):
        """Get the first part of the portable test id, consisting
        moduleBase.class.  This is the prefix to output files"""
        # module name is __main__ when run standalone, so get base file name
        mod = os.path.splitext(os.path.basename(sys.modules[self.__class__.__module__].__file__))[0]
        return mod + "." + self.__class__.__name__

    def getId(self):
        """get the fixed test id, which is in the form moduleBase.class.method
        which avoids different ids when test module is run as main or
        from a larger program"""
        # last part of unittest id is method
        return self.getClassId() + "." + self.id().split(".")[-1]

    def getTestDir(self):
        """find test directory, where concrete class is defined."""
        testDir = os.path.dirname(sys.modules[self.__class__.__module__].__file__)
        if testDir == "":
            testDir = "."
        testDir = os.path.realpath(testDir)
        # turn this into a relative directory
        cwd = os.getcwd()
        if testDir.startswith(cwd):
            testDir = testDir[len(cwd) + 1:]
            if len(testDir) == 0:
                testDir = "."
        return testDir

    def getTestRelProg(self, progName):
        "get path to a program in directory above the test directory"
        return os.path.join(self.getTestDir(), "..", progName)

    def getInputFile(self, fname):
        """Get a path to a file in the test input directory"""
        return self.getTestDir() + "/input/" + fname

    def getOutputDir(self):
        """get the path to the output directory to use for this test, create if it doesn't exist"""
        d = self.getTestDir() + "/output"
        ensureDir(d)
        return d

    def getOutputFile(self, ext):
        """Get path to the output file, using the current test id and append
        ext, which should contain a dot"""
        f = self.getOutputDir() + "/" + self.getId() + ext
        ensureFileDir(f)
        return f

    def getExpectedFile(self, ext, basename=None):
        """Get path to the expected file, using the current test id and append
        ext. If basename is used, it is inset of the test id, allowing share
        an expected file between multiple tests."""
        return self.getTestDir() + "/expected/" + (basename if basename is not None else self.getId()) + ext

    def __getLines(self, file):
        with open(file) as fh:
            return fh.readlines()

    def __getBytes(self, file):
        with open(file, "rb") as fh:
            return fh.read()

    def mustExist(self, path):
        if not os.path.exists(path):
            self.fail("file does not exist: " + path)

    def diffExpected(self, ext, expectedBasename=None):
        """diff expected and output files.  If expectedBasename is used, it is
        used insted of the test id to find the expected file, allowing share
        an expected file between multiple tests."""

        expFile = self.getExpectedFile(ext, expectedBasename)
        expLines = self.__getLines(expFile)

        outFile = self.getOutputFile(ext)
        outLines = self.__getLines(outFile)

        diff = difflib.unified_diff(expLines, outLines, expFile, outFile)
        cnt = 0
        for l in diff:
            sys.stdout.write(l)
            cnt += 1
        self.assertTrue(cnt == 0)

    def diffBinaryExpected(self, ext, expectedBasename=None):
        """diff expected and output binary files.  If expectedBasename is
        used, it is used insted of the test id to find the expected file,
        allowing share an expected file between multiple tests."""

        expFile = self.getExpectedFile(ext, expectedBasename)
        expBytes = self.__getBytes(expFile)

        outFile = self.getOutputFile(ext)
        outBytes = self.__getBytes(outFile)

        self.assertEqual(outBytes, expBytes)

    def createOutputFile(self, ext, contents=""):
        """create an output file, filling it with contents."""
        fpath = self.getOutputFile(ext)
        ensureFileDir(fpath)
        fh = open(fpath, "w")
        try:
            fh.write(contents)
        finally:
            fh.close()

    def verifyOutputFile(self, ext, expectContents=""):
        """verify an output file, if contents is not None, it is a string to
        compare to the expected contents of the file."""
        fpath = self.getOutputFile(ext)
        self.mustExist(fpath)
        self.assertTrue(os.path.isfile(fpath))
        fh = open(fpath)
        try:
            got = fh.read()
        finally:
            fh.close()
        self.assertEqual(got, expectContents)

    @staticmethod
    def numRunningThreads():
        "get the number of threads that are running"
        n = 0
        for t in threading.enumerate():
            if t.isAlive():
                n += 1
        return n

    def assertSingleThread(self):
        "fail if more than one thread is running"
        self.assertEqual(self.numRunningThreads(), 1)

    def assertNoChildProcs(self):
        "fail if there are any running or zombie child process"
        foundChild = True
        try:
            s = os.waitpid(0, os.WNOHANG)
        except OSError as ex:
            if ex.errno != errno.ECHILD:
                raise
            foundChild = False
        if foundChild:
            self.fail("pending child processes or zombies: " + str(s))

    @staticmethod
    def numOpenFiles():
        "count the number of open files"
        n = 0
        for fd in xrange(0, MAXFD):
            try:
                os.fstat(fd)
            except:
                n += 1
        return MAXFD - n

    def assertNumOpenFilesSame(self, prevNumOpen):
        "assert that the number of open files has not changed"
        numOpen = self.numOpenFiles()
        if numOpen != prevNumOpen:
            self.fail("number of open files changed, was " + str(prevNumOpen) + ", now it's " + str(numOpen))

    def assertRegexpMatchesDotAll(self, obj, expectRe, msg=None):
        """Fail if the str(obj) does not match expectRe operator, including `.' matching newlines"""
        if not re.match(expectRe, str(obj), re.DOTALL):
            raise self.failureException(msg or "'{}' does not match '{}'".format(str(obj), expectRe))
