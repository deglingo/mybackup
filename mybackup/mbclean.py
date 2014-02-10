#

import sys, getopt, logging, os, pprint

from mybackup.base import *
from mybackup.log import *
from mybackup.tools import *
from mybackup.config import Config
from mybackup.journal import Journal, JournalNotFoundError
from mybackup import postproc
from mybackup import report
from mybackup import mbapp


# USAGE:
#
USAGE = """\
USAGE: mbclean [OPTIONS] CONFIG

OPTIONS:

  -q, --quiet   be less verbose
  -v, --verbose be more verbose
  -h, --help    print this message and exit
"""


# MBCleanApp:
#
class MBCleanApp (mbapp.MBAppBase) :


    LOG_DOMAIN = 'mbclean'
            

    # app_run:
    #
    def app_run (self) :
        # parse the command line
        shortopts = 'qvh'
        longopts = ['quiet', 'verbose', 'help']
        opts, args = getopt.gnu_getopt(sys.argv[1:], shortopts, longopts)
        for o, a in opts :
            if o in ('-h', '--help') :
                sys.stdout.write(USAGE)
                sys.exit(0)
            elif o in ('-q', '--quiet') :
                self.quiet()
            elif o in ('-v', '--verbose') :
                self.verbose()
            else :
                assert 0, (o, a)
        # init the config
        assert len(args) == 1, args
        self.init_config(args[0])
        # open a logfile
        self.open_logfile()
        # acquire the config lock
        try:
            with FLock(self.config.cfglockfile, block=False) :
                self.__main_L()
        except FLockError as exc:
            error("could not acquire the config lock: '%s'" % self.config.cfglockfile)
            error("(this probably means that another mb* process is running)")
            sys.exit(1)


    # __main_L:
    #
    def __main_L (self) :
        trace("trying to open the journal: '%s'" % self.config.journalfile)
        try:
            self.journal = Journal(self.config.journalfile, 'r',
                                   tool_name='mbclean',
                                   lockfile=self.config.journallock)
        except JournalNotFoundError:
            info("journal not found - the config '%s' seems clean" %
                 self.config.cfgname)
            return
        info("journal found, cleaning up...")
        pp = postproc.PostProcess()
        try:
            pp.run(self.config)
        except:
            # the message i never want to see (probably means a bug)
            critical("ERROR(S) OCCURED DURING CLEANUP - MANUAL MAINTENANCE REQUIRED!")
        # format and send the report
        rep = report.Report(self.config)
        sep = ''.center(70, '-') + '\n'
        info("REPORT:\n%s%s\n%s%s\n%s" % (sep, rep.title, sep, rep.body, sep))
        if sendmail(addrs=self.config.mailto, subject=rep.title, body=rep.body) != 0 :
            raise Exception("sendmail failed!") # [fixme]
        # and roll the journal
        self.roll_journal()


# exec
if __name__ == '__main__' :
    MBCleanApp.main()
