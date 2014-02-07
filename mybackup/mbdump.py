#

import sys, os, traceback, getopt, json, weakref, collections, time
import re, sqlite3, shutil, copy, pprint, subprocess, threading
import logging, codecs, types
from subprocess import PIPE as CMDPIPE
from functools import partial

from mybackup.base import *
from mybackup.log import *
from mybackup.tools import *
from mybackup import asciitable
from mybackup.config import Config
from mybackup.journal import Journal
from mybackup import mbdb
from mybackup import postproc
from mybackup import mbapp

# debug
# import mybackup as _debug_mybackup
# sys.stderr.write("MYBACKUP: %s\n" % _debug_mybackup)


# USAGE:
#
USAGE = """\
USAGE: mbdump [OPTIONS] CONFIG [DISK...]

OPTIONS:

  -f, --force    force dump(s)
  -q, --quiet    be less verbose
  -v, --verbose  be more verbose
  -h, --help     print this message and exit
"""


# DumpSched:
#
DumpSched = attrdict('DumpSched', ())


# DumpEstimate:
#
DumpEstimate = collections.namedtuple(
    'DumpEstimate',
    ('prev', 'raw', 'comp', 'est'))


# Index:
#
class Index :


    # __init__:
    #
    def __init__ (self, fname) :
        self.fname = fname
        self.f = open(self.fname, 'wt')
        self.count = 0


    # __call__:
    #
    def __call__ (self, line) :
        #trace("INDEX: %s" % line.rstrip())
        self.f.write(line)
        self.count += 1


    # close:
    #
    def close (self) :
        self.f.close()


# MBDumpApp:
#
class MBDumpApp (mbapp.MBAppBase) :


    LOG_DOMAIN = 'mbdump'


    # app_run:
    #
    def app_run (self) :
        # parse the command line
        # [fixme] -c should be elsewhere
        _cfgparam = ''
        shortopts = 'c:fhqv'
        longopts = ['force', 'help']
        opts, args = getopt.gnu_getopt(sys.argv[1:], shortopts, longopts)
        for o, a in opts :
            if o in ('-h', '--help') :
                sys.stdout.write(USAGE)
                sys.exit(0)
            elif o in ('-f', '--force') :
                self.config.force = True
            elif o in ('-q', '--quiet') :
                self.quiet()
            elif o in ('-v', '--verbose') :
                self.verbose()
            elif o in ('-c',) :
                _cfgparam = a
            else :
                assert 0, (o, a)
        # [REMOVEME]
        if _cfgparam :
            if len(args) >= 1 :
                self.init_config(args[0])
            o = self.config
            for n in _cfgparam.split('.') :
                o = getattr(o, n)
            sys.stdout.write('%s\n' % str(o))
            sys.exit(0)
        # init the config
        assert len(args) >= 1, args
        self.init_config(args.pop(0))
        # open the logfile and say something
        self.open_logfile()
        # acquire the config lock
        try:
            with FLock(self.config.cfglockfile, block=False) :
                self.__main_L(args)
        except FLockError as exc:
            error(exc, exc_info=sys.exc_info())
            error("(this probably means that another mbdump process is running)")
            sys.exit(1)


    # __main_L:
    #
    def __main_L (self, args) :
        # open the DB
        self.db = mbdb.DB(self.config.dbfile)
        # [fixme] select disks
        sched = self.__select_disks(args)
        if not sched :
            info("no disk selected, bye")
            return
        info("selected %d disks: %s" %
             (len(sched), ', '.join(d.disk for d in sched)))
        # go
        self.__process(sched)
        # cleanup
        pp = postproc.PostProcess()
        pp.run(self.config)
        # ok
        info("all done, bye!")


    # __select_disks:
    #
    def __select_disks (self, args) :
        trace("selecting disks (%d args: %s force=%s)" %
              (len(args), args, self.config.force))
        if args :
            disklist = [self.config.disks[d] for d in args]
        else :
            disklist = list(self.config.disks.values())
        sched = []
        for disk in disklist :
            if self.config.force :
                trace("%s: force flag set, selected" % disk.name)
            else :
                dump = self.db.select_last_dump(disk)
                if dump is None :
                    trace("%s: no last dump found, selected" % disk)
                else :
                    hrs = self.db.select_run(dump.runid).hrs
                    # [TODO]
                    if hrs[:8] > self.config.start_hrs[:8] :
                        error("%s: last dump is in the future!!" % disk.name)
                        error("%s: I prefer to skip this dump, use -f to force selection" % disk.name)
                        continue
                    elif hrs[:8] < self.config.start_hrs[:8] :
                        trace("%s: last dump older than 1 day, selected" % disk.name)
                    else :
                        trace("%s: up to date, skipped" % disk.name)
                        continue
            sched.append(DumpSched(disk=disk.name, cfgdisk=disk))
        return sched


    # __process:
    #
    def __process (self, sched) :
        # record the run now so we get a runid
        self.runid = self.db.record_run(self.config.start_hrs)
        # open the journal
        try:
            self.journal = Journal(self.config.journalfile, 'w',
                                   lockfile=self.config.journallock)
        except FileExistsError:
            error("could not open journal file: '%s'" % self.config.journalfile)
            error("this probably means that an earlier run failed, please run \`mbclean %s'" %
                  (self.config.cfgname))
            sys.exit(1)
        warning("OUCH")
        self.journal.record('START', config=self.config.cfgname, runid=self.runid, hrs=self.config.start_hrs)
        self.journal.record('SELECT', disks=','.join(s.disk for s in sched))
        # schedule the dumps
        self.trigger_hooks('schedule', [d.cfgdisk for d in sched])
        for dsched in sched :
            self.__schedule_dump(dsched)
        # run
        for dsched in sched :
            self.__process_dump(dsched)
        # close the journal
        self.journal.record('END', hrs=stamp2hrs(int(time.time())))
        self.journal.close()


    # trigger_hooks:
    #
    def trigger_hooks (self, trigger, disklist) :
        trace("triggering all '%s' hooks" % trigger)
        for disk in disklist :
            disk.run_hooks(trigger, self.journal)


    # __schedule_dump:
    #
    def __schedule_dump (self, dsched) :
        trace("%s: scheduling dump" % dsched.disk)
        cycle = self.db.get_current_cycle(dsched.disk)
        trace("%s: %d dumps in current cycle" % (dsched.disk, len(cycle)))
        for d in cycle : trace(" - %s" % repr(d))
        if cycle :
            estims = [self.__estim_dump(dsched, None)]
            estims.extend(self.__estim_dump(dsched, d)
                          for d in cycle)
            select = None
            for e in estims :
                if select is None or select.est > e.est :
                    select = e
            if select is None :
                warning("%s: could not get estimates, full dump forced" % dsched.disk)
                dsched.update(prevrun=0)
            else :
                info("%s: got best estimate: %s" % (dsched.disk, select))
                dsched.update(prevrun=select.prev)
        else :
            info("%s: no cycle found, full dump forced" % dsched.disk)
            dsched.update(prevrun=0)
            
        self.journal.record('SCHEDULE', disk=dsched.disk, prevrun=dsched.prevrun)


    # __estim_dump:
    #
    def __estim_dump (self, dsched, prev) :
        trace("[TODO] estim(%s, %s)" % (dsched.disk, prev))
        return None
        # prevrun = (0 if prev is None else prev.runid)
        # return DumpEstimate(prev=prevrun, raw=100, comp=100, est=prevrun*10)
            

    # __process_dump:
    #
    def __process_dump (self, dsched) :
        cdisk = dsched.cfgdisk
        info("%s: starting dump (%s)" % (cdisk.name, cdisk.path))
        # make a filename
        destbase = 'mbdump.%s.%s.%s' % (self.config.cfgname, dsched.disk,
                                        self.config.start_hrs)
        destext = dsched.cfgdisk.get_dumpext() + '.part'
        destfull = os.path.join(self.config.partdir, destbase+destext)
        # instantiate a dumper
        dumper = dsched.cfgdisk.get_dumper()
        trace("dumper: %s" % dumper)
        # looks like we're ready
        self.journal.record('DUMP-START', disk=dsched.disk, fname=destbase+destext)
        procs = []
        pipes = []
        # open dest file and index
        trace("temp dump file: '%s'" % destfull)
        fdest = open(destfull, 'wb')
        index = Index('/dev/null')
        # [fixme] filters
        trace("%s: starting the filters" % cdisk.name)
        filters = [cmdexec(['gzip'], stdin=CMDPIPE, stdout=CMDPIPE)]
        # start the dumper
        trace("%s: starting the dumper" % cdisk.name)
        proc_dump = dumper.start(dsched.cfgdisk.path)
        trace("%s: dumper running with pid %d" % (cdisk.name, proc_dump.pid))
        procs.append(proc_dump)
        p_dump = PipeThread('dumper', proc_dump.stdout, ())
        pipes.append(p_dump)
        # start the index
        trace("%s: starting the index" % cdisk.name)
        proc_index = dumper.start_index()
        trace("%s: index running with pid %d" % (cdisk.name, proc_index.pid))
        procs.append(proc_index)
        p_dump.plug_output(proc_index.stdin)
        p_index = PipeThread('index', proc_index.stdout, (), line_handler=index)
        pipes.append(p_index)
        # plug the filters
        data_plug = p_dump
        for n, filt in enumerate(filters) :
            data_plug.plug_output(filt.stdin)
            data_plug = PipeThread('filter[%d]' % n, filt.stdout, ())
            procs.append(filt)
            pipes.append(data_plug)
        # plug output
        data_plug.plug_output(fdest)
        # start all pipes
        for p in pipes :
            p.start()
        # then wait...
        trace("%s: waiting for %d pipes..." % (cdisk.name, len(pipes)))
        for p in pipes :
            p.join()
            #trace("%s: OK (%d bytes)" % (p.name, p.data_size))
        # wait processes
        trace("%s: waiting for %d processes..." % (cdisk.name, len(procs)))
        state = DumpState.OK
        for p in procs :
            #trace("wait proc: %s" % p)
            r = p.wait()
            trace("%s: process %d terminated: %d" % (cdisk.name, p.pid, r))
            if r != 0 :
                error("%s: process %d failed: %d" % (cdisk.name, p.pid, r))
                state = DumpState.FAILED
        # close files
        # [fixme] datasync
        trace("%s: closing dump file" % cdisk.name)
        fdest.close()
        index.close()
        # collect datas about the dump
        raw_size = p_dump.data_size
        comp_size = data_plug.data_size
        nfiles = index.count
        # all done
        self.journal.record('DUMP-FINISHED',
                            disk=dsched.disk, state=DumpState.tostr(state),
                            raw_size=raw_size, comp_size=comp_size,
                            nfiles=nfiles)
        info("%s: dump finished: %s (%s/%s, %d files)" %
             (cdisk.name, state, human_size(raw_size),
              human_size(comp_size), nfiles))


# exec
if __name__ == '__main__' :
    MBDumpApp.main()
