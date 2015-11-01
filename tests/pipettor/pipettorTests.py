# Copyright 2006-2012 Mark Diekhans
import unittest, sys, os, re
if __name__ == '__main__':
    sys.path.append(os.path.normpath(os.path.dirname(sys.argv[0]))+"/../..")
from pipettor.pipettor import Pipeline, Popen, ProcException, PipettorException, DataReader, DataWriter
from tests.pipettor.testCaseBase import TestCaseBase

# this keeps OS/X crash reporter from popping up on unittest error
import signal
signal.signal(signal.SIGQUIT,
              lambda signum, frame: sys.exit(os.EX_SOFTWARE))
signal.signal(signal.SIGABRT,
              lambda signum, frame: sys.exit(os.EX_SOFTWARE))


# FIXME from: ccds2/modules/gencode/src/progs/gencodeMakeTracks/gencodeGtfToGenePred
# this doesn't work, nothing is returned by the readers,
# used to fix Pipeline at some time
class ChrMLifterBROKEN(object):
    "Do lifting to of chrM"
    def __init__(self, liftFile):
        self.mappedRd = DataReader()
        self.droppedRd = DataReader()
        self.pipeline = Pipeline(["liftOver", "-genePred", "stdin", liftFile, self.mappedRd, self.droppedRd], "w")

    def write(self, gp):
        gp.name = "NC_012920"
        gp.write(self.pipeline)

    def __checkForDropped(self):
        "check if anything written to the dropped file"
        dropped = [gp for gp in GenePredFhReader(StringIO(self.droppedRd.get()))]
        if len(dropped) > 0:
            raise Exception("chrM liftOver dropped " + str(len(dropped)) + " records")

    def finishLifting(self, gpOutFh):
        self.pipeline.wait()
        for gp in GenePredFhReader(StringIO(self.mappedRd.get())):
            gp.write(gpOutFh)
        self.__checkForDropped()


class PipelineTests(TestCaseBase):
    def commonChecks(self, nopen, pd, expectStr, isRe=False):
        """check that files, threads, and processes have not leaked. Check str(pd)
        against expectStr, which can be a string, or an regular expression if
        isRe==True, or None to not check."""
        s = str(pd)
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
        pd = Pipeline(("true",))
        pd.wait()
        self.commonChecks(nopen, pd, "true")

    def testTrivialFail(self):
        nopen = self.numOpenFiles()
        pd = Pipeline(("false",))
        with self.assertRaisesRegexp(ProcException, "^process exited 1: false$") as cm:
            pd.wait()
        self.commonChecks(nopen, pd, "false")

    def testSimplePipe(self):
        nopen = self.numOpenFiles()
        pd = Pipeline([("true",), ("true",)])
        pd.wait()
        self.commonChecks(nopen, pd, "true | true")

    def testSimplePipeFail(self):
        nopen = self.numOpenFiles()
        pd = Pipeline([("false",), ("true",)])
        with self.assertRaisesRegexp(ProcException, "^process exited 1: false$") as cm:
            pd.wait()
        self.commonChecks(nopen, pd, "false | true")

    def testExecFail(self):
        "invalid executable"
        nopen = self.numOpenFiles()
        dw = DataWriter("one\ntwo\nthree\n")
        pd = Pipeline(("procDoesNotExist","-r"), stdin=dw)
        with self.assertRaises(ProcException) as cm:
            pd.wait()
        expect = "exec failed: procDoesNotExist -r,\n    caused by: OSError: [Errno 2] No such file or directory"
        msg = str(cm.exception)
        if not msg.startswith(expect):
            self.fail("'"+ msg + "' does not start with '"
                      + expect + "', cause: " + str(getattr(cm.exception,"cause", None)))
        self.commonChecks(nopen, pd, "procDoesNotExist -r <[DataWriter]")

    def testStdinMem(self):
        "write from memory to stdin"
        nopen = self.numOpenFiles()
        outf = self.getOutputFile(".out")
        dw = DataWriter("one\ntwo\nthree\n")
        pd = Pipeline(("sort","-r"), stdin=dw, stdout=outf)
        pd.wait()
        self.diffExpected(".out")
        self.commonChecks(nopen, pd, "^sort -r <\\[DataWriter\\] >.+/output/pipettorTests\\.PipelineTests\\.testStdinMem\\.out$", isRe=True)

    def testStdoutMem(self):
        "read from stdout into memory"
        nopen = self.numOpenFiles()
        inf = self.getInputFile("simple1.txt")
        dr = DataReader()
        pd = Pipeline(("sort","-r"), stdin=inf, stdout=dr)
        pd.wait()
        self.assertEqual(dr.data, "two\nthree\nsix\none\nfour\nfive\n")
        self.commonChecks(nopen, pd, "^sort -r <.+/input/simple1\\.txt >\\[DataReader\\]", isRe=True)

    def testStdinStdoutMem(self):
        "write and read from memory"
        nopen = self.numOpenFiles()
        dw = DataWriter("one\ntwo\nthree\n")
        dr = DataReader()
        pd = Pipeline([("cat","-u"),("cat","-u")], stdin=dw, stdout=dr)
        pd.wait()
        self.assertEqual(dr.data, "one\ntwo\nthree\n")
        self.commonChecks(nopen, pd, "^cat -u | cat -u <\\[DataWriter\\] >\\[DataReader\\]$", isRe=True)


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
        with self.assertRaisesRegexp(ProcException, "^process exited 1: false$") as cm:
            pl.wait()
        for p in pl.procs:
            self.assertTrue(p.returncode == 1)

    def testSigPipe(self):
        "test not reading all of pipe output"
        pl = Popen([("yes",), ("true",)], "r")
        pl.wait()
        
def suite():
    ts = unittest.TestSuite()
    ts.addTest(unittest.makeSuite(PipelineTests))
    ts.addTest(unittest.makeSuite(PopenTests))
    return ts

if __name__ == '__main__':
    unittest.main()
