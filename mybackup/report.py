# report.py - dump report formatter

__all__ = [
    'Report',
]

import copy

from mybackup.sysconf import SYSCONF
from mybackup.base import *
from mybackup.log import *
from mybackup.asciitable import Table, Frame, Justify


# Report:
#
class Report :


    ndumps = property(lambda s: len(s.runinfo.dumps))
    nerrors = property(lambda s: len(s.errors))
    nwarnings = property(lambda s: len(s.warnings))
    nstranges = property(lambda s: len(s.stranges))
    nnotes =  property(lambda s: len(s.notes))
    
    
    # __init__:
    #
    def __init__ (self, config, runinfo, running=False, width=70) :
        self.width = width
        # NOTE: only use config for infos which are not in runinfo!
        self.config = config
        self.runinfo = runinfo
        self.running = running
        self.__report_prep()
        self.__report_title()
        self.__report_body()


    def maybe_error (self, msg) :
        if self.running :
            self.notes.append(msg)
        else :
            self.pre_errors.append(msg)


    # __report_prep:
    #
    def __report_prep (self) :
        self.pre_errors = []
        self.errors = copy.deepcopy(self.runinfo.errors)
        self.warnings = copy.deepcopy(self.runinfo.warnings)
        self.stranges = copy.deepcopy(self.runinfo.stranges)
        self.notes = copy.deepcopy(self.runinfo.notes)
        self.messages = copy.deepcopy(self.runinfo.messages)
        # [fixme]
        for nlvl, nmsg in self.messages :
            self.pre_errors.append("NOTE: %s" % nmsg)
        # check if we started at all
        if self.runinfo.start_hrs == 'X' :
            self.maybe_error("this run did not start!?")
        if self.runinfo.end_hrs == 'X' :
            self.maybe_error("this run did not finish properly!")
        # check if all dumps are ok
        if self.runinfo.dumps :
            failed = [d for d in self.runinfo.dumps.values()
                      if not DumpState.cmp(d.state, 'ok')]
            if failed :
                self.maybe_error("%s did not finished properly!"
                                 % plural(len(failed), 'dump'))
        else :
            self.maybe_error("no dump found")
        # [fixme] check if cleaning has been done
        # if not self.summary.postprocs :
        #     self.maybe_error("no post-processing done")
        # else :
        #     # [fixme] check and report previous ones too ?
        #     pp = self.summary.postprocs[-1]
        #     if pp.endhrs == 'X' :
        #         self.maybe_error("the last post-processing did not finish!")
        # format the 'error mark'
        self.errmark = ''
        self.errmark += ('!' if (self.errors or self.pre_errors) else '-')
        self.errmark += ('!' if self.warnings else '-')
        self.errmark += ('!' if self.stranges else '-')


    # __report_title:
    #
    def __report_title (self) :
        fmt = "%(package)s '%(config)s' REPORT [%(errmark)s] %(date)s"
        args = {'errmark': self.errmark,
                'package': SYSCONF['PACKAGE'].upper(),
                'config': self.runinfo.config,
                'date': hrs2date(self.runinfo.start_hrs)}
        self.title = fmt % args


    # __report_body:
    #
    def __report_body (self) :
        self.body = ''.join((self.__report_header(), '\n\n',
                             self.__report_dumps(), '\n\n',
                             self.__report_footer(), '\n\n',
                             '-- END OF REPORT --', '\n'))


    # __report_header:
    #
    def __report_header (self) :
        lines = []
        # head line
        headline = "%s/%04d - %s - %s" % (self.runinfo.config,
                                          self.runinfo.runid,
                                          hrs2date(self.runinfo.start_hrs),
                                          plural(self.ndumps, 'DUMP'))
        lines.append(headline.center(self.width))
        lines.append('')
        # summary
        for e in self.pre_errors :
            lines.append(' - ERROR: %s' % e)
        errs = []
        if self.errors : errs.append('%s' % plural(self.nerrors, 'error'))
        if self.warnings : errs.append('%s' % plural(self.nwarnings, 'warning'))
        if self.stranges : errs.append('%s' % plural(self.nstranges, 'strange line'))
        if errs :
            lines.append(" - WARNING: %s reported in this dump"
                          % ', '.join(errs))
        # join all
        return '\n'.join(lines)


    # __report_footer:
    #
    def __report_footer (self) :
        lines = []
        if self.nerrors :
            lines.append("")
            lines.append(" - %s :" % plural(self.nerrors, 'error'))
            lines.append("")
            lines.extend(("   %s" % m) for m in self.errors)
        if self.nwarnings :
            lines.append("")
            lines.append(" - %s :" % plural(self.nwarnings, 'warning'))
            lines.append("")
            lines.extend(("   %s" % m) for m in self.warnings)
        if self.nstranges :
            lines.append("")
            lines.append(" - %s :" % plural(self.nstranges, 'strange line'))
            lines.append("")
            lines.extend(("   %s: %s" % (s, m)) for s, m in self.stranges)
        return '\n'.join(lines)


    # __report_dumps:
    #
    def __report_dumps (self) :
        table = Table()
        # parse column specs (title, format, args)
        cspecs = self.__parse_columns(self.config.report_columns)
        # big title
        big_title = "%s/%04d - %s" % (self.runinfo.config,
                                      self.runinfo.runid,
                                      hrs2date(self.runinfo.start_hrs))
        table.add(big_title, 0, 0, 1, len(cspecs), frame=Frame.BOX,
                  justify=Justify.CENTER)
        # columns titles
        for c, col in enumerate(cspecs) :
            table.add(col[0], 1, c, frame=Frame.BOX, justify=Justify.CENTER)
        # columns content
        t_state, t_raw, t_comp, t_files = DumpState.OK, 0, 0, 0
        ndumps = len(self.runinfo.dumps)
        last = ndumps - 1
        for r, dump in enumerate(self.runinfo.dumps.values()) :
            if not DumpState.cmp(dump.state, 'ok') :
                t_state = DumpState.FAILED
            t_raw += dump.raw_size
            t_comp += dump.comp_size
            t_files += dump.nfiles
            for c, col in enumerate(cspecs) :
                attrs = { # [fixme] should be automated
                    'disk': dump.disk,
                    'upstate': DumpState.tostr(dump.state, up=True),
                    'raw_hsize': human_size(dump.raw_size),
                    'comp_hsize': human_size(dump.comp_size),
                    'comp_ratio': ((dump.comp_size * 100.0 / dump.raw_size)
                                   if dump.raw_size > 0 else 0.0),
                    'nfiles': dump.nfiles,
                }
                text = col[1] % attrs
                frame = (Frame.LR | (Frame.BOTTOM if r == last else 0))
                table.add(text, r+2, c, frame=frame, **col[2])
        # totals line
        if ndumps > 1 :
            total_row = ndumps + 2
            t_attrs = {'disk': '',
                       'upstate': DumpState.tostr(t_state).upper(),
                       'raw_hsize': human_size(t_raw),
                       'comp_hsize': human_size(t_comp),
                       'comp_ratio': ((t_comp * 100.0 / t_raw) if t_raw > 0 else 0.0),
                       'nfiles': t_files}
            for c, col in enumerate(cspecs) :
                text = col[1] % t_attrs
                table.add(text, total_row, c, frame=Frame.BOX, **col[2])
        # dump
        lines = table.getlines()
        tab = ' ' * ((self.width - len(lines[0])) // 2)
        return '\n'.join((tab+l) for l in lines)


    # __parse_columns:
    #
    def __parse_columns (self, colspecs) :
        cols = []
        for cspec in colspecs :
            #trace("CSPEC: '%s'" % cspec)
            title = ''
            kwargs = {}
            while cspec and cspec[0] == "\\" :
                end = cspec.find("\\", 1)
                if end < 0 :
                    cspec = cspec[1:]
                    break
                attr = cspec[1:end]
                cspec = cspec[end:]
                eq = attr.find('=')
                if eq >= 0 :
                    atname, atval = attr[:eq], attr[eq+1:]
                else :
                    atname, atval = attr, ''
                if atname == 'title' :
                    title = atval
                elif atname == 'left' :
                    kwargs['justify'] = Justify.LEFT
                elif atname == 'right' :
                    kwargs['justify'] = Justify.RIGHT
                elif atname == 'center' :
                    kwargs['justify'] = Justify.CENTER
                else :
                    assert 0, (atname, atval)
            cols.append((title, cspec, kwargs))
            #trace(" -> %s" % repr(cols[-1]))
        return cols
