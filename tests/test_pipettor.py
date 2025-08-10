# -*- coding: utf-8 -*-
# Copyright 2006-2025 Mark Diekhans
import pytest
import sys
import os
import os.path as osp
import re
from pathlib import Path

sys.path = [osp.normpath(osp.dirname(__file__) + "/../lib"),
            osp.normpath(osp.dirname(__file__))] + sys.path

import testing_support as ts
from pipettor import Pipeline, Popen, ProcessException, PipettorException, DataReader, DataWriter, File, run, runout, runlex, runlexout

def _get_prog_with_error_cmd(request, *args):
    return (os.path.join(ts.get_test_dir(request), "progWithError"),) + args

def orphan_checks(nopen):
    "check for orphaned child process, open files or threads"
    ts.assert_no_child_procs()
    ts.assert_num_open_files_same(nopen)
    ts.assert_single_thread()

def common_checks(nopen, pipeline, expect_str, is_re=False):
    """check that files, threads, and processes have not leaked. Check str(pipeline)
    against expectStr, which can be a string, or an regular expression if
    is_re==True, or None to not check."""
    s = str(pipeline)
    if expect_str is not None:
        if is_re:
            if not re.search(expect_str, s):
                pytest.fail(f"'{s}' doesn't match RE '{expect_str}'")
        else:
            assert s == expect_str
    orphan_checks(nopen)

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
    nopen = ts.get_num_open_files()
    pl = Pipeline(("true",))
    pl.wait()
    common_checks(nopen, pl, "true 2>[DataReader]")

def test_trivial_poll():
    nopen = ts.get_num_open_files()
    pl = Pipeline(("sleep", "1"))
    while not pl.poll():
        pass
    pl.wait()
    common_checks(nopen, pl, "sleep 1 2>[DataReader]")

def test_trivial_fail_poll():
    nopen = ts.get_num_open_files()
    pl = Pipeline([("sleep", "1"), ("false",)])
    with pytest.raises(ProcessException, match="^process exited 1: sleep 1 | false$"):
        pl.wait()
    common_checks(nopen, pl, "sleep 1 | false 2>[DataReader]")

def test_trivial_status():
    nopen = ts.get_num_open_files()
    pl = Pipeline(("true",))
    pl.start()
    assert pl.running
    assert not pl.finished
    pl.wait()
    assert not pl.running
    assert pl.finished
    common_checks(nopen, pl, "true 2>[DataReader]")

def test_simple_pipe():
    nopen = ts.get_num_open_files()
    log = ts.LoggerForTests()
    pl = Pipeline([("true",), ("true",)], logger=log.logger)
    pl.wait()
    common_checks(nopen, pl, "true | true 2>[DataReader]")
    assert log.data == ("""start: true | true 2>[DataReader]\n"""
                        """success: true | true 2>[DataReader]\n""")

def test_simple_pipe_fail():
    nopen = ts.get_num_open_files()
    log = ts.LoggerForTests()
    pl = Pipeline([("false",), ("true",)], logger=log.logger)
    with pytest.raises(ProcessException, match="^process exited 1: false$"):
        pl.wait()
    common_checks(nopen, pl, "false | true 2>[DataReader]")
    assert re.search("""^start: false | true 2>[DataReader]\n"""
                     """failure: false | true 2>[DataReader]: process exited 1: false\n.*""",
                     log.data, re.MULTILINE)

def test_path_obj():
    nopen = ts.get_num_open_files()
    log = ts.LoggerForTests()
    true_path = Path("/usr/bin/true")
    pl = Pipeline([(true_path,), (true_path,)], logger=log.logger)
    pl.wait()
    common_checks(nopen, pl, "/usr/bin/true | /usr/bin/true 2>[DataReader]")
    assert log.data == ("""start: /usr/bin/true | /usr/bin/true 2>[DataReader]\n"""
                        """success: /usr/bin/true | /usr/bin/true 2>[DataReader]\n""")

def test_pipe_fail_stderr(request):
    nopen = ts.get_num_open_files()
    # should report first failure
    pl = Pipeline([("true",), _get_prog_with_error_cmd(request), ("false",)], stderr=DataReader)
    with pytest.raises(ProcessException) as cm:
        pl.wait()
    check_prog_with_error(cm.value)
    orphan_checks(nopen)

def test_pipe_fail3_stderr(request):
    # all 3 process fail
    nopen = ts.get_num_open_files()
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
    orphan_checks(nopen)

def test_exec_fail():
    # invalid executable
    nopen = ts.get_num_open_files()
    dw = DataWriter("one\ntwo\nthree\n")
    pl = Pipeline(("procDoesNotExist", "-r"), stdin=dw)
    with pytest.raises(ProcessException) as cm:
        pl.wait()
    assert re.search("exec failed: procDoesNotExist -r.*", str(cm.value))
    assert cm.value.__cause__ is not None
    assert re.search("\\[Errno 2\\] No such file or directory: 'procDoesNotExist'.*",
                     str(cm.value.__cause__))
    common_checks(nopen, pl, "procDoesNotExist -r <[DataWriter] 2>[DataReader]")

def test_signaled():
    # process signals
    nopen = ts.get_num_open_files()
    pl = Pipeline(("sh", "-c", "kill -11 $$"))
    with pytest.raises(ProcessException) as cm:
        pl.wait()
    expect = "process signaled: SIGSEGV: sh -c 'kill -11 $$'"
    msg = str(cm.value)
    if not msg.startswith(expect):
        pytest.fail(f"'{msg}' does not start with '{expect}', cause: " + str(getattr(cm.value, "cause", None)))
    common_checks(nopen, pl, "sh -c 'kill -11 $$' 2>[DataReader]")

def test_stdin_mem(request):
    # write from memory to stdin
    nopen = ts.get_num_open_files()
    outf = ts.get_test_output_file(request, ".out")
    dw = DataWriter("one\ntwo\nthree\n")
    pl = Pipeline(("sort", "-r"), stdin=dw, stdout=outf)
    pl.wait()
    ts.diff_results_expected(request, ".out")
    common_checks(nopen, pl, "^sort -r <\\[DataWriter\\] >.+/output/test_pipettor.py::test_stdin_mem\\.out 2>\\[DataReader\\]$", is_re=True)

def test_stdout_mem(request):
    # read from stdout into memory
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "simple1.txt")
    dr = DataReader()
    pl = Pipeline(("sort", "-r"), stdin=inf, stdout=dr)
    pl.wait()
    assert dr.data == "two\nthree\nsix\none\nfour\nfive\n"
    common_checks(nopen, pl, "^sort -r <.+/input/simple1\\.txt >\\[DataReader\\]", is_re=True)

def test_stdin_stdout_mem():
    # write and read from memory
    nopen = ts.get_num_open_files()
    dw = DataWriter("one\ntwo\nthree\n")
    dr = DataReader()
    pl = Pipeline([("cat", "-u"), ("cat", "-u")], stdin=dw, stdout=dr)
    pl.wait()
    assert dr.data == "one\ntwo\nthree\n"
    common_checks(nopen, pl, "^cat -u <\\[DataWriter\\] \\| cat -u >\\[DataReader\\] 2>\\[DataReader\\]$", is_re=True)

def test_file_mode():
    with pytest.raises(PipettorException, match="^invalid or unsupported mode 'q' opening /dev/null"):
        File("/dev/null", "q")

def test_collect_stdout_err():
    # independent collection of stdout and stderr
    nopen = ts.get_num_open_files()
    stdoutRd = DataReader()
    stderrRd = DataReader()
    pl = Pipeline(("sh", "-c", "echo this goes to stdout; echo this goes to stderr >&2"),
                  stdout=stdoutRd, stderr=stderrRd)
    pl.wait()
    assert stdoutRd.data == "this goes to stdout\n"
    assert stderrRd.data == "this goes to stderr\n"
    common_checks(nopen, pl, "sh -c 'echo this goes to stdout; echo this goes to stderr >&2' >[DataReader] 2>[DataReader]")

def test_stdin_mem_binary(request):
    # binary write from memory to stdin
    nopen = ts.get_num_open_files()
    outf = ts.get_test_output_file(request, ".out")
    fh = open(ts.get_test_input_file(request, "file.binary"), "rb")
    dw = DataWriter(fh.read())
    fh.close()
    pl = Pipeline(("cat",), stdin=dw, stdout=outf)
    pl.wait()
    ts.diff_results_binary_expected(request, ".out", expect_basename="file.binary")
    common_checks(nopen, pl, "^cat <\\[DataWriter] >.*/output/test_pipettor.py::test_stdin_mem_binary.out 2>\\[DataReader\\]$", is_re=True)

def test_stdout_mem_binary(request):
    # binary read from stdout into memory
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "file.binary")
    dr = DataReader(binary=True)
    pl = Pipeline(("cat",), stdin=inf, stdout=dr)
    pl.wait()
    fh = open(ts.get_test_output_file(request, ".out"), "wb")
    fh.write(dr.data)
    fh.close()
    ts.diff_results_binary_expected(request, ".out", expect_basename="file.binary")
    common_checks(nopen, pl, "^cat <.*/input/file.binary >\\[DataReader] 2>\\[DataReader\\]$", is_re=True)

def test_write_file(request):
    # test write to File object
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "simple1.txt")
    outf = ts.get_test_output_file(request, ".out")
    # double cat actually found a bug
    pl = Pipeline([("cat",), ("cat",)], stdin=inf, stdout=File(outf, "w"))
    pl.wait()
    ts.diff_results_expected(request, ".out")
    common_checks(nopen, pl, "cat <.*/input/simple1.txt \\| cat >.*/output/test_pipettor.py::test_write_file.out 2>\\[DataReader\\]$", is_re=True)

def test_read_file(request):
    # test read and write to File object
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "simple1.txt")
    outf = ts.get_test_output_file(request, ".out")
    pl = Pipeline([("cat",), ("cat",)], stdin=File(inf), stdout=File(outf, "w"))
    pl.wait()
    ts.diff_results_expected(request, ".out")
    common_checks(nopen, pl, "cat <.*/input/simple1.txt \\| cat >.*/output/test_pipettor.py::test_read_file.out 2>\\[DataReader\\]$", is_re=True)

def test_append_file(request):
    # test append to File object
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "simple1.txt")
    outf = ts.get_test_output_file(request, ".out")
    # double cat actually found a bug
    pl = Pipeline([("cat",), ("cat",)], stdin=inf, stdout=File(outf, "w"), stderr=None)
    pl.wait()
    pl = Pipeline([("cat",), ("cat",)], stdin=inf, stdout=File(outf, "a"), stderr=None)
    pl.wait()
    ts.diff_results_expected(request, ".out")
    common_checks(nopen, pl, "cat <.*/input/simple1.txt \\| cat >.*/output/test_pipettor.py::test_append_file.out$", is_re=True)

_bogus_stdio_expect_re = "^invalid stdio specification object type: <class 'float'> 3\\.14159$"

def test_bogus_stdin(request):
    # test stdin specification is not legal
    nopen = ts.get_num_open_files()
    with pytest.raises(PipettorException, match=_bogus_stdio_expect_re):
        pl = Pipeline([("date",), ("date",)], stdin=3.14159)
        pl.wait()
    orphan_checks(nopen)

def test_bogus_stdout():
    # test stdout specification is not legal
    nopen = ts.get_num_open_files()
    with pytest.raises(PipettorException, match=_bogus_stdio_expect_re):
        pl = Pipeline([("date",), ("date",)], stdout=3.14159)
        pl.wait()
    orphan_checks(nopen)

def test_bogus_stderr():
    # test stderr specification is not legal
    nopen = ts.get_num_open_files()
    with pytest.raises(PipettorException, match=_bogus_stdio_expect_re):
        pl = Pipeline([("date",), ("date",)], stderr=3.14159)
        pl.wait()
    orphan_checks(nopen)

def test_data_reader_share():
    # test stderr linked to stdout/stderr
    nopen = ts.get_num_open_files()
    dr = DataReader()
    pl = Pipeline([("date",), ("date",)], stdout=dr, stderr=dr)
    pl.wait()
    orphan_checks(nopen)

def test_data_writer_bogus_share():
    # test stderr specification is not legal
    nopen = ts.get_num_open_files()
    dw = DataWriter("fred")
    with pytest.raises(PipettorException, match="^DataWriter already bound to a process$"):
        pl1 = Pipeline([("cat", "/dev/null"), ("cat", "/dev/null")], stdin=dw)
        Pipeline([("cat", "/dev/null"), ("cat", "/dev/null")], stdin=dw)
    pl1.shutdown()  # clean up unstarted process
    orphan_checks(nopen)

def test_int_arg(request):
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "simple1.txt")
    dr = DataReader()
    pl = Pipeline(("head", -2), stdin=inf, stdout=dr)
    pl.wait()
    assert dr.data == "one\ntwo\n"
    common_checks(nopen, pl, "^head -2 <.+/input/simple1\\.txt >\\[DataReader\\]", is_re=True)

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
    nopen = ts.get_num_open_files()
    outf = ts.get_test_output_file(request, ".out")
    outfGz = ts.get_test_output_file(request, ".out.gz")

    pl = Popen(("gzip", "-1"), "w", stdout=outfGz)
    cp_file_to_pl(request, "simple1.txt", pl)
    pl.close()
    common_checks(nopen, pl, "gzip -1 <.+ >.*output/test_pipettor.py::test_popen_write.out.gz", is_re=True)

    # macOS Ventura: user gunzip rather than zcat, as zcat did not support .gz
    Pipeline(("gunzip", "-c", outfGz), stdout=outf).wait()
    ts.diff_results_expected(request, ".out")

def test_popen_write_file(request):
    nopen = ts.get_num_open_files()
    outf = ts.get_test_output_file(request, ".out")
    outfGz = ts.get_test_output_file(request, ".out.gz")

    with open(outfGz, "w") as outfGzFh:
        pl = Popen(("gzip", "-1"), "w", stdout=outfGzFh)
        cp_file_to_pl(request, "simple1.txt", pl)
        pl.wait()

    # macOS Ventura: don't used zcat; would need to use gzcat, but this is compatbile with all
    Pipeline(("gunzip", "-c", outfGz), stdout=outf).wait()
    ts.diff_results_expected(request, ".out")
    common_checks(nopen, pl, "gzip -1 <.* >.*output/test_pipettor.py::test_popen_write_file.out.gz", is_re=True)

def test_popen_write_mult(request):
    nopen = ts.get_num_open_files()
    outf = ts.get_test_output_file(request, ".wc")

    # grr, BSD wc adds an extract space, so just convert to tabs
    pl = Popen((("gzip", "-1"),
                ("gzip", "-dc"),
                ("wc",),
                ("sed", "-e", "s/  */\t/g")), "w", stdout=outf)
    cp_file_to_pl(request, "simple1.txt", pl)
    pl.wait()

    ts.diff_results_expected(request, ".wc")
    common_checks(nopen, pl, "^gzip -1 <.+ | gzip -dc | wc | sed -e 's/  \\*/	/g' >.*output/test_pipettor::.test_popen_write_mult.wc$", is_re=True)

def test_popen_read(request):
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "simple1.txt")
    infGz = ts.get_test_output_file(request, ".txt.gz")
    Pipeline(("gzip", "-c", inf), stdout=infGz).wait()

    pl = Popen(("gzip", "-dc"), "r", stdin=infGz)
    cp_pl_to_file(request, pl, ".out")
    pl.wait()

    ts.diff_results_expected(request, ".out")
    common_checks(nopen, pl, "^gzip -dc <.*output/test_pipettor.py::test_popen_read.txt.gz >.+$", is_re=True)

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
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "simple1.txt")

    pl = Popen((("gzip", "-1c"),
                ("gzip", "-dc"),
                ("wc",),
                ("sed", "-e", "s/  */\t/g")), "r", stdin=inf)
    cp_pl_to_file(request, pl, ".wc")
    pl.wait()

    ts.diff_results_expected(request, ".wc")
    common_checks(nopen, pl, "^gzip -1c <.*tests/input/simple1.txt | gzip -dc | wc | sed -e 's/  \\*/	/g' >.+$", is_re=True)

def test_popen_exit_code():
    nopen = ts.get_num_open_files()
    pl = Popen(("false",))
    with pytest.raises(ProcessException, match="^process exited 1: false$"):
        pl.wait()
    for p in pl.procs:
        assert p.returncode == 1
    common_checks(nopen, pl, "^false >.+$", is_re=True)


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
    nopen = ts.get_num_open_files()
    pl = Popen([("yes",), ("true",)], "r")
    pl.wait()
    common_checks(nopen, pl, "^yes | true >.+ 2>\\[DataReader\\]$", is_re=True)

def test_popen_read_as_ascii_replace(request):
    # file contains unicode character outside of the ASCII range
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "nonAscii.txt")
    with Popen(["cat", inf], encoding='latin-1', errors="replace") as fh:
        lines = [l[:-1] for l in fh]
    assert ['Microtubules are assembled from dimers of a- and \xc3\x9f-tubulin.'] == lines
    orphan_checks(nopen)

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
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "simple1.txt")
    outf = ts.get_test_output_file(request, ".out")
    run([("cat",), ("cat",)], stdin=inf, stdout=File(outf, "w"))
    ts.diff_results_expected(request, ".out")
    orphan_checks(nopen)

def test_fn_path_obj():
    nopen = ts.get_num_open_files()
    true_path = Path("/usr/bin/true")
    run([true_path])
    orphan_checks(nopen)

def test_fn_simple_pipe_fail():
    nopen = ts.get_num_open_files()
    with pytest.raises(ProcessException, match="^process exited 1: false$"):
        run([("false",), ("true",)])
    orphan_checks(nopen)

def test_fn_stdout_read(request):
    # read from stdout into memory
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "simple1.txt")
    out = runout(("sort", "-r"), stdin=inf)
    assert out == "two\nthree\nsix\none\nfour\nfive\n"
    orphan_checks(nopen)

def test_fn_stdout_read_fail(request):
    # read from stdout into memory
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "simple1.txt")
    with pytest.raises(ProcessException) as cm:
        runout([("sort", "-r"), _get_prog_with_error_cmd(request), ("false",)], stdin=inf)
    check_prog_with_error(cm.value)
    orphan_checks(nopen)

def test_fn_write_file_lex(request):
    # test write to File object
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "simple1.txt")
    outf = ts.get_test_output_file(request, ".out")
    runlex(["cat -u", ["cat", "-u"], "cat -n"], stdin=inf, stdout=File(outf, "w"))
    ts.diff_results_expected(request, ".out")
    orphan_checks(nopen)

def test_fn_stdout_read_lex(request):
    # read from stdout into memory
    nopen = ts.get_num_open_files()
    inf = ts.get_test_input_file(request, "simple1.txt")
    out = runlexout("sort -r", stdin=inf)
    assert out == "two\nthree\nsix\none\nfour\nfive\n"
    orphan_checks(nopen)

def test_fn_env_passing():
    env = dict(os.environ)
    env['PIPETTOR'] = "YES"
    lines = runout(["env"], env=env).splitlines()
    assert "PIPETTOR=YES" in lines
