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


# PostProcess:
#
class PostProcess :


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
        dump = self.summary.dumps[disk]
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
    def run (self, app_name, config) :
        self.panic_count = 0
        self.config = config
        self.db = mbdb.DB(self.config.dbfile)
        self.journal = journal.Journal(config.journalfile, 'a',
                                       app_name=app_name,
                                       lockfile=config.journallock,
                                       skip_postproc=True)
        self.summary = self.journal.summary()
        self.journal.record('CLEAN-START', hrs=self.config.start_hrs)
        try:
            self.__run()
        except Exception as exc:
            self.panic("unhandled exception: %s: %s" %
                       (exc.__class__.__name__, exc))
        self.journal.record('CLEAN-END', hrs=self.config.start_hrs)
        self.journal.close()
        # [fixme] should not be here - send a report (from a fresh
        # journal)
        self.journal.reopen('r', skip_postproc=False)
        rep = report.Report(self.config, self.journal.summary(), width=70)
        sep = ''.center(70, '-') + '\n'
        info("REPORT:\n%s%s\n%s%s\n%s" % (sep, rep.title, sep, rep.body, sep))
        if sendmail(addrs=self.config.mailto, subject=rep.title, body=rep.body) != 0 :
            self.panic("sendmail failed!")
            return
        # time to panic now
        if self.panic_count > 0 :
            raise PostProcPanic()
        # and roll the journal
        self.journal.roll(dirname=self.config.journaldir, hrs=self.summary.hrs)


    # __run:
    #
    def __run (self) :
        # process dumps
        for disk, dump in self.summary.dumps.items() :
            try:
                self.__process_dump(disk, dump)
            except Exception as exc:
                self.panic("unhandled exception in dump '%s': %s: %s" %
                           (disk, exc.__class__.__name__, exc))


    # __process_dump:
    #
    def __process_dump (self, disk, dump) :
        # check if we already have a record
        rec = self.db.select_dump(runid=self.summary.runid, disk=disk)
        if rec is None :
            trace("%s: dump not registered, processing" % disk)
            self.__check_dump(disk, dump)
            # record the dump
            destbase = self.config.disks[disk].get_dumpname(runid=self.summary.runid,
                                                            hrs=self.summary.hrs,
                                                            level=0, # [TODO]
                                                            prevrun=dump.prevrun,
                                                            state=dump.state)
            destext = self.config.disks[disk].get_dumpext()
            try:
                rec = self.db.record_dump(runid=self.summary.runid, disk=disk, state=dump.state,
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
        if fd != 0 :
            os.close(fd)
        # now we can do it
        trace("%s: rename('%s', '%s')" % (disk, partfile, destfile))
        os.rename(partfile, destfile)
        trace("%s: move OK" % disk)