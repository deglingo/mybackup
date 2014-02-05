# postproc.py - cleanup & post-processing

__all__ = [
    'post_process',
]

import os, stat

from mybackup.base import *
from mybackup.log import *
from mybackup.tools import *
from mybackup import mbdb


# [FIXME]
_error = error


# post_process:
#
def post_process (config, summary) :
    summary = copy.deepcopy(summary)
    trace("post-processing dumps (date=%s, errors=%d, warnings=%d, stranges=%d)" %
          (hrs2date(summary.hrs), summary.nerrors, summary.nwarnings, summary.nstranges))
    # open the database
    db = mbdb.DB(config.dbfile)
    # process the dumps
    for dump in summary.dumps.values() :
        _post_process_dump(config, db, summary, dump)
    # debug
    trace("post-processing done!")
    db.dump()


# _post_process_dump:
#
def _post_process_dump (config, db, summary, dump) :
    cfgdisk = config.disks[dump.disk]
    trace("%s: %s" % (cfgdisk.name, dump))
    # discard those which did not even start
    if DumpState.cmp(dump.state, 'selected', 'scheduled') :
        trace("dump not started (%s), discarded" % (dump.state))
        return
    # [fixme]
    assert DumpState.cmp(dump.state, 'ok', 'partial', 'failed', 'broken'), \
      DumpState.tostr(dump.state)
    # partial file
    partfile = os.path.join(config.partdir, dump.fname)
    # check if we already have a record
    rec = db.select_dump(runid=summary.runid, disk=dump.disk)
    if rec is None :
        # no record, so we didn't name and move the file yet - check
        # if it's worth doing it (ie don't keep an empty file)
        dump_stat = os.lstat(partfile)
        assert stat.S_ISREG(dump_stat.st_mode) # parano
        if dump_stat.st_size == 0 :
            _error("dump '%s' is empty - file discarded" % partfile)
            dump.state = DumpState.EMPTY
            rec = None
        else :
            destbase = cfgdisk.get_dumpname(runid=summary.runid, level=9,
                                            prevrun=dump.prevrun, hrs=summary.hrs)
            if not DumpState.cmp(dump.state, 'ok') :
                destbase += '.' + DumpState.tostr(dump.state).upper()
            # [fixme] ?
            # destfile = create_file_nc(dirname=config.dumpdir, base=destbase,
            #                           ext=cfgdisk.get_dumpext())
            destfile = os.path.join(config.dumpdir, destbase+cfgdisk.get_dumpext())
            # record
            rec = db.record_dump(disk=dump.disk, runid=summary.runid, state=dump.state,
                                 prevrun=dump.prevrun, fname=destfile, raw_size=dump.raw_size,
                                 comp_size=dump.comp_size, nfiles=dump.nfiles)
    # now we have a record, try to move the dump
    if os.path.exists(partfile) :
        if os.path.exists(destfile) :
            _error("partfile and dump are both present !? (%s -> %s)" %
                   (partfile, destfile))
        else :
            trace("moving dump: '%s' -> '%s'" % (partfile, destfile))
            os.rename(partfile, destfile)
    else :
        if os.path.exists(destfile) :
            trace("dump already moved: '%s'" % destfile)
        else :
            _error("partfile and dump are both absent !? (%s -> %s)" %
                   (partfile, destfile))
