# mbdb.py - the dumps database

__all__ = [
    'DB',
]

import sqlite3, collections

from mybackup.base import *
from mybackup.log import *
from mybackup.tools import *


# DB:
#
class DB :


    __TABLES = (
        ('runs', (('runid', 'integer primary key autoincrement'),
                  ('hrs',   'text unique'))),

        ('dumps', (('dumpid', 'integer primary key autoincrement'),
                   ('disk', 'text'),
                   ('runid', 'references runs(runid)'),
                   ('prevrun', 'references runs(runid)'),
                   ('state', 'dumpstate'),
                   ('fname', 'text'),
                   ('raw_size', 'int'),
                   ('comp_size', 'int'),
                   ('nfiles',    'int'),
                   ('hashtype', 'text'),
                   ('hashsum', 'text'))),
    )


    __tpcache = {}

    # [fixme] how to adapt DumpState
    sqlite3.register_converter('dumpstate', DumpState.convert)


    # __row:
    #
    def __row (self, cur, row) :
        key = tuple(d[0] for d in cur.description)
        tp = self.__tpcache.get(key)
        if tp is None :
            tp = self.__tpcache[key] = collections.namedtuple('Row%d' % len(self.__tpcache), key)
        return tp(*row)

    
    # __init__:
    #
    def __init__ (self, fname) :
        self.fname = fname
        if os.path.exists(fname) :
            # [FIXME] should only be done by writer tools
            backup_file(fname)
        else :
            open(fname, 'wt').close()
        self.con = sqlite3.connect(self.fname, detect_types=sqlite3.PARSE_DECLTYPES)
        self.con.row_factory = self.__row
        self._init()


    # _init:
    #
    def _init (self) :
        sel = self._execute('select * from sqlite_master')
        if sel :
            trace("[todo] update db")
            return
        for tname, tcols in DB.__TABLES :
            sql = 'create table %s (' % tname
            sql += ', '.join('%s %s' % c for c in tcols)
            sql += ')'
            self._execute(sql)
        self._commit()


    # __repr__:
    #
    def __repr__ (self) :
        return '<%s "%s">' % (self.__class__.__name__, self.fname)


    # dump:
    #
    def dump (self, depth=0) :
        lines = []
        lines.append(("  %s  " % self).center(120, '=') + '\n')
        for tname, tcols in DB.__TABLES :
            sel = self._execute('select * from %s order by %s' %
                                (tname, tcols[0][0]))
            lines.append("%s: %d records\n" % (tname.upper(), len(sel)))
            if sel :
                lines.append(("  [ %s ]" % ', '.join(sel[0]._fields)) + '\n')
            for row in sel :
                lines.append(("  ( %s )" % ', '.join(str(c) for c in row)) + '\n')
        lines.append(''.center(120, '=') + '\n')
        trace("DBDUMP:\n%s" % ''.join(lines), depth=depth+1)


    # _execute:
    #
    def _execute (self, sql, args=(), commit=True) :
        cur = self.con.cursor()
        #trace("SQL: %s" % sql)
        cur.execute(sql, args)
        r = list(cur.fetchall())
        if commit :
            self._commit()
        cur.close()
        return r


    # _commit:
    #
    def _commit (self) :
        self.con.commit()


    # record_run:
    #
    def record_run (self, hrs) :
        self._execute('insert into runs (hrs) values (?)',
                      (hrs,), commit=True)
        sel = self._execute('select * from runs where hrs == ?', (hrs,))
        assert len(sel) == 1
        trace("run recorded: %d (%s)" % (sel[0].runid, sel[0].hrs))
        return sel[0].runid


    # select_run:
    #
    def select_run (self, runid) :
        sel = self._execute('select * from runs where runid == ?', (runid,))
        return sel[0] if sel else None


    # record_dump:
    #
    def record_dump (self, disk, runid, prevrun, state, fname, raw_size, comp_size, nfiles, hashtype, hashsum) :
        # [FIXME] must be carefull with 'state' because i didn't find
        # a way to automatically 'adapt' it
        state = DumpState.tostr(state)
        self._execute('insert into dumps ' +
                      '(disk, runid, prevrun, state, fname, raw_size, comp_size, nfiles, hashtype, hashsum) ' +
                      'values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      (disk, runid, prevrun, state, fname, raw_size, comp_size, nfiles, hashtype, hashsum))
        rec = self.select_dump(runid=runid, disk=disk)
        assert rec is not None, (disk, runid)
        trace("dump recorded: %s" % repr(disk))
        return rec


    # select_dump:
    #
    def select_dump (self, runid, disk) :
        sel = self._execute('select * from dumps where runid == ? and disk == ?',
                            (runid, disk))
        assert len(sel) <= 1
        return sel[0] if sel else None


    # select_last_dump:
    #
    def select_last_dump (self, disk) :
        sel = self._execute('select * from dumps where disk == ?' +
                            ' order by runid desc', (disk,))
        return sel[0] if sel else None


    # get_current_cycle:
    #
    def get_current_cycle (self, disk) :
        sel = self._execute('select * from dumps ' +
                            'where disk == ? ' +
                            'order by runid desc',
                            (disk,))
        trace("get_cycle(%s) -> %s" % (disk, sel))
        return sel
