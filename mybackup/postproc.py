# postproc.py - cleanup & post-processing

__all__ = [
    'PostProcess',
]

import os, stat

from mybackup.base import *
from mybackup.log import *
from mybackup.tools import *
from mybackup import journal
from mybackup import mbdb
from mybackup import report


# PostProcPanic:
#
class PostProcPanic (Exception) :
    pass


_JRunInfo = attrdict('_JRunInfo')
_JDumpInfo = attrdict('_JDumpInfo')

class JRunInfo (_JRunInfo) :

    def __init__ (self) :
        _JRunInfo.__init__(self,
                           config='X',
                           start_hrs='X',
                           end_hrs='X',
                           runid=0,
                           dumps={},
                           errors=[],
                           warnings=[],
                           stranges=[],
                           notes=[],
                           messages=[])

class JDumpInfo (_JDumpInfo) :

    def __init__ (self, disk) :
        _JDumpInfo.__init__(self,
                            disk=disk,
                            state='selected',
                            fname='',
                            prevrun=-1,
                            raw_size=-1,
                            comp_size=-1,
                            nfiles=-1)
    

# JState:
#
class JState :


    # analysis:
    #
    @staticmethod
    def analysis (state) :
        runinfo = JRunInfo()
        for session in state :
            op = session[0]
            assert op.key == '_OPEN', op
            if op.tool == 'dump' :
                JState._analysis_dump(runinfo, session)
            else :
                assert 0, op
        return runinfo

    @staticmethod
    def _analysis_dump (runinfo, ss) :
        for ent in ss[1:] :
            if ent.key == 'START' :
                assert runinfo.start_hrs == 'X'
                runinfo.update(config=ent.config, start_hrs=ent.hrs, runid=ent.runid)
            elif ent.key == 'SELECT' :
                runinfo.dumps = dict((n, JDumpInfo(disk=n))
                                     for n in ent.disks.split(','))
            elif ent.key == 'SCHEDULE' :
                assert runinfo.dumps[ent.disk].state == 'selected'
                runinfo.dumps[ent.disk].update(state='scheduled', prevrun=ent.prevrun)
            elif ent.key == 'DUMP-START' :
                assert runinfo.dumps[ent.disk].state == 'scheduled'
                runinfo.dumps[ent.disk].update(state='partial', fname=ent.fname)
            elif ent.key == 'DUMP-FINISHED' :
                assert runinfo.dumps[ent.disk].state == 'partial'
                runinfo.dumps[ent.disk].update(state=DumpState.tostr(ent.state),
                                               raw_size=ent.raw_size,
                                               comp_size=ent.comp_size,
                                               nfiles=ent.nfiles)
            elif ent.key == 'USER-MESSAGE' :
                runinfo.messages.append((ent.level, ent.message))
            elif ent.key == 'END' :
                assert runinfo.end_hrs == 'X'
                runinfo.update(end_hrs=ent.hrs)
            else :
                assert 0, ent

# PostProcess:
#
class PostProcess :


    # analysis:
    #
    # [FIXME] should be elsewhere
    #
    def analysis (self, state) :
        ssdump = None
        ssclean = None
        # filter
        for ss in state :
            op = ss[0]
            assert op.key == '_OPEN', op
            if op.tool == 'dump' :
                assert ssdump is None
                ssdump = ss
            elif op.tool == 'clean' :
                ssclean = ss
            else :
                assert 0, ss

        trace("analysing dump:\n%s" % '\n'.join(repr(s) for s in ssdump))
        if ssclean is None :
            trace("no last clean found")
        else :
            trace("found last clean state:\n%s" % '\n'.join(repr(s) for s in ssclean))

        return JState.analysis([ssdump])


    @staticmethod
    def _exc_info (exc_info) :
        if exc_info is None :
            exc_info = sys.exc_info()
            if exc_info[0] is None :
                exc_info = None
        return exc_info
    
            
    # panic:
    #
    def panic (self, msg, exc_info=None) :
        exc_info = self._exc_info(exc_info)
        critical("PANIC: %s" % msg, exc_info=exc_info)
        #exc = '\n'.join(format_exception(exc_info))
        self.panic_count += 1


    # error:
    #
    def error (self, msg, exc_info=None) :
        exc_info = self._exc_info(exc_info)
        error(msg, exc_info=exc_info)


    # __fix_dump:
    #
    def __fix_dump (self, disk, state=None) :
        dump = self.runinfo.dumps[disk]
        kw = {'disk': disk}
        if state is None :
            kw['state'] = None
        else :
            kw['state'] = state
            dump.state = state
        # record
        trace("%s: fix: %s" % (dump.disk,
                               ', '.join("%s=%s" % (n, str(v))
                                         for n, v in kw.items())))
        self.journal.record('DUMP-FIX', **kw)

        
    # run:
    #
    def run (self, config) :
        self.panic_count = 0
        self.config = config
        self.db = mbdb.DB(self.config.dbfile)
        self.journal = journal.Journal(config.journalfile, 'a',
                                       tool_name='clean',
                                       lockfile=config.journallock,
                                       skip_postproc=True)
        self.runinfo = self.analysis(self.journal.get_state())
        try:
            self.__run()
        except Exception as exc:
            self.panic("unhandled exception: %s: %s" %
                       (exc.__class__.__name__, exc))
        self.journal.close()
        # [fixme] should not be here - send a report (from a fresh
        # journal)
        self.journal.reopen('r', skip_postproc=False)
        rep = report.Report(self.config, self.analysis(self.journal.get_state()), width=70)
        sep = ''.center(70, '-') + '\n'
        info("REPORT:\n%s%s\n%s%s\n%s" % (sep, rep.title, sep, rep.body, sep))
        if sendmail(addrs=self.config.mailto, subject=rep.title, body=rep.body) != 0 :
            self.panic("sendmail failed!")
            return
        # time to panic now
        if self.panic_count > 0 :
            raise PostProcPanic()
        # and roll the journal
        self.journal.roll(dirname=self.config.journaldir, hrs=self.runinfo.start_hrs)


    # __run:
    #
    def __run (self) :
        trace("post-processing: %s" % repr(self.runinfo))
        # process dumps
        for disk, dump in self.runinfo.dumps.items() :
            try:
                self.__process_dump(disk, dump)
            except Exception as exc:
                self.panic("unhandled exception in dump '%s': %s: %s" %
                           (disk, exc.__class__.__name__, exc))


    # __process_dump:
    #
    # IF NOT RECORDED THEN
    #   1. discard and report empty dumps -> stop
    #   2. check the partfile and fix the state
    #   3. record
    # ENDIF
    # 4. move
    #
    def __process_dump (self, disk, dump) :
        # check if we already have a record
        rec = self.db.select_dump(runid=self.runinfo.runid, disk=disk)
        if rec is None :
            trace("%s: dump not registered, processing" % disk)
            self.__check_dump(disk, dump)
            # record the dump
            destbase = self.config.disks[disk].get_dumpname(runid=self.runinfo.runid,
                                                            hrs=self.runinfo.start_hrs,
                                                            level=0, # [TODO]
                                                            prevrun=dump.prevrun,
                                                            state=dump.state)
            destext = self.config.disks[disk].get_dumpext()
            try:
                rec = self.db.record_dump(runid=self.runinfo.runid, disk=disk, state=dump.state,
                                          prevrun=dump.prevrun, fname=destbase+destext,
                                          raw_size=dump.raw_size, comp_size=dump.comp_size,
                                          nfiles=dump.nfiles)
            except:
                error("DUMP: %s" % repr(dump))
                raise
        # and do the move
        if DumpState.cmp(rec.state, 'empty') :
            trace("%s: dump is empty, nothing to move" % disk)
        else :
            self.__process_move(disk, dump, rec)


    # __check_dump:
    #
    def __check_dump (self, disk, dump) :
        cfgdisk = self.config.disks[disk]
        # skip those which didn't start
        if not dump.fname :
            trace("%s: dump did not start, check skipped" % disk)
            assert DumpState.cmp(dump.state, 'selected', 'scheduled'), dump.state
            self.__fix_dump(disk, state=DumpState.EMPTY)
            return
        # check if we have a partfile and it is not-empty
        partfile = os.path.join(self.config.partdir, dump.fname)
        trace("%s: checking partfile: '%s'" % (disk, partfile))
        try:
            st = os.stat(partfile)
        except FileNotFoundError:
            trace("%s: partfile not found" % disk)
            if not DumpState.cmp(dump.state, 'partial', 'failed') :
                self.error("%s: dump is '%s' but the dump does not exist! (%s)" %
                           (disk, DumpState.tostr(dump.state), partfile))
            self.__fix_dump(disk, state=DumpState.EMPTY, fname='')
            return
        # check the size
        assert stat.S_ISREG(st.st_mode) # parano
        if st.st_size == 0 :
            trace("%s: partfile is empty" % disk)
            if not DumpState.cmp(dump.state, 'partial', 'failed') :
                self.error("%s: dump is '%s' but the dump is empty! (%s)" %
                           (disk, DumpState.tostr(dump.state), partfile))
            self.__fix_dump(disk, state=DumpState.EMPTY, fname='')
            # note: if cleanup is interrupted after this we'll get
            # a 'file does not exist' error instead of 'file is
            # empty'
            os.unlink(partfile)
            return

        # and much more...
        self.__check_dump_sanity(disk, dump, partfile, st)


    # __check_dump_sanity:
    #
    def __check_dump_sanity (self, disk, dump, partfile, st) :
        warning("dump comp size: '%s' (%s)" % (dump.comp_size, dump.comp_size.__class__))
        # now we know that the dump exists
        assert DumpState.cmp(dump.state, 'ok', 'partial', 'failed'), \
          DumpState.tostr(dump.state)
        trace("%s: checking dump sanity" % disk)
        # comp_size
        if st.st_size != dump.comp_size :
            trace("%s: size mismatch: %d != %d" % (disk, st.st_size, dump.comp_size))
            if DumpState.cmp(dump.state, 'partial', 'failed') :
                state = dump.state
            else :
                self.error("%s: dump is '%s' but reported size doesn't match file size (%d != %d)"
                           % (disk, DumpState.tostr(dump.state), dump.comp_size, st.st_size))
                state = DumpState.BROKEN
            self.__fix_dump(disk, state=state)
        # what else now ?


    # __process_move:
    #
    # Move the dump from 'partdir' to its final destination. At this
    # point we know that the dump exists and is not empty, but the
    # move may have already been done.
    #
    def __process_move (self, disk, dump, rec) :
        assert dump.fname, dump
        partfile = os.path.join(self.config.partdir, dump.fname)
        destfile = os.path.join(self.config.dumpdir, rec.fname)
        trace("%s: moving dump '%s' -> '%s'" % (disk, partfile, destfile))
        # check if we have a partfile
        if not os.path.exists(partfile) :
            if not os.path.exists(destfile) :
                self.panic("%s: the dumpfile vanished! (%s -> %s)" %
                           (disk, partfile, destfile))
                return
            trace("%s: move already done" % disk)
            # maybe recheck destfile size ?
            return
        # just in case, make sure we don't clobber an existing file -
        # [FIXME] a race condition can leave an empty destfile behind
        # if we are interrupted here, so we just silently delete it if
        # it happens.
        try:
            fd = os.open(destfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            st = os.stat(destfile)
            if st.st_size == 0 :
                trace("%s: found empty destfile, wiping it" % disk)
                fd = 0
                os.unlink(destfile)
            else :
                # [fixme] could move it to some 'precious' dir to
                # avoid the panic
                self.panic("%s: partial and final dump both exist! (%s -> %s)" %
                           (disk, partfile, destfile))
                return
        else:
            os.close(fd)
        # now we can do it
        trace("%s: rename('%s', '%s')" % (disk, partfile, destfile))
        os.rename(partfile, destfile)
        trace("%s: move OK" % disk)
