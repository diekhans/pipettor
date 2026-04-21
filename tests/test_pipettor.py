# -*- coding: utf-8 -*-
# Copyright 2006-2025 Mark Diekhans
import pytest
import sys
import os
import os.path as osp
import re
import shutil
from pathlib import Path

sys.path = [osp.normpath(osp.dirname(__file__) + "/../lib"),
            osp.normpath(osp.dirname(__file__))] + sys.path

import testing_support as ts
from pipettor import (Pipeline, Popen, ProcessException, PipettorException,
                      DataReader, DataWriter, StreamReader, StreamWriter,
                      File, run, runout, runlex, runlexout)

def _get_prog_with_error_cmd(request, *args):
    return (os.path.join(ts.get_test_dir(request), "progWithError"),) + args

@pytest.fixture(autouse=True)
def _check_no_leaks():
    "snapshot open-file / process / thread state and assert unchanged at teardown"
    nopen = ts.get_num_open_files()
    yield
    ts.assert_no_child_procs()
    ts.assert_num_open_files_same(nopen)
    ts.assert_single_thread()

def check_pipeline_str(pipeline, expect_str, is_re=False):
    """Check str(pipeline) against expect_str (literal or regex)."""
    s = str(pipeline)
    if is_re:
        if not re.search(expect_str, s):
            pytest.fail(f"'{s}' doesn't match RE '{expect_str}'")
    else:
        assert s == expect_str

def check_prog_with_error(proc_except, prog_args=None):
    expect_re_tmpl = "^process exited 1: .+/progWithError{}{}:\nTHIS GOES TO STDERR{}{}.*$"
    if prog_args is not None:
        expect_re = expect_re_tmpl.format(" ", prog_args, ": ", prog_args)
    else:
        expect_re = expect_re_tmpl.format("", "", "", "")
    if not re.match(expect_re, str(proc_except), re.MULTILINE):
        pytest.fail(f"'{proc_except}' does not match '{expect_re}'")

###
# Pipeline tests
###

def test_trivial():
    pl = Pipeline(("true",))
    pl.wait()
    check_pipeline_str(pl, "true 2>[DataReader]")

def test_trivial_poll():
    pl = Pipeline(("sleep", "1"))
    while not pl.poll():
        pass
    pl.wait()
    check_pipeline_str(pl, "sleep 1 2>[DataReader]")

def test_trivial_fail_poll():
    pl = Pipeline([("sleep", "1"), ("false",)])
    with pytest.raises(ProcessException, match="^process exited 1: sleep 1 | false$"):
        pl.wait()
    check_pipeline_str(pl, "sleep 1 | false 2>[DataReader]")

def test_trivial_status():
    pl = Pipeline(("true",))
    pl.start()
    assert pl.running
    assert not pl.finished
    pl.wait()
    assert not pl.running
    assert pl.finished
    check_pipeline_str(pl, "true 2>[DataReader]")

def test_simple_pipe():
    log = ts.LoggerForTests()
    pl = Pipeline([("true",), ("true",)], logger=log.logger)
    pl.wait()
    check_pipeline_str(pl, "true | true 2>[DataReader]")
    assert log.data == ("""start: true | true 2>[DataReader]\n"""
                        """success: true | true 2>[DataReader]\n""")

def test_simple_pipe_fail():
    log = ts.LoggerForTests()
    pl = Pipeline([("false",), ("true",)], logger=log.logger)
    with pytest.raises(ProcessException, match="^process exited 1: false$"):
        pl.wait()
    check_pipeline_str(pl, "false | true 2>[DataReader]")
    assert re.search("""^start: false | true 2>[DataReader]\n"""
                     """failure: false | true 2>[DataReader]: process exited 1: false\n.*""",
                     log.data, re.MULTILINE)

def test_path_obj():
    log = ts.LoggerForTests()
    true_path = Path(shutil.which("true"))
    pl = Pipeline([(true_path,), (true_path,)], logger=log.logger)
    pl.wait()
    tp = str(true_path)
    check_pipeline_str(pl, f"{tp} | {tp} 2>[DataReader]")
    assert log.data == (f"start: {tp} | {tp} 2>[DataReader]\n"
                        f"success: {tp} | {tp} 2>[DataReader]\n")

def test_pipe_fail_stderr(request):
    # should report first failure
    pl = Pipeline([("true",), _get_prog_with_error_cmd(request), ("false",)], stderr=DataReader)
    with pytest.raises(ProcessException) as cm:
        pl.wait()
    check_prog_with_error(cm.value)

def test_pipe_fail3_stderr(request):
    # all 3 process fail
    # should report first failure
    pl = Pipeline([_get_prog_with_error_cmd(request, "process0"),
                   _get_prog_with_error_cmd(request, "process1"),
                   _get_prog_with_error_cmd(request, "process2")],
                  stderr=DataReader)
    with pytest.raises(ProcessException) as cm:
        pl.wait()
    # should be first process
    check_prog_with_error(cm.value, "process0")
    # check process
    for i in range(3):
        check_prog_with_error(pl.procs[i].procExcept, "process{}".format(i))

def test_exec_fail():
    # invalid executable
    dw = DataWriter("one\ntwo\nthree\n")
    pl = Pipeline(("procDoesNotExist", "-r"), stdin=dw)
    with pytest.raises(ProcessException) as cm:
        pl.wait()
    assert re.search("exec failed: procDoesNotExist -r.*", str(cm.value))
    assert cm.value.__cause__ is not None
    assert re.search("\\[Errno 2\\] No such file or directory: 'procDoesNotExist'.*",
                     str(cm.value.__cause__))
    check_pipeline_str(pl, "procDoesNotExist -r <[DataWriter] 2>[DataReader]")

def test_signaled():
    # process signals
    pl = Pipeline(("sh", "-c", "kill -11 $$"))
    with pytest.raises(ProcessException) as cm:
        pl.wait()
    expect = "process signaled: SIGSEGV: sh -c 'kill -11 $$'"
    msg = str(cm.value)
    if not msg.startswith(expect):
        pytest.fail(f"'{msg}' does not start with '{expect}', cause: " + str(getattr(cm.value, "cause", None)))
    check_pipeline_str(pl, "sh -c 'kill -11 $$' 2>[DataReader]")

def test_stdin_mem(request):
    # write from memory to stdin
    outf = ts.get_test_output_file(request, ".out")
    dw = DataWriter("one\ntwo\nthree\n")
    pl = Pipeline(("sort", "-r"), stdin=dw, stdout=outf)
    pl.wait()
    ts.diff_results_expected(request, ".out")
    check_pipeline_str(pl, "^sort -r <\\[DataWriter\\] >.+/output/test_pipettor.py::test_stdin_mem\\.out 2>\\[DataReader\\]$", is_re=True)

def test_stdout_mem(request):
    # read from stdout into memory
    inf = ts.get_test_input_file(request, "simple1.txt")
    dr = DataReader()
    pl = Pipeline(("sort", "-r"), stdin=inf, stdout=dr)
    pl.wait()
    assert dr.data == "two\nthree\nsix\none\nfour\nfive\n"
    check_pipeline_str(pl, "^sort -r <.+/input/simple1\\.txt >\\[DataReader\\]", is_re=True)

def test_stdin_stdout_mem():
    # write and read from memory
    dw = DataWriter("one\ntwo\nthree\n")
    dr = DataReader()
    pl = Pipeline([("cat", "-u"), ("cat", "-u")], stdin=dw, stdout=dr)
    pl.wait()
    assert dr.data == "one\ntwo\nthree\n"
    check_pipeline_str(pl, "^cat -u <\\[DataWriter\\] \\| cat -u >\\[DataReader\\] 2>\\[DataReader\\]$", is_re=True)

def test_file_mode():
    with pytest.raises(PipettorException, match="^invalid or unsupported mode 'q' opening /dev/null"):
        File("/dev/null", "q")

def test_collect_stdout_err():
    # independent collection of stdout and stderr
    stdoutRd = DataReader()
    stderrRd = DataReader()
    pl = Pipeline(("sh", "-c", "echo this goes to stdout; echo this goes to stderr >&2"),
                  stdout=stdoutRd, stderr=stderrRd)
    pl.wait()
    assert stdoutRd.data == "this goes to stdout\n"
    assert stderrRd.data == "this goes to stderr\n"
    check_pipeline_str(pl, "sh -c 'echo this goes to stdout; echo this goes to stderr >&2' >[DataReader] 2>[DataReader]")

def test_stdin_mem_binary(request):
    # binary write from memory to stdin
    outf = ts.get_test_output_file(request, ".out")
    fh = open(ts.get_test_input_file(request, "file.binary"), "rb")
    dw = DataWriter(fh.read())
    fh.close()
    pl = Pipeline(("cat",), stdin=dw, stdout=outf)
    pl.wait()
    ts.diff_results_binary_expected(request, ".out", expect_basename="file.binary")
    check_pipeline_str(pl, "^cat <\\[DataWriter] >.*/output/test_pipettor.py::test_stdin_mem_binary.out 2>\\[DataReader\\]$", is_re=True)

def test_stdout_mem_binary(request):
    # binary read from stdout into memory
    inf = ts.get_test_input_file(request, "file.binary")
    dr = DataReader(binary=True)
    pl = Pipeline(("cat",), stdin=inf, stdout=dr)
    pl.wait()
    fh = open(ts.get_test_output_file(request, ".out"), "wb")
    fh.write(dr.data)
    fh.close()
    ts.diff_results_binary_expected(request, ".out", expect_basename="file.binary")
    check_pipeline_str(pl, "^cat <.*/input/file.binary >\\[DataReader] 2>\\[DataReader\\]$", is_re=True)

def test_write_file(request):
    # test write to File object
    inf = ts.get_test_input_file(request, "simple1.txt")
    outf = ts.get_test_output_file(request, ".out")
    # double cat actually found a bug
    pl = Pipeline([("cat",), ("cat",)], stdin=inf, stdout=File(outf, "w"))
    pl.wait()
    ts.diff_results_expected(request, ".out")
    check_pipeline_str(pl, "cat <.*/input/simple1.txt \\| cat >.*/output/test_pipettor.py::test_write_file.out 2>\\[DataReader\\]$", is_re=True)

def test_read_file(request):
    # test read and write to File object
    inf = ts.get_test_input_file(request, "simple1.txt")
    outf = ts.get_test_output_file(request, ".out")
    pl = Pipeline([("cat",), ("cat",)], stdin=File(inf), stdout=File(outf, "w"))
    pl.wait()
    ts.diff_results_expected(request, ".out")
    check_pipeline_str(pl, "cat <.*/input/simple1.txt \\| cat >.*/output/test_pipettor.py::test_read_file.out 2>\\[DataReader\\]$", is_re=True)

def test_append_file(request):
    # test append to File object
    inf = ts.get_test_input_file(request, "simple1.txt")
    outf = ts.get_test_output_file(request, ".out")
    # double cat actually found a bug
    pl = Pipeline([("cat",), ("cat",)], stdin=inf, stdout=File(outf, "w"), stderr=None)
    pl.wait()
    pl = Pipeline([("cat",), ("cat",)], stdin=inf, stdout=File(outf, "a"), stderr=None)
    pl.wait()
    ts.diff_results_expected(request, ".out")
    check_pipeline_str(pl, "cat <.*/input/simple1.txt \\| cat >.*/output/test_pipettor.py::test_append_file.out$", is_re=True)


_bogus_stdio_expect_re = "^invalid stdio specification object type: <class 'float'> 3\\.14159$"

def test_bogus_stdin(request):
    # test stdin specification is not legal
    with pytest.raises(PipettorException, match=_bogus_stdio_expect_re):
        pl = Pipeline([("date",), ("date",)], stdin=3.14159)
        pl.wait()

def test_bogus_stdout():
    # test stdout specification is not legal
    with pytest.raises(PipettorException, match=_bogus_stdio_expect_re):
        pl = Pipeline([("date",), ("date",)], stdout=3.14159)
        pl.wait()

def test_bogus_stderr():
    # test stderr specification is not legal
    with pytest.raises(PipettorException, match=_bogus_stdio_expect_re):
        pl = Pipeline([("date",), ("date",)], stderr=3.14159)
        pl.wait()

def test_data_reader_share():
    # test stderr linked to stdout/stderr
    dr = DataReader()
    pl = Pipeline([("date",), ("date",)], stdout=dr, stderr=dr)
    pl.wait()

def test_data_writer_bogus_share():
    # test stderr specification is not legal
    dw = DataWriter("fred")
    with pytest.raises(PipettorException, match="^DataWriter already bound to a process$"):
        pl1 = Pipeline([("cat", "/dev/null"), ("cat", "/dev/null")], stdin=dw)
        Pipeline([("cat", "/dev/null"), ("cat", "/dev/null")], stdin=dw)
    pl1.shutdown()  # clean up unstarted process

def test_int_arg(request):
    inf = ts.get_test_input_file(request, "simple1.txt")
    dr = DataReader()
    pl = Pipeline(("head", -2), stdin=inf, stdout=dr)
    pl.wait()
    assert dr.data == "one\ntwo\n"
    check_pipeline_str(pl, "^head -2 <.+/input/simple1\\.txt >\\[DataReader\\]", is_re=True)

def test_stderr_pipe_redir():
    # stderr DataReader on multiple processes
    stderr = DataReader(errors='backslashreplace')
    cmds = (["sh", "-c", "echo command one >&2"],
            ["sh", "-c", "echo COMMAND TWO >&2"])
    pl = Pipeline(cmds, stdout='/dev/null', stderr=stderr)
    pl.wait()
    # can't predict order
    err_sorted = list(sorted(stderr.data.strip().split('\n')))
    assert err_sorted == ['COMMAND TWO', 'command one']

###
# Popen tests
###

def cp_file_to_pl(request, in_name, pl):
    inf = ts.get_test_input_file(request, in_name)
    fh = open(inf)
    for line in fh:
        pl.write(line)
    fh.close()

def cp_pl_to_file(request, pl, out_ext):
    outf = ts.get_test_output_file(request, out_ext)
    fh = open(outf, "w")
    for line in pl:
        fh.write(line)
    fh.close()

def test_popen_write(request):
    outf = ts.get_test_output_file(request, ".out")
    outfGz = ts.get_test_output_file(request, ".out.gz")

    pl = Popen(("gzip", "-1"), "w", stdout=outfGz)
    cp_file_to_pl(request, "simple1.txt", pl)
    pl.close()
    check_pipeline_str(pl, "gzip -1 <.+ >.*output/test_pipettor.py::test_popen_write.out.gz", is_re=True)

    # macOS Ventura: user gunzip rather than zcat, as zcat did not support .gz
    Pipeline(("gunzip", "-c", outfGz), stdout=outf).wait()
    ts.diff_results_expected(request, ".out")

def test_popen_write_file(request):
    outf = ts.get_test_output_file(request, ".out")
    outfGz = ts.get_test_output_file(request, ".out.gz")

    with open(outfGz, "w") as outfGzFh:
        pl = Popen(("gzip", "-1"), "w", stdout=outfGzFh)
        cp_file_to_pl(request, "simple1.txt", pl)
        pl.wait()

    # macOS Ventura: don't used zcat; would need to use gzcat, but this is compatbile with all
    Pipeline(("gunzip", "-c", outfGz), stdout=outf).wait()
    ts.diff_results_expected(request, ".out")
    check_pipeline_str(pl, "gzip -1 <.* >.*output/test_pipettor.py::test_popen_write_file.out.gz", is_re=True)

def test_popen_write_mult(request):
    outf = ts.get_test_output_file(request, ".wc")

    # grr, BSD wc adds an extract space, so just convert to tabs
    pl = Popen((("gzip", "-1"),
                ("gzip", "-dc"),
                ("wc",),
                ("sed", "-e", "s/  */\t/g")), "w", stdout=outf)
    cp_file_to_pl(request, "simple1.txt", pl)
    pl.wait()

    ts.diff_results_expected(request, ".wc")
    check_pipeline_str(pl, "^gzip -1 <.+ | gzip -dc | wc | sed -e 's/  \\*/	/g' >.*output/test_pipettor::.test_popen_write_mult.wc$", is_re=True)

def test_popen_read(request):
    inf = ts.get_test_input_file(request, "simple1.txt")
    infGz = ts.get_test_output_file(request, ".txt.gz")
    Pipeline(("gzip", "-c", inf), stdout=infGz).wait()

    pl = Popen(("gzip", "-dc"), "r", stdin=infGz)
    cp_pl_to_file(request, pl, ".out")
    pl.wait()

    ts.diff_results_expected(request, ".out")
    check_pipeline_str(pl, "^gzip -dc <.*output/test_pipettor.py::test_popen_read.txt.gz >.+$", is_re=True)

def test_popen_read_for(request):
    inf = ts.get_test_input_file(request, "simple1.txt")
    infGz = ts.get_test_output_file(request, ".txt.gz")
    Pipeline(("gzip", "-c", inf), stdout=infGz).wait()

    outf = ts.get_test_output_file(request, ".out")
    with open(outf, "w") as outfh:
        for line in Popen(("zcat", infGz)):
            outfh.write(line)
    ts.diff_results_expected(request, ".out")

def test_popen_read_for_error():
    # error in for loop read
    with pytest.raises(ProcessException, match="^process exited 1: zcat /does/not/exist$"):
        for line in Popen(("zcat", "/does/not/exist")):
            pass

def test_popen_read_mult(request):
    inf = ts.get_test_input_file(request, "simple1.txt")

    pl = Popen((("gzip", "-1c"),
                ("gzip", "-dc"),
                ("wc",),
                ("sed", "-e", "s/  */\t/g")), "r", stdin=inf)
    cp_pl_to_file(request, pl, ".wc")
    pl.wait()

    ts.diff_results_expected(request, ".wc")
    check_pipeline_str(pl, "^gzip -1c <.*tests/input/simple1.txt | gzip -dc | wc | sed -e 's/  \\*/	/g' >.+$", is_re=True)

def test_popen_exit_code():
    pl = Popen(("false",))
    with pytest.raises(ProcessException, match="^process exited 1: false$"):
        pl.wait()
    for p in pl.procs:
        assert p.returncode == 1
    check_pipeline_str(pl, "^false >.+$", is_re=True)


simple_one_lines = ['one\n', 'two\n', 'three\n', 'four\n', 'five\n', 'six\n']

def test_popen_read_dos(request):
    with Popen(("cat", ts.get_test_input_file(request, "simple1.dos.txt")), mode="r") as fh:
        lines = [l for l in fh]
    assert lines == simple_one_lines

def test_popen_read_mac(request):
    with Popen(("cat", ts.get_test_input_file(request, "simple1.mac.txt")), mode="r") as fh:
        lines = [l for l in fh]
    assert lines == simple_one_lines

def test_popen_sig_pipe():
    # test not reading all of pipe output
    pl = Popen([("yes",), ("true",)], "r")
    pl.wait()
    check_pipeline_str(pl, "^yes | true >.+ 2>\\[DataReader\\]$", is_re=True)

def test_popen_read_as_ascii_replace(request):
    # file contains unicode character outside of the ASCII range
    inf = ts.get_test_input_file(request, "nonAscii.txt")
    with Popen(["cat", inf], encoding='latin-1', errors="replace") as fh:
        lines = [l[:-1] for l in fh]
    assert ['Microtubules are assembled from dimers of a- and \xc3\x9f-tubulin.'] == lines

def test_popen_bidi_write_then_read():
    # write all input, close_stdin, drain all output
    with Popen([("cat", "-u"), ("cat", "-u")], "r+") as pl:
        for i in range(20):
            pl.write(f"line{i}\n")
        pl.close_stdin()
        got = list(pl)
    assert got == [f"line{i}\n" for i in range(20)]

def test_popen_bidi_interleaved():
    # interleaved write+readline; cat -u keeps 1:1 so no deadlock
    got = []
    with Popen([("cat", "-u"), ("cat", "-u")], "r+", buffering=1) as pl:
        for i in range(20):
            pl.write(f"line{i}\n")
            got.append(pl.readline())
        pl.close_stdin()
        assert pl.read() == ""
    assert got == [f"line{i}\n" for i in range(20)]

def test_popen_bidi_binary():
    # binary bidi roundtrip
    payload = bytes(range(256))
    with Popen(("cat",), "rb+") as pl:
        pl.write(payload)
        pl.close_stdin()
        got = pl.read()
    assert got == payload

def test_popen_bidi_rejects_stdin():
    with pytest.raises(PipettorException, match="can not specify stdin with write mode"):
        Popen(("cat",), "r+", stdin="/dev/null")

def test_popen_bidi_rejects_stdout():
    with pytest.raises(PipettorException, match="can not specify stdout with read mode"):
        Popen(("cat",), "r+", stdout="/dev/null")

def test_popen_invalid_mode_append():
    with pytest.raises(PipettorException, match="can not specify append mode"):
        Popen(("cat",), "a")

def test_popen_invalid_mode_empty():
    with pytest.raises(PipettorException, match="invalid mode"):
        Popen(("cat",), "")

def test_popen_iobase_conformance():
    # Popen should be a proper io.IOBase subclass
    import io
    with Popen(("echo", "hi"), "r") as p:
        assert isinstance(p, io.IOBase)
        assert p.readable()
        assert not p.writable()
        assert not p.seekable()
        with pytest.raises(io.UnsupportedOperation):
            p.seek(0)
        with pytest.raises(io.UnsupportedOperation):
            p.truncate()
        assert p.readline() == "hi\n"

def test_popen_bidi_fileno_ambiguous():
    # in bidi mode fileno cannot choose a side
    import io
    with Popen(("cat",), "r+") as p:
        with pytest.raises(io.UnsupportedOperation):
            p.fileno()
        p.close_stdin()

def test_popen_close_stdin_half_close():
    # close_stdin sends EOF; remaining output still readable
    with Popen([("cat", "-u"), ("cat", "-u")], "r+", buffering=1) as pl:
        pl.write("one\ntwo\nthree\n")
        pl.close_stdin()
        assert pl.read() == "one\ntwo\nthree\n"

def test_data_writer_iterable_str():
    expected = [f"line{i}\n" for i in range(50)]
    dr = DataReader()
    Pipeline(("cat",), stdin=DataWriter(expected), stdout=dr).wait()
    assert dr.data == "".join(expected)

def test_data_writer_iterable_generator():
    def gen():
        for i in range(20):
            yield f"v{i}\n"
    dr = DataReader()
    Pipeline(("cat",), stdin=DataWriter(gen()), stdout=dr).wait()
    assert dr.data == "".join(f"v{i}\n" for i in range(20))

def test_data_writer_iterable_bytes():
    chunks = [bytes([i]) * 8 for i in range(10)]
    dr = DataReader(binary=True)
    Pipeline(("cat",), stdin=DataWriter(iter(chunks), binary=True), stdout=dr).wait()
    assert dr.data == b"".join(chunks)

def test_data_writer_iterable_empty():
    dr = DataReader()
    Pipeline(("cat",), stdin=DataWriter(iter(())), stdout=dr).wait()
    assert dr.data == ""

def test_stream_reader_double_bind():
    sr = StreamReader()
    Pipeline(("cat",), stdout=sr).wait()
    with pytest.raises(PipettorException, match="StreamReader already bound"):
        Pipeline(("cat",), stdout=sr).wait()

def test_stream_writer_double_bind():
    sw = StreamWriter()
    pl = Pipeline(("cat", "/dev/null"), stdin=sw)
    with pytest.raises(PipettorException, match="StreamWriter already bound"):
        Pipeline(("cat", "/dev/null"), stdin=sw)
    sw.close()
    pl.shutdown()

def test_stream_reader_file_like_attrs():
    sr = StreamReader()
    pl = Pipeline(("echo", "hi"), stdout=sr)
    pl.start()
    assert sr.readable() and not sr.writable()
    assert not sr.seekable()
    assert not sr.isatty()
    assert sr.fileno() >= 0
    sr.flush()
    assert str(sr) == "[StreamReader]"
    assert sr.readlines() == ["hi\n"]
    pl.wait()
    assert sr.closed

def test_stream_reader_next():
    sr = StreamReader()
    pl = Pipeline(("printf", "a\\nb\\n"), stdout=sr)
    pl.start()
    assert next(sr) == "a\n"
    assert next(sr) == "b\n"
    with pytest.raises(StopIteration):
        next(sr)
    pl.wait()

def test_stream_writer_file_like_attrs():
    sw = StreamWriter()
    with Popen(("cat",), "r", stdin=sw) as pl:
        assert not sw.readable() and sw.writable()
        sw.writelines(["a\n", "b\n"])
        sw.close()
        assert pl.read() == "a\nb\n"
    assert str(sw) == "[StreamWriter]"

def test_stream_reader_context_manager():
    sr = StreamReader()
    Pipeline(("echo", "ctx"), stdout=sr).wait()
    with sr as s:
        assert s is sr
    assert sr.closed

def test_popen_poll_unsupported():
    import io
    with Popen(("true",), "r") as pl:
        with pytest.raises(io.UnsupportedOperation):
            pl.poll()

def test_popen_tell_unsupported():
    # pipes are not seekable, so tell() on the underlying pipe fh raises
    import io
    with Popen(("echo", "x"), "r") as pl:
        with pytest.raises(io.UnsupportedOperation):
            pl.tell()

def test_popen_iter_autoclose():
    pl = Popen(("printf", "a\\nb\\n"))
    lines = list(pl)
    assert lines == ["a\n", "b\n"]
    assert pl.closed

def test_pipeline_start_twice_raises():
    pl = Pipeline(("true",))
    pl.start()
    with pytest.raises(PipettorException, match="already been started"):
        pl.start()
    pl.wait()

def test_pipeline_shutdown_running():
    # shutdown kills running processes and swallows the resulting exception
    pl = Pipeline(("sleep", "30"))
    pl.start()
    pl.shutdown()
    assert all(p.finished for p in pl.procs)

def test_pipeline_shutdown_unstarted():
    # no start: shutdown just cleans up devices
    pl = Pipeline(("true",))
    pl.shutdown()
    assert pl.finished

def test_pipeline_kill():
    pl = Pipeline(("sleep", "30"))
    pl.start()
    pl.kill()
    with pytest.raises(ProcessException):
        pl.wait()

def test_data_reader_get_child_write_fd_unknown():
    from pipettor.processes import Process
    dr = DataReader()
    # bind to one process, query with an unrelated one
    Pipeline(("true",), stdout=dr).wait()
    fake = Process(("x",), logger=None)
    with pytest.raises(ValueError, match="not associated"):
        dr.get_child_write_fd(fake)

def test_default_logger_setters():
    from pipettor import (setDefaultLogger, getDefaultLogger,
                          setDefaultLogLevel, getDefaultLogLevel,
                          setDefaultLogging)
    import logging as _logging
    orig_logger = getDefaultLogger()
    orig_level = getDefaultLogLevel()
    try:
        setDefaultLogger("test_pipettor_logger")
        assert getDefaultLogger().name == "test_pipettor_logger"
        setDefaultLogger(_logging.getLogger("direct"))
        assert getDefaultLogger().name == "direct"
        setDefaultLogLevel(_logging.INFO)
        assert getDefaultLogLevel() == _logging.INFO
        setDefaultLogging("combined", _logging.WARNING)
        assert getDefaultLogger().name == "combined"
        assert getDefaultLogLevel() == _logging.WARNING
        setDefaultLogging(None, None)  # both None = no-op
        assert getDefaultLogger().name == "combined"
    finally:
        setDefaultLogger(orig_logger)
        setDefaultLogLevel(orig_level)

def test_logger_as_string_arg():
    # logger kwarg resolves a string to a logger
    log = ts.LoggerForTests()
    log.logger.name = "pipettor_str_arg_test"
    import logging as _logging
    _logging.getLogger("pipettor_str_arg_test").handlers = log.logger.handlers
    Pipeline(("true",), logger="pipettor_str_arg_test").wait()

def test_env_passing():
    env = dict(os.environ)
    env['PIPETTOR'] = "YES"

    got_it = False
    with Popen(["env"], env=env) as fh:
        for line in fh:
            if line.strip() == "PIPETTOR=YES":
                got_it = True
    assert got_it, "PIPETTOR=YES not set in enviroment"

###
# function tests
###

def test_fn_write_file(request):
    # test write to File object
    inf = ts.get_test_input_file(request, "simple1.txt")
    outf = ts.get_test_output_file(request, ".out")
    run([("cat",), ("cat",)], stdin=inf, stdout=File(outf, "w"))
    ts.diff_results_expected(request, ".out")

def test_fn_path_obj():
    true_path = Path(shutil.which("true"))
    run([true_path])

def test_fn_simple_pipe_fail():
    with pytest.raises(ProcessException, match="^process exited 1: false$"):
        run([("false",), ("true",)])

def test_fn_stdout_read(request):
    # read from stdout into memory
    inf = ts.get_test_input_file(request, "simple1.txt")
    out = runout(("sort", "-r"), stdin=inf)
    assert out == "two\nthree\nsix\none\nfour\nfive\n"

def test_fn_stdout_read_fail(request):
    # read from stdout into memory
    inf = ts.get_test_input_file(request, "simple1.txt")
    with pytest.raises(ProcessException) as cm:
        runout([("sort", "-r"), _get_prog_with_error_cmd(request), ("false",)], stdin=inf)
    check_prog_with_error(cm.value)

def test_fn_write_file_lex(request):
    # test write to File object
    inf = ts.get_test_input_file(request, "simple1.txt")
    outf = ts.get_test_output_file(request, ".out")
    runlex(["cat -u", ["cat", "-u"], "cat -n"], stdin=inf, stdout=File(outf, "w"))
    ts.diff_results_expected(request, ".out")

def test_fn_stdout_read_lex(request):
    # read from stdout into memory
    inf = ts.get_test_input_file(request, "simple1.txt")
    out = runlexout("sort -r", stdin=inf)
    assert out == "two\nthree\nsix\none\nfour\nfive\n"

def test_fn_env_passing():
    env = dict(os.environ)
    env['PIPETTOR'] = "YES"
    lines = runout(["env"], env=env).splitlines()
    assert "PIPETTOR=YES" in lines

###
# StreamReader / StreamWriter tests
###

def test_stream_reader():
    # StreamReader reads pipeline output directly, line-by-line
    expected = [f"line{i}\n" for i in range(10)]
    sr = StreamReader()
    pl = Pipeline([("cat", "-u"), ("cat", "-u")],
                  stdin=DataWriter("".join(expected)), stdout=sr)
    pl.start()
    got = [line for line in sr]
    pl.wait()
    assert got == expected

def test_stream_writer():
    # StreamWriter pushes lines to pipeline stdin; read back via DataReader
    dr = DataReader()
    sw = StreamWriter()
    pl = Pipeline([("cat", "-u"), ("cat", "-u")], stdin=sw, stdout=dr)
    pl.start()
    expected = [f"line{i}\n" for i in range(50)]
    for ln in expected:
        sw.write(ln)
    sw.close()
    pl.wait()
    assert dr.data == "".join(expected)

def test_stream_interleaved():
    # StreamWriter + StreamReader interleaved loop on main thread.
    # cat -u is unbuffered so each write produces a matching line;
    # alternating keeps both pipes drained, no deadlock.
    sw = StreamWriter()
    sr = StreamReader()
    pl = Pipeline([("cat", "-u"), ("cat", "-u")], stdin=sw, stdout=sr)
    pl.start()
    got = []
    for i in range(20):
        sw.write(f"line{i}\n")
        sw.flush()
        got.append(sr.readline())
    sw.close()
    assert sr.read() == ""
    pl.wait()
    assert got == [f"line{i}\n" for i in range(20)]

def test_stream_binary():
    # binary StreamReader/StreamWriter roundtrip
    sw = StreamWriter(binary=True)
    sr = StreamReader(binary=True)
    pl = Pipeline(("cat",), stdin=sw, stdout=sr)
    pl.start()
    payload = bytes(range(256))
    sw.write(payload)
    sw.close()
    assert sr.read() == payload
    pl.wait()
