# Copyright 2006-2012 Mark Diekhans
import unittest, sys, os, re
if __name__ == '__main__':
    sys.path.insert(0, os.path.normpath(os.path.dirname(sys.argv[0]))+"/..")
from pipettor.pipettor import Pipeline, Popen, ProcessException, PipettorException, DataReader, DataWriter, File
from testCaseBase import TestCaseBase

# this keeps OS/X crash reporter from popping up on unittest error
import signal
signal.signal(signal.SIGQUIT,
              lambda signum, frame: sys.exit(os.EX_SOFTWARE))
signal.signal(signal.SIGABRT,
              lambda signum, frame: sys.exit(os.EX_SOFTWARE))


class PipelineTests(TestCaseBase):
    def commonChecks(self, nopen, pipeline, expectStr, isRe=False):
        """check that files, threads, and processes have not leaked. Check str(pipeline)
        against expectStr, which can be a string, or an regular expression if
        isRe==True, or None to not check."""
        s = str(pipeline)
        if expectStr is not None:
            if isRe:
                if not re.search(expectStr, s):
                    self.fail("'" +s+ "' doesn't match RE '" + expectStr + "'")
            else:
                self.assertEqual(s, expectStr)
        self.assertNoChildProcs()
        self.assertNumOpenFilesSame(nopen)
        self.assertSingleThread()

    def testTrivial(self):
        nopen = self.numOpenFiles()
        pl = Pipeline(("true",))
        pl.wait()
        self.commonChecks(nopen, pl, "true")

    def testTrivialFail(self):
        nopen = self.numOpenFiles()
        pl = Pipeline(("false",))
        with self.assertRaisesRegexp(ProcessException, "^process exited 1: false$") as cm:
            pl.wait()
        self.commonChecks(nopen, pl, "false")

    def testSimplePipe(self):
        nopen = self.numOpenFiles()
        pl = Pipeline([("true",), ("true",)])
        pl.wait()
        self.commonChecks(nopen, pl, "true | true")

    def testSimplePipeFail(self):
        nopen = self.numOpenFiles()
        pl = Pipeline([("false",), ("true",)])
        with self.assertRaisesRegexp(ProcessException, "^process exited 1: false$") as cm:
            pl.wait()
        self.commonChecks(nopen, pl, "false | true")

    def testExecFail(self):
        # invalid executable
        nopen = self.numOpenFiles()
        dw = DataWriter("one\ntwo\nthree\n")
        pl = Pipeline(("procDoesNotExist","-r"), stdin=dw)
        with self.assertRaises(ProcessException) as cm:
            pl.wait()
        expect = "exec failed: procDoesNotExist -r,\n    caused by: OSError: [Errno 2] No such file or directory"
        msg = str(cm.exception)
        if not msg.startswith(expect):
            self.fail("'"+ msg + "' does not start with '"
                      + expect + "', cause: " + str(getattr(cm.exception,"cause", None)))
        self.commonChecks(nopen, pl, "procDoesNotExist -r <[DataWriter]")

    def testSignaled(self):
        # process signals
        nopen = self.numOpenFiles()
        pl = Pipeline(("sh","-c", "kill -11 $$"))
        with self.assertRaises(ProcessException) as cm:
            pl.wait()
        expect = "process signaled: SIGSEGV: sh -c 'kill -11 $$'"
        msg = str(cm.exception)
        if not msg.startswith(expect):
            self.fail("'"+ msg + "' does not start with '"
                      + expect + "', cause: " + str(getattr(cm.exception,"cause", None)))
        self.commonChecks(nopen, pl,  "sh -c 'kill -11 $$'")

    def testStdinMem(self):
        # write from memory to stdin
        nopen = self.numOpenFiles()
        outf = self.getOutputFile(".out")
        dw = DataWriter("one\ntwo\nthree\n")
        pl = Pipeline(("sort","-r"), stdin=dw, stdout=outf)
        pl.wait()
        self.diffExpected(".out")
        self.commonChecks(nopen, pl, "^sort -r <\\[DataWriter\\] >.+/output/pipettorTests\\.PipelineTests\\.testStdinMem\\.out$", isRe=True)

    def testStdoutMem(self):
        # read from stdout into memory
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        dr = DataReader()
        pl = Pipeline(("sort","-r"), stdin=inf, stdout=dr)
        pl.wait()
        self.assertEqual(dr.data, "two\nthree\nsix\none\nfour\nfive\n")
        self.commonChecks(nopen, pl, "^sort -r <.+/input/simple1\\.txt >\\[DataReader\\]", isRe=True)

    def testStdinStdoutMem(self):
        # write and read from memory
        nopen = self.numOpenFiles()
        dw = DataWriter("one\ntwo\nthree\n")
        dr = DataReader()
        pl = Pipeline([("cat","-u"),("cat","-u")], stdin=dw, stdout=dr)
        pl.wait()
        self.assertEqual(dr.data, "one\ntwo\nthree\n")
        self.commonChecks(nopen, pl, "^cat -u <\\[DataWriter\\] \\| cat -u >\\[DataReader\\]$", isRe=True)

    def testFileMode(self):
        with self.assertRaisesRegexp(PipettorException, "^invalid mode: 'q', expected 'r', 'w', or 'a' with optional 'b' suffix$") as cm:
            File("/dev/null", "q")

    def testCollectStdoutErr(self):
        # independent collection of stdout and stderr
        nopen = self.numOpenFiles()
        stdoutRd = DataReader()
        stderrRd = DataReader()
        pl = Pipeline(("bash", "-c", "echo this goes to stdout; echo this goes to stderr >&2"),
                      stdout=stdoutRd, stderr=stderrRd)
        pl.wait()
        self.assertEqual(stdoutRd.data, "this goes to stdout\n")
        self.assertEqual(stderrRd.data, "this goes to stderr\n")
        self.commonChecks(nopen, pl, "bash -c 'echo this goes to stdout; echo this goes to stderr >&2' >[DataReader] 2>[DataReader]")
                       
    def testStdinMemBinary(self):
        # binary write from memory to stdin
        nopen = self.numOpenFiles()
        outf = self.getOutputFile(".out")
        fh = open(self.getInputFile("file.binary"), "rb")
        dw = DataWriter(fh.read())
        fh.close()
        pl = Pipeline(("cat",), stdin=dw, stdout=outf)
        pl.wait()
        self.diffExpected(".out", expectedBasename="file.binary")
        self.commonChecks(nopen, pl, "^cat <\\[DataWriter] >.*/output/pipettorTests.PipelineTests.testStdinMemBinary.out$", isRe=True)

    def testStdoutMemBinary(self):
        # binary read from stdout into memory
        nopen = self.numOpenFiles()
        inf = self.getInputFile("file.binary")
        dr = DataReader()
        pl = Pipeline(("cat",), stdin=inf, stdout=dr)
        pl.wait()
        fh = open(self.getOutputFile(".out"), "wb")
        fh.write(dr.data)
        fh.close()
        self.diffExpected(".out", expectedBasename="file.binary")
        self.commonChecks(nopen, pl, "^cat <.*/input/file.binary >\\[DataReader]$", isRe=True)

    def testWriteFile(self):
        # test write to File object
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        outf = self.getOutputFile(".out")
        # double cat actually found a bug
        pl = Pipeline([("cat",),("cat",)], stdin=inf, stdout=File(outf, "w"))
        pl.wait()
        self.diffExpected(".out")
        self.commonChecks(nopen, pl, "cat <.*/input/simple1.txt \\| cat >.*/output/pipettorTests.PipelineTests.testWriteFile.out$", isRe=True)

    def testReadFile(self):
        # test read and write to File object
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        outf = self.getOutputFile(".out")
        pl = Pipeline([("cat",),("cat",)], stdin=File(inf), stdout=File(outf, "w"))
        pl.wait()
        self.diffExpected(".out")
        self.commonChecks(nopen, pl, "cat <.*/input/simple1.txt \\| cat >.*/output/pipettorTests.PipelineTests.testReadFile.out$", isRe=True)

    def testAppendFile(self):
        # test append to File object
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        outf = self.getOutputFile(".out")
        # double cat actually found a bug
        pl = Pipeline([("cat",),("cat",)], stdin=inf, stdout=File(outf, "w"))
        pl.wait()
        pl = Pipeline([("cat",),("cat",)], stdin=inf, stdout=File(outf, "a"))
        pl.wait()
        self.diffExpected(".out")
        self.commonChecks(nopen, pl, "cat <.*/input/simple1.txt \\| cat >.*/output/pipettorTests.PipelineTests.testAppendFile.out$", isRe=True)

    def testBogusStdin(self):
        # test stdin specification is not legal
        nopen = self.numOpenFiles()
        with self.assertRaisesRegexp(PipettorException, "^invalid stdio specification object type: <type 'float'>$") as cm:
            pl = Pipeline([("date",),("date",)], stdin=3.14159)
            pl.wait()
        self.commonChecks(nopen, None, None)

    def testBogusStdout(self):
        # test stdout specification is not legal
        nopen = self.numOpenFiles()
        with self.assertRaisesRegexp(PipettorException, "^invalid stdio specification object type: <type 'float'>$") as cm:
            pl = Pipeline([("date",),("date",)], stdout=3.14159)
            pl.wait()
        self.commonChecks(nopen, None, None)

    def testBogusStderr(self):
        # test stderr specification is not legal
        nopen = self.numOpenFiles()
        with self.assertRaisesRegexp(PipettorException, "^invalid stdio specification object type: <type 'float'>$") as cm:
            pl = Pipeline([("date",),("date",)], stderr=3.14159)
            pl.wait()
        self.commonChecks(nopen, None, None)


        
class PopenTests(TestCaseBase):
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
        outf = self.getOutputFile(".out")
        outfGz = self.getOutputFile(".out.gz")

        po = Popen(("gzip", "-1"), "w", other=outfGz)
        self.cpFileToPl("simple1.txt", po)
        po.close()

        Pipeline(("zcat", outfGz), stdout=outf).wait()
        self.diffExpected(".out")

    def testWriteFile(self):
        outf = self.getOutputFile(".out")
        outfGz = self.getOutputFile(".out.gz")

        with open(outfGz, "w") as outfGzFh:
            pl = Popen(("gzip", "-1"), "w", other=outfGzFh)
            self.cpFileToPl("simple1.txt", pl)
            pl.wait()

        Pipeline(("zcat", outfGz), stdout=outf).wait()
        self.diffExpected(".out")

    def testWriteMult(self):
        outf = self.getOutputFile(".wc")

        # grr, BSD wc adds an extract space, so just convert to tabs
        pl = Popen((("gzip", "-1"),
                       ("gzip", "-dc"),
                       ("wc",),
                       ("sed", "-e", "s/  */\t/g")),
                      "w", other=outf)
        self.cpFileToPl("simple1.txt", pl)
        pl.wait()

        self.diffExpected(".wc")

    def testRead(self):
        inf = self.getInputFile("simple1.txt")
        infGz = self.getOutputFile(".txt.gz")
        Pipeline(("gzip", "-c", inf), stdout=infGz).wait()

        pl = Popen(("gzip", "-dc"), "r", other=infGz)
        self.cpPlToFile(pl, ".out")
        pl.wait()

        self.diffExpected(".out")

    def testReadMult(self):
        inf = self.getInputFile("simple1.txt")

        pl = Popen((("gzip","-1c"),
                       ("gzip", "-dc"),
                       ("wc",),
                       ("sed", "-e", "s/  */\t/g")),
                      "r", other=inf)
        self.cpPlToFile(pl, ".wc")
        pl.wait()

        self.diffExpected(".wc")

    def testExitCode(self):
        pl = Popen(("false",))
        with self.assertRaisesRegexp(ProcessException, "^process exited 1: false$") as cm:
            pl.wait()
        for p in pl.procs:
            self.assertTrue(p.returncode == 1)

    def testSigPipe(self):
        # test not reading all of pipe output
        pl = Popen([("yes",), ("true",)], "r")
        pl.wait()
        
def suite():
    ts = unittest.TestSuite()
    ts.addTest(unittest.makeSuite(PipelineTests))
    ts.addTest(unittest.makeSuite(PopenTests))
    return ts

if __name__ == '__main__':
    unittest.main()
