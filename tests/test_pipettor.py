# -*- coding: utf-8 -*-
# Copyright 2006-2025 Mark Diekhans
import unittest
import sys
import os
import re
import signal
import tracemalloc
from pathlib import Path

if __name__ == '__main__':
    sys.path.insert(0, os.path.normpath(os.path.dirname(sys.argv[0])) + "/../lib")
    from testCaseBase import TestCaseBase, LoggerForTests
else:
    from .testCaseBase import TestCaseBase, LoggerForTests
from pipettor import Pipeline, Popen, ProcessException, PipettorException, DataReader, DataWriter, File, run, runout, runlex, runlexout


def sigquit_handler(signum, frame):
    " prevent MacOS  crash reporter"
    sys.exit(os.EX_SOFTWARE)


signal.signal(signal.SIGQUIT, sigquit_handler)

# this keeps OS/X crash reporter from popping up on unittest error
signal.signal(signal.SIGQUIT,
              lambda signum, frame: sys.exit(os.EX_SOFTWARE))
signal.signal(signal.SIGABRT,
              lambda signum, frame: sys.exit(os.EX_SOFTWARE))

def setup_module(module):
    tracemalloc.start()

def _getProgWithErrorCmd(test, *args):
    return (os.path.join(test.getTestDir(), "progWithError"),) + args

class PipettorTestBase(TestCaseBase):
    "provide common functions used in test classes"
    def __init__(self, methodName):
        super(PipettorTestBase, self).__init__(methodName)

    def orphanChecks(self, nopen):
        "check for orphaned child process, open files or threads"
        self.assertNoChildProcs()
        self.assertNumOpenFilesSame(nopen)
        self.assertSingleThread()

    def commonChecks(self, nopen, pipeline, expectStr, isRe=False):
        """check that files, threads, and processes have not leaked. Check str(pipeline)
        against expectStr, which can be a string, or an regular expression if
        isRe==True, or None to not check."""
        s = str(pipeline)
        if expectStr is not None:
            if isRe:
                if not re.search(expectStr, s):
                    self.fail("'" + s + "' doesn't match RE '" + expectStr + "'")
            else:
                self.assertEqual(s, expectStr)
        self.orphanChecks(nopen)

    def _checkProgWithError(self, procExcept, progArgs=None):
        expectReTmpl = "^process exited 1: .+/progWithError{}{}:\nTHIS GOES TO STDERR{}{}.*$"
        if progArgs is not None:
            expectRe = expectReTmpl.format(" ", progArgs, ": ", progArgs)
        else:
            expectRe = expectReTmpl.format("", "", "", "")
        if not re.match(expectRe, str(procExcept), re.MULTILINE):
            self.fail("'{}' does not match '{}'".format(str(procExcept), str(expectRe)))


class PipelineTests(PipettorTestBase):
    def __init__(self, methodName):
        super(PipelineTests, self).__init__(methodName)

    def testTrivial(self):
        nopen = self.numOpenFiles()
        pl = Pipeline(("true",))
        pl.wait()
        self.commonChecks(nopen, pl, "true 2>[DataReader]")

    def testTrivialPoll(self):
        nopen = self.numOpenFiles()
        pl = Pipeline(("sleep", "1"))
        while not pl.poll():
            pass
        pl.wait()
        self.commonChecks(nopen, pl, "sleep 1 2>[DataReader]")

    def testTrivialFailPoll(self):
        nopen = self.numOpenFiles()
        pl = Pipeline([("sleep", "1"), ("false",)])
        with self.assertRaisesRegex(ProcessException, "^process exited 1: sleep 1 | false$"):
            pl.wait()
        self.commonChecks(nopen, pl, "sleep 1 | false 2>[DataReader]")

    def testTrivialStatus(self):
        nopen = self.numOpenFiles()
        pl = Pipeline(("true",))
        pl.start()
        self.assertTrue(pl.running)
        self.assertFalse(pl.finished)
        pl.wait()
        self.assertFalse(pl.running)
        self.assertTrue(pl.finished)
        self.commonChecks(nopen, pl, "true 2>[DataReader]")

    def testSimplePipe(self):
        nopen = self.numOpenFiles()
        log = LoggerForTests()
        pl = Pipeline([("true",), ("true",)], logger=log.logger)
        pl.wait()
        self.commonChecks(nopen, pl, "true | true 2>[DataReader]")
        self.assertEqual(log.data, """start: true | true 2>[DataReader]\n"""
                         """success: true | true 2>[DataReader]\n""")

    def testSimplePipeFail(self):
        nopen = self.numOpenFiles()
        log = LoggerForTests()
        pl = Pipeline([("false",), ("true",)], logger=log.logger)
        with self.assertRaisesRegex(ProcessException, "^process exited 1: false$"):
            pl.wait()
        self.commonChecks(nopen, pl, "false | true 2>[DataReader]")
        self.assertRegex(log.data,
                         re.compile("""^start: false | true 2>[DataReader]\n"""
                                    """failure: false | true 2>[DataReader]: process exited 1: false\n.*""",
                                    re.MULTILINE))

    def testPathObj(self):
        nopen = self.numOpenFiles()
        log = LoggerForTests()
        true_path = Path("/usr/bin/true")
        pl = Pipeline([(true_path,), (true_path,)], logger=log.logger)
        pl.wait()
        self.commonChecks(nopen, pl, "/usr/bin/true | /usr/bin/true 2>[DataReader]")
        self.assertEqual(log.data, """start: /usr/bin/true | /usr/bin/true 2>[DataReader]\n"""
                         """success: /usr/bin/true | /usr/bin/true 2>[DataReader]\n""")

    def testPipeFailStderr(self):
        nopen = self.numOpenFiles()
        # should report first failure
        pl = Pipeline([("true",), _getProgWithErrorCmd(self), ("false",)], stderr=DataReader)
        with self.assertRaises(ProcessException) as cm:
            pl.wait()
        self._checkProgWithError(cm.exception)
        self.orphanChecks(nopen)

    def testPipeFail3Stderr(self):
        # all 3 process fail
        nopen = self.numOpenFiles()
        # should report first failure
        pl = Pipeline([_getProgWithErrorCmd(self, "process0"),
                       _getProgWithErrorCmd(self, "process1"),
                       _getProgWithErrorCmd(self, "process2")],
                      stderr=DataReader)
        with self.assertRaises(ProcessException) as cm:
            pl.wait()
        # should be first process
        self._checkProgWithError(cm.exception, "process0")
        # check process
        for i in range(3):
            self._checkProgWithError(pl.procs[i].procExcept, "process{}".format(i))
        self.orphanChecks(nopen)

    def testExecFail(self):
        # invalid executable
        nopen = self.numOpenFiles()
        dw = DataWriter("one\ntwo\nthree\n")
        pl = Pipeline(("procDoesNotExist", "-r"), stdin=dw)
        with self.assertRaises(ProcessException) as cm:
            pl.wait()
        self.assertRegex(str(cm.exception),
                         "exec failed: procDoesNotExist -r.*")
        self.assertIsNot(cm.exception.__cause__, None)
        self.assertRegex(str(cm.exception.__cause__),
                         "\\[Errno 2\\] No such file or directory: 'procDoesNotExist'.*")
        self.commonChecks(nopen, pl, "procDoesNotExist -r <[DataWriter] 2>[DataReader]")

    def testSignaled(self):
        # process signals
        nopen = self.numOpenFiles()
        pl = Pipeline(("sh", "-c", "kill -11 $$"))
        with self.assertRaises(ProcessException) as cm:
            pl.wait()
        expect = "process signaled: SIGSEGV: sh -c 'kill -11 $$'"
        msg = str(cm.exception)
        if not msg.startswith(expect):
            self.fail("'" + msg + "' does not start with '"
                      + expect + "', cause: " + str(getattr(cm.exception, "cause", None)))
        self.commonChecks(nopen, pl, "sh -c 'kill -11 $$' 2>[DataReader]")

    def testStdinMem(self):
        # write from memory to stdin
        nopen = self.numOpenFiles()
        outf = self.getOutputFile(".out")
        dw = DataWriter("one\ntwo\nthree\n")
        pl = Pipeline(("sort", "-r"), stdin=dw, stdout=outf)
        pl.wait()
        self.diffExpected(".out")
        self.commonChecks(nopen, pl, "^sort -r <\\[DataWriter\\] >.+/output/test_pipettor\\.PipelineTests\\.testStdinMem\\.out 2>\\[DataReader\\]$", isRe=True)

    def testStdoutMem(self):
        # read from stdout into memory
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        dr = DataReader()
        pl = Pipeline(("sort", "-r"), stdin=inf, stdout=dr)
        pl.wait()
        self.assertEqual(dr.data, "two\nthree\nsix\none\nfour\nfive\n")
        self.commonChecks(nopen, pl, "^sort -r <.+/input/simple1\\.txt >\\[DataReader\\]", isRe=True)

    def testStdinStdoutMem(self):
        # write and read from memory
        nopen = self.numOpenFiles()
        dw = DataWriter("one\ntwo\nthree\n")
        dr = DataReader()
        pl = Pipeline([("cat", "-u"), ("cat", "-u")], stdin=dw, stdout=dr)
        pl.wait()
        self.assertEqual(dr.data, "one\ntwo\nthree\n")
        self.commonChecks(nopen, pl, "^cat -u <\\[DataWriter\\] \\| cat -u >\\[DataReader\\] 2>\\[DataReader\\]$", isRe=True)

    def testFileMode(self):
        with self.assertRaisesRegex(PipettorException, "^invalid or unsupported mode 'q' opening /dev/null"):
            File("/dev/null", "q")

    def testCollectStdoutErr(self):
        # independent collection of stdout and stderr
        nopen = self.numOpenFiles()
        stdoutRd = DataReader()
        stderrRd = DataReader()
        pl = Pipeline(("sh", "-c", "echo this goes to stdout; echo this goes to stderr >&2"),
                      stdout=stdoutRd, stderr=stderrRd)
        pl.wait()
        self.assertEqual(stdoutRd.data, "this goes to stdout\n")
        self.assertEqual(stderrRd.data, "this goes to stderr\n")
        self.commonChecks(nopen, pl, "sh -c 'echo this goes to stdout; echo this goes to stderr >&2' >[DataReader] 2>[DataReader]")

    def testStdinMemBinary(self):
        # binary write from memory to stdin
        nopen = self.numOpenFiles()
        outf = self.getOutputFile(".out")
        fh = open(self.getInputFile("file.binary"), "rb")
        dw = DataWriter(fh.read())
        fh.close()
        pl = Pipeline(("cat",), stdin=dw, stdout=outf)
        pl.wait()
        self.diffBinaryExpected(".out", expectedBasename="file.binary")
        self.commonChecks(nopen, pl, "^cat <\\[DataWriter] >.*/output/test_pipettor.PipelineTests.testStdinMemBinary.out 2>\\[DataReader\\]$", isRe=True)

    def testStdoutMemBinary(self):
        # binary read from stdout into memory
        nopen = self.numOpenFiles()
        inf = self.getInputFile("file.binary")
        dr = DataReader(binary=True)
        pl = Pipeline(("cat",), stdin=inf, stdout=dr)
        pl.wait()
        fh = open(self.getOutputFile(".out"), "wb")
        fh.write(dr.data)
        fh.close()
        self.diffBinaryExpected(".out", expectedBasename="file.binary")
        self.commonChecks(nopen, pl, "^cat <.*/input/file.binary >\\[DataReader] 2>\\[DataReader\\]$", isRe=True)

    def testWriteFile(self):
        # test write to File object
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        outf = self.getOutputFile(".out")
        # double cat actually found a bug
        pl = Pipeline([("cat",), ("cat",)], stdin=inf, stdout=File(outf, "w"))
        pl.wait()
        self.diffExpected(".out")
        self.commonChecks(nopen, pl, "cat <.*/input/simple1.txt \\| cat >.*/output/test_pipettor.PipelineTests.testWriteFile.out 2>\\[DataReader\\]$", isRe=True)

    def testReadFile(self):
        # test read and write to File object
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        outf = self.getOutputFile(".out")
        pl = Pipeline([("cat",), ("cat",)], stdin=File(inf), stdout=File(outf, "w"))
        pl.wait()
        self.diffExpected(".out")
        self.commonChecks(nopen, pl, "cat <.*/input/simple1.txt \\| cat >.*/output/test_pipettor.PipelineTests.testReadFile.out 2>\\[DataReader\\]$", isRe=True)

    def testAppendFile(self):
        # test append to File object
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        outf = self.getOutputFile(".out")
        # double cat actually found a bug
        pl = Pipeline([("cat",), ("cat",)], stdin=inf, stdout=File(outf, "w"), stderr=None)
        pl.wait()
        pl = Pipeline([("cat",), ("cat",)], stdin=inf, stdout=File(outf, "a"), stderr=None)
        pl.wait()
        self.diffExpected(".out")
        self.commonChecks(nopen, pl, "cat <.*/input/simple1.txt \\| cat >.*/output/test_pipettor.PipelineTests.testAppendFile.out$", isRe=True)

    def __bogusStdioExpectRe(self):
        return "^invalid stdio specification object type: <class 'float'> 3\\.14159$"

    def testBogusStdin(self):
        # test stdin specification is not legal
        nopen = self.numOpenFiles()
        with self.assertRaisesRegex(PipettorException, self.__bogusStdioExpectRe()):
            pl = Pipeline([("date",), ("date",)], stdin=3.14159)
            pl.wait()
        self.orphanChecks(nopen)

    def testBogusStdout(self):
        # test stdout specification is not legal
        nopen = self.numOpenFiles()
        with self.assertRaisesRegex(PipettorException, self.__bogusStdioExpectRe()):
            pl = Pipeline([("date",), ("date",)], stdout=3.14159)
            pl.wait()
        self.orphanChecks(nopen)

    def testBogusStderr(self):
        # test stderr specification is not legal
        nopen = self.numOpenFiles()
        with self.assertRaisesRegex(PipettorException, self.__bogusStdioExpectRe()):
            pl = Pipeline([("date",), ("date",)], stderr=3.14159)
            pl.wait()
        self.orphanChecks(nopen)

    def testDataReaderShare(self):
        # test stderr linked to stdout/stderr
        nopen = self.numOpenFiles()
        dr = DataReader()
        pl = Pipeline([("date",), ("date",)], stdout=dr, stderr=dr)
        pl.wait()
        self.orphanChecks(nopen)

    def testDataWriterBogusShare(self):
        # test stderr specification is not legal
        nopen = self.numOpenFiles()
        dw = DataWriter("fred")
        with self.assertRaisesRegex(PipettorException, "^DataWriter already bound to a process$"):
            pl1 = Pipeline([("cat", "/dev/null"), ("cat", "/dev/null")], stdin=dw)
            Pipeline([("cat", "/dev/null"), ("cat", "/dev/null")], stdin=dw)
        pl1.shutdown()  # clean up unstarted process
        self.orphanChecks(nopen)

    def testIntArg(self):
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        dr = DataReader()
        pl = Pipeline(("head", -2), stdin=inf, stdout=dr)
        pl.wait()
        self.assertEqual(dr.data, "one\ntwo\n")
        self.commonChecks(nopen, pl, "^head -2 <.+/input/simple1\\.txt >\\[DataReader\\]", isRe=True)

    def testStderrPipeRedir(self):
        # stderr DataReader on multiple processes
        stderr = DataReader(errors='backslashreplace')
        cmds = (["sh", "-c", "echo command one >&2"],
                ["sh", "-c", "echo COMMAND TWO >&2"])
        pl = Pipeline(cmds, stdout='/dev/null', stderr=stderr)
        pl.wait()
        # can't predict order
        err_sorted = list(sorted(stderr.data.strip().split('\n')))
        self.assertEqual(err_sorted, ['COMMAND TWO', 'command one'])


class PopenTests(PipettorTestBase):
    def __init__(self, methodName):
        super(PopenTests, self).__init__(methodName)

    def cpFileToPl(self, inName, pl):
        inf = self.getInputFile(inName)
        fh = open(inf)
        for line in fh:
            pl.write(line)
        fh.close()

    def cpPlToFile(self, pl, outExt):
        outf = self.getOutputFile(outExt)
        fh = open(outf, "w")
        for line in pl:
            fh.write(line)
        fh.close()

    def testWrite(self):
        nopen = self.numOpenFiles()
        outf = self.getOutputFile(".out")
        outfGz = self.getOutputFile(".out.gz")

        pl = Popen(("gzip", "-1"), "w", stdout=outfGz)
        self.cpFileToPl("simple1.txt", pl)
        pl.close()
        self.commonChecks(nopen, pl, "gzip -1 <.+ >.*output/test_pipettor.PopenTests.testWrite.out.gz", isRe=True)

        # macOS Ventura: don't used zcat; would need to use gzcat, but this is compatbile with all
        Pipeline(("gunzip", "-c", outfGz), stdout=outf).wait()
        self.diffExpected(".out")

    def testWriteFile(self):
        nopen = self.numOpenFiles()
        outf = self.getOutputFile(".out")
        outfGz = self.getOutputFile(".out.gz")

        with open(outfGz, "w") as outfGzFh:
            pl = Popen(("gzip", "-1"), "w", stdout=outfGzFh)
            self.cpFileToPl("simple1.txt", pl)
            pl.wait()

        # macOS Ventura: don't used zcat; would need to use gzcat, but this is compatbile with all
        Pipeline(("gunzip", "-c", outfGz), stdout=outf).wait()
        self.diffExpected(".out")
        self.commonChecks(nopen, pl, "gzip -1 <.* >.*output/test_pipettor.PopenTests.testWriteFile.out.gz", isRe=True)

    def testWriteMult(self):
        nopen = self.numOpenFiles()
        outf = self.getOutputFile(".wc")

        # grr, BSD wc adds an extract space, so just convert to tabs
        pl = Popen((("gzip", "-1"),
                    ("gzip", "-dc"),
                    ("wc",),
                    ("sed", "-e", "s/  */\t/g")), "w", stdout=outf)
        self.cpFileToPl("simple1.txt", pl)
        pl.wait()

        self.diffExpected(".wc")
        self.commonChecks(nopen, pl, "^gzip -1 <.+ | gzip -dc | wc | sed -e 's/  \\*/	/g' >.*output/test_pipettor.PopenTests.testWriteMult.wc$", isRe=True)

    def testRead(self):
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        infGz = self.getOutputFile(".txt.gz")
        Pipeline(("gzip", "-c", inf), stdout=infGz).wait()

        pl = Popen(("gzip", "-dc"), "r", stdin=infGz)
        self.cpPlToFile(pl, ".out")
        pl.wait()

        self.diffExpected(".out")
        self.commonChecks(nopen, pl, "^gzip -dc <.*output/test_pipettor.PopenTests.testRead.txt.gz >.+$", isRe=True)

    def testReadMult(self):
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")

        pl = Popen((("gzip", "-1c"),
                    ("gzip", "-dc"),
                    ("wc",),
                    ("sed", "-e", "s/  */\t/g")), "r", stdin=inf)
        self.cpPlToFile(pl, ".wc")
        pl.wait()

        self.diffExpected(".wc")
        self.commonChecks(nopen, pl, "^gzip -1c <.*tests/input/simple1.txt | gzip -dc | wc | sed -e 's/  \\*/	/g' >.+$", isRe=True)

    def testExitCode(self):
        nopen = self.numOpenFiles()
        pl = Popen(("false",))
        with self.assertRaisesRegex(ProcessException, "^process exited 1: false$"):
            pl.wait()
        for p in pl.procs:
            self.assertTrue(p.returncode == 1)
        self.commonChecks(nopen, pl, "^false >.+$", isRe=True)

    simpleOneLines = ['one\n', 'two\n', 'three\n', 'four\n', 'five\n', 'six\n']

    def testReadDos(self):
        with Popen(("cat", self.getInputFile("simple1.dos.txt")), mode="r") as fh:
            lines = [l for l in fh]
        self.assertEqual(lines, self.simpleOneLines)

    def testReadMac(self):
        with Popen(("cat", self.getInputFile("simple1.mac.txt")), mode="r") as fh:
            lines = [l for l in fh]
        self.assertEqual(lines, self.simpleOneLines)

    def testSigPipe(self):
        # test not reading all of pipe output
        nopen = self.numOpenFiles()
        pl = Popen([("yes",), ("true",)], "r")
        pl.wait()
        self.commonChecks(nopen, pl, "^yes | true >.+ 2>\\[DataReader\\]$", isRe=True)

    def testReadAsAsciiReplace(self):
        # file contains unicode character outside of the ASCII range
        nopen = self.numOpenFiles()
        inf = self.getInputFile("nonAscii.txt")
        with Popen(["cat", inf], encoding='latin-1', errors="replace") as fh:
            lines = [l[:-1] for l in fh]
        self.assertEqual(['Microtubules are assembled from dimers of a- and \xc3\x9f-tubulin.'], lines)
        self.orphanChecks(nopen)

    def testEnvPassing(self):
        env = dict(os.environ)
        env['PIPETTOR'] = "YES"

        got_it = False
        with Popen(["env"], env=env) as fh:
            for line in fh:
                if line.strip() == "PIPETTOR=YES":
                    got_it = True
        assert got_it, "PIPETTOR=YES not set in enviroment"

class FunctionTests(PipettorTestBase):
    def __init__(self, methodName):
        super(FunctionTests, self).__init__(methodName)

    def testWriteFile(self):
        # test write to File object
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        outf = self.getOutputFile(".out")
        run([("cat",), ("cat",)], stdin=inf, stdout=File(outf, "w"))
        self.diffExpected(".out")
        self.orphanChecks(nopen)

    def testPathObj(self):
        nopen = self.numOpenFiles()
        true_path = Path("/usr/bin/true")
        run([true_path])
        self.orphanChecks(nopen)

    def testSimplePipeFail(self):
        nopen = self.numOpenFiles()
        with self.assertRaisesRegex(ProcessException, "^process exited 1: false$"):
            run([("false",), ("true",)])
        self.orphanChecks(nopen)

    def testStdoutRead(self):
        # read from stdout into memory
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        out = runout(("sort", "-r"), stdin=inf)
        self.assertEqual(out, "two\nthree\nsix\none\nfour\nfive\n")
        self.orphanChecks(nopen)

    def testStdoutReadFail(self):
        # read from stdout into memory
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        with self.assertRaises(ProcessException) as cm:
            runout([("sort", "-r"), _getProgWithErrorCmd(self), ("false",)], stdin=inf)
        self._checkProgWithError(cm.exception)
        self.orphanChecks(nopen)

    def testWriteFileLex(self):
        # test write to File object
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        outf = self.getOutputFile(".out")
        runlex(["cat -u", ["cat", "-u"], "cat -n"], stdin=inf, stdout=File(outf, "w"))
        self.diffExpected(".out")
        self.orphanChecks(nopen)

    def testStdoutReadLex(self):
        # read from stdout into memory
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        out = runlexout("sort -r", stdin=inf)
        self.assertEqual(out, "two\nthree\nsix\none\nfour\nfive\n")
        self.orphanChecks(nopen)

    def testEnvPassing(self):
        env = dict(os.environ)
        env['PIPETTOR'] = "YES"

        lines = runout(["env"], env=env).splitlines()
        assert "PIPETTOR=YES" in lines


def suite():
    ts = unittest.TestSuite()
    ts.addTest(unittest.makeSuite(PipelineTests))
    ts.addTest(unittest.makeSuite(PopenTests))
    ts.addTest(unittest.makeSuite(FunctionTests))
    return ts


if __name__ == '__main__':
    unittest.main()
