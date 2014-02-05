#

from mybackup.log import *


# MBCleanApp:
#
class MBCleanApp :


    # main:
    #
    def main (self) :
        logger = log_setup('mbclean')
        trace("HELLO!")


# exec
if __name__ == '__main__' :
    app = MBCleanApp()
    app.main()
