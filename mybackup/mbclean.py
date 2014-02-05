#

from mybackup.log import *
from mybackup.config import Config


# MBCleanApp:
#
class MBCleanApp :


    # main:
    #
    def main (self) :
        self.__log_setup()
        self.config = Config()
        # parse the command line


    # __log_setup:
    #
    def __log_setup (self) :
        logger = log_setup('mbclean')
        self.cfilt = LogLevelFilter()
        hdlr = LogConsoleHandler()
        hdlr.addFilter(self.cfilt)
        logger.addHandler(hdlr)
        trace("HELLO!")


# exec
if __name__ == '__main__' :
    app = MBCleanApp()
    app.main()
