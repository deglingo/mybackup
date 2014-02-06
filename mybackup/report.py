# report.py - dump report formatter

__all__ = [
    'Report',
]

import copy

from mybackup.sysconf import SYSCONF
from mybackup.base import *


# Report:
#
class Report :


    # __init__:
    #
    def __init__ (self, summary, running=False) :
        self.summary = summary
        self.running = running
        self.__report_prep()
        self.__report_title()
        self.__report_body()


    def maybe_error (self, msg) :
        if self.running :
            self.notes.insert(0, msg)
        else :
            self.errors.insert(0, msg)


    # __report_prep:
    #
    def __report_prep (self) :
        self.errors = copy.deepcopy(self.summary.errors)
        self.warnings = copy.deepcopy(self.summary.warnings)
        self.stranges = copy.deepcopy(self.summary.stranges)
        self.notes = copy.deepcopy(self.summary.notes)
        # check if we started at all
        if self.summary.hrs == 'X' :
            self.maybe_error("no starting date (dump not started?)")
        if self.summary.endhrs == 'X' :
            self.maybe_error("no ending date (dump still running or interrupted)")
        # check if all dumps are ok
        if self.summary.dumps :
            failed = [d for d in self.summary.dumps.values()
                      if not DumpState.cmp(d.state, 'ok')]
            if failed :
                self.maybe_error("%d dumps did not finished properly" % len(failed))
        else :
            self.maybe_error("no dump found")
        # format the 'error mark'
        self.errmark = ''
        self.errmark += ('!' if self.errors else '-')
        self.errmark += ('!' if self.warnings else '-')
        self.errmark += ('!' if self.stranges else '-')


    # __report_title:
    #
    def __report_title (self) :
        fmt = "%(errmark)s %(package)s '%(config)s' REPORT [%(date)s]"
        args = {'errmark': self.errmark,
                'package': SYSCONF['PACKAGE'],
                'config': self.summary.config,
                'date': hrs2date(self.summary.hrs)}
        self.title = fmt % args


    # __report_body:
    #
    def __report_body (self) :
        self.body = "[TODO] report body\n" + repr(self.summary)

    # #############

    # # __report:
    # #
    # def __report (self, info, width=70) :
    #     trace("formatting report")
    #     title = self.__report_title(info)

    #     header = ['HEADER']

    #     # dumps table
    #     dumps = [l.center(70) for l in self.__report_dumps(info)]

    #     body = header + dumps
    #     return title, body


    # # __report_dumps:
    # #
    # def __report_dumps (self, info) :
    #     cols = self.__parse_columns(self.config.report_columns)                
    #     table = asciitable.Table(len(info.dumps)+3, len(cols),
    #                              vpad=0, hpad=1)
    #     table.set_vpad(0, 1)
    #     table.set_vpad(1, 1)
    #     table.set_vpad(2, 1)
    #     table.set_vpad(len(info.dumps)+2, 1)
    #     table.set_vpad(len(info.dumps)+3, 1)
    #     # table title
    #     table_title = 'DUMP RUN %04d' % info.runid
    #     table.add(table_title, 0, 0, 1, len(cols),
    #               frame=asciitable.Frame.FULL, justify='center',)
    #     # column titles
    #     for col, (title, cfmt, kwargs) in enumerate(cols) :
    #         table.add(title, 1, col, margins=(0, 1, 0, 1),
    #                   frame=asciitable.Frame.FULL, justify='center')
    #     # dump lines
    #     nfiles_total, raw_total, comp_total = 0, 0, 0
    #     for row, (disk, dump) in enumerate(info.dumps.items()) :
    #         nfiles_total += dump.nfiles
    #         raw_total += dump.raw_size
    #         comp_total += dump.comp_size
    #         for col, (t, cfmt, kwargs) in enumerate(cols) :
    #             table.add(cfmt % dump, row+2, col,
    #                       frame=asciitable.Frame.LR, **kwargs)
    #     # total lines (if more than one dump)
    #     if len(info.dumps) > 1 :
    #         attr_total = {'disk': '',
    #                       'state': '',
    #                       'nfiles': nfiles_total,
    #                       'raw_size': raw_total,
    #                       'raw_hsize': human_size(raw_total),
    #                       'comp_size': comp_total,
    #                       'comp_hsize': human_size(comp_total),
    #                       'comp_ratio': ((comp_total * 100.0 / raw_total)
    #                                      if raw_total > 0 else 0.0)}
    #         for col, (t, f, k) in enumerate(cols) :
    #             text = (f % attr_total).strip()
    #             table.add(text, row+3, col,
    #                       frame=asciitable.Frame.FULL, **k)
    #     # ok
    #     return table.getlines(debug=0)


    # # __parse_columns:
    # #
    # def __parse_columns (self, colspecs) :
    #     cols = []
    #     for cspec in colspecs :
    #         #trace("CSPEC: '%s'" % cspec)
    #         title = ''
    #         kwargs = {}
    #         while cspec and cspec[0] == "\\" :
    #             end = cspec.find("\\", 1)
    #             if end < 0 :
    #                 cspec = cspec[1:]
    #                 break
    #             attr = cspec[1:end]
    #             cspec = cspec[end:]
    #             eq = attr.find('=')
    #             if eq >= 0 :
    #                 atname, atval = attr[:eq], attr[eq+1:]
    #             else :
    #                 atname, atval = attr, ''
    #             if atname == 'title' :
    #                 title = atval
    #             elif atname == 'left' :
    #                 kwargs['justify'] = left
    #             elif atname == 'right' :
    #                 kwargs['justify'] = 'right'
    #             elif atname == 'center' :
    #                 kwargs['justify'] = 'center'
    #             else :
    #                 assert 0, (atname, atval)
    #         cols.append((title, cspec, kwargs))
    #         #trace(" -> %s" % repr(cols[-1]))
    #     return cols
        

    # # __report_title:
    # #
    # def __report_title (self, info) :
    #     mark = '--'
    #     title = "%(package)s '%(config)s' REPORT %(status_mark)s %(date)s" \
    #       % {'package': self.config.system.PACKAGE.upper(),
    #          'config': info.config,
    #          'status_mark': mark,
    #          'date': hrs2date(info.hrs)}
    #     return title
