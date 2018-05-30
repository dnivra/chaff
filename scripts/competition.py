#!/usr/bin/python

import argparse
import atexit
import datetime
import json
import lockfile
import os
import pipes
import re
import shlex
import shutil
import signal
import string
import subprocess32
import sys
import time

from math import sqrt
from os.path import basename, dirname, join, abspath, exists

from lava import LavaDatabase, Bug, Build, DuaBytes, Run, \
    run_cmd, run_cmd_notimeout, mutfile, inject_bugs, LavaPaths, \
    validate_bugs, run_modified_program, unfuzzed_input_for_bug, \
    fuzzed_input_for_bug, get_trigger_line, AttackPoint, Bug


RETRY_COUNT = 0

# Build both scripts - in a seperate fn for testing
def run_builds(scripts):
    for script in scripts:
        with open(script) as f:
            print(f.read())
        (rv, outp) = run_cmd_notimeout(["/bin/bash", script])
        if rv != 0:
            raise RuntimeError("Could not build {}".format(script))
        print("Built with command {}".format(script))

# collect num bugs AND num non-bugs
# with some hairy constraints
# we need no two bugs or non-bugs to have same file/line attack point
# that allows us to easily evaluate systems which say there is a bug at file/line.
# further, we require that no two bugs or non-bugs have same file/line dua
# because otherwise the db might give us all the same dua
def competition_bugs_and_non_bugs(num, db):
    bugs_and_non_bugs = []
    fileline = set()
    def get_bugs_non_bugs(fake, limit):
        items = db.uninjected_random(fake)
        for item in items:
            dfl = (item.trigger_lval.loc_filename, item.trigger_lval.loc_begin_line)
            afl = (item.atp.loc_filename, item.atp.loc_begin_line)
            # Skip this one if we've already used an ATP or DUA with the same line. Or if this is a function call atp. or it it's an easybug or an info leak
            if (dfl in fileline) or (afl in fileline) or (item.atp.typ == AttackPoint.FUNCTION_CALL) or (item.type == Bug.RET_BUFFER) or (item.type == Bug.PRINTF_LEAK):
                continue
            if fake:
                print "non-bug", 
            else:
                print "bug    ",
            print ' dua_fl={} atp_fl={}'.format(str(dfl), str(afl))
            fileline.add(dfl)
            fileline.add(afl)
            bugs_and_non_bugs.append(item)
            if (len(bugs_and_non_bugs) == limit):
                break
    get_bugs_non_bugs(False, num)
    get_bugs_non_bugs(True, 2*num)
    return [b.id for b in bugs_and_non_bugs]

def main():
    parser = argparse.ArgumentParser(description='Inject and test LAVA bugs.')
    parser.add_argument('project', type=argparse.FileType('r'),
            help = 'JSON project file')
    parser.add_argument('-m', '--many', action="store", default=-1,
            help = 'Inject this many bugs and this many non-bugs (chosen randomly)')
    parser.add_argument('-n', '--minYield', action="store", default=-1,
            help = 'Require at least this many real bugs')
    parser.add_argument('-l', '--buglist', action="store", default=False,
            help = 'Inject this list of bugs')
    parser.add_argument('-e', '--exitCode', action="store", default=0, type=int,
            help = ('Expected exit code when program exits without crashing. Default 0'))

    args = parser.parse_args()
    project = json.load(args.project)
    project_file = args.project.name

    # Set various paths
    lp = LavaPaths(project)

    # Make the bugs top_dir start with competition
    lp.bugs_top_dir = join(lp.top_dir, "competition")
    compdir = join(lp.top_dir, "competition")
    bugdir = join(compdir, "bugs")

    db = LavaDatabase(project)

    if not os.path.exists(bugdir):
        os.makedirs(bugdir)

    bugs_parent = bugdir
    lp.set_bugs_parent(bugdir)

    try:
        shutil.rmtree(bugdir)
    except:
        pass

    args.knobTrigger = -1
    args.checkStacktrace = False
    args.arg_dataflow = False
    failcount = 0

    while True:
        if args.buglist:
            bug_list = eval(args.buglist)
        elif args.many:
            bug_list = competition_bugs_and_non_bugs(int(args.many), db)

        # add either bugs to the source code and check that we can still compile
        try:
            (build, input_files) = inject_bugs(bug_list, db, lp, project_file, \
                                              project, args, False, competition=True)
        except RuntimeError:
            if failcount < RETRY_COUNT:
                print("Failed to inject bugs, trying again:\n{}".format(bug_list))
                failcount += 1
                continue
            raise



        # bug is valid if seg fault (or bus error)
        # AND if stack trace indicates bug manifests at trigger line we inserted
        real_bug_list = validate_bugs(bug_list, db, lp, project, input_files, build, \
                                          args, False, competition=True)

        if len(real_bug_list) < int(args.minYield):
            print "\n\nXXX Yield too low -- %d bugs minimum is required for competition" % int(args.minYield)
            print "Trying again.\n"
        else:
            print "\n\n Yield acceptable"
            break

    # re-build just with the real bugs. Inject in competition mode
    (build,input_files) = inject_bugs(real_bug_list, db, lp, project_file, \
                                          project, args, False, competition=True)


    corpus_dir = join(compdir, "corpora")
    subprocess32.check_call(["mkdir", "-p", corpus_dir])

    # original bugs src dir
    # directory for this corpus
    corpname = "lava-corpus-" + ((datetime.datetime.now()).strftime("%Y-%m-%d-%H-%M-%S"))
    corpdir = join(corpus_dir,corpname)
    subprocess32.check_call(["mkdir", corpdir])

    lava_bd = join(lp.bugs_parent, lp.source_root)

    # Copy lava's builddir into our local build-dir
    bd = join(corpdir, "build-dir")
    shutil.copytree(lava_bd, bd)

    # Corpus directory structure: lava-corpus-[date]/
    #   inputs/
    #   src/
    #   build.sh
    #   log_build.sh
    #   lava-install-internal
    #   lava-install-prod

    # subdir with trigger inputs
    inputsdir = join(corpdir, "inputs")
    subprocess32.check_call(["mkdir", inputsdir])
    # subdir with src -- note we can't create it or copytree will fail!
    srcdir = join(corpdir, "src")
    # copy src
    shutil.copytree(bd, srcdir)

    predictions = {}
    for bug in  db.session.query(Bug).filter(Bug.id.in_(real_bug_list)).all():
        prediction = "{}:{}".format(basename(bug.atp.loc_filename),
                                    get_trigger_line(lp, bug))
#        print "Bug %d: prediction = [%s]" % (bug.id, prediction)
        if not get_trigger_line(lp, bug):
            print("Warning - unknown trigger, skipping")
            continue

        assert not (prediction in predictions)
        fuzzed_input = fuzzed_input_for_bug(lp, bug)
        (dc, fi) = os.path.split(fuzzed_input)
        shutil.copy(fuzzed_input, inputsdir)
        predictions[prediction] = fi

    print "Answer key:"
    ans = open(join(corpdir, "ans"), "w")
    for prediction in predictions:
        print "ANSWER  [%s] [%s]" % (prediction, predictions[prediction])
        ans.write("%s %s\n" % (prediction, predictions[prediction]))
    ans.close()

    # clean up srcdir before tar
    os.chdir(srcdir)
    try:
        # Unconfigure
        subprocess32.check_call(["make", "distclean"])
    except:
        pass
    shutil.rmtree(join(srcdir, ".git"))
    shutil.rmtree(join(srcdir, "lava-install"))
    os.remove(join(srcdir, "compile_commands.json"))
    os.remove(join(srcdir, "btrace.log"))

    # build source tar
    #tarball = join(srcdir + ".tgz")
    #os.chdir(corpdir)
    #cmd = "/bin/tar czvf " + tarball + " src"
    #subprocess32.check_call(cmd.split())
    #print "created corpus tarball " + tarball + "\n";

    #lp.bugs_install = join(corpdir,"lava-install") # Change to be in our corpdir
    # Save the commands we use into files so we can rerun later
    build_sh = join(corpdir, "build.sh")
    with open(build_sh, "w") as build:
        build.write("""#!/bin/bash
        pushd `pwd`
        cd {bugs_build}
        {make_clean}
        {configure}
        {make}
        {install}
        cp -r lava-install {outdir}
        popd
        """.format(
            bugs_build=bd,
            make_clean = "make clean" if project["makeclean"] else "",
            configure=project['configure'],
            make=project['make'],
            install=project['install'],
            outdir=join(corpdir, "lava-install")))

    log_build_sh = join(corpdir, "log_build.sh")
    with open(log_build_sh, "w") as build:
        build.write("""#!/bin/bash
        pushd `pwd`
        cd {bugs_build}

        # Build internal version
        {make_clean}
        {configure}
        {make} CFLAGS+="-DLAVA_LOGGING"
        rm -rf "{internal_builddir}"
        {install}
        cp -r lava-install {internal_builddir}

        # Build public version
        {make_clean}
        {configure}
        {make}
        rm -rf "{public_builddir}"
        {install}
        cp -r lava-install {public_builddir}

        popd
        """.format(
            bugs_build=bd,
            make_clean = "make clean" if project["makeclean"] else "",
            configure=project['configure'],
            make = project['make'],
            internal_builddir = join(corpdir, "lava-install-internal"),
            public_builddir = join(corpdir, "lava-install"),
            install = project['install'],
            ))

    trigger_all_crashes = join(corpdir, "trigger_crashes.sh")
    with open(trigger_all_crashes, "w") as build:
        build.write("""#!/bin/bash
        pushd `pwd`
        cd {corpdir}

        for fname in {inputdir}/*-fuzzed-*; do
            LD_LIBRARY_PATH={librarydir} {command}
        done

        popd
        """.format(command = project['command'].format(**{"install_dir": join(corpdir, "lava-install-internal"), "input_file": "$fname"}), # This syntax is weird but only thing that works?
            corpdir = corpdir,
            librarydir = join(corpdir, "lava-install-internal", "lib"),
            inputdir = join(corpdir, "inputs")
            ))

    # Build a version to ship in src
    run_builds([build_sh, log_build_sh])
    print("Success! Competition build in {}".format(corpdir))


if __name__ == "__main__":
    main()
