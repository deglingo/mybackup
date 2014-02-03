#

# note: docs must be before systest!
SUBDIRS = bin mybackup docs systest

.PHONY: listdirs

listdirs:
	@fmt="%-15s | %-50s | %-50s\n"; \
	printf "$$fmt" "prefix" '@prefix@' "$(prefix)"; \
	printf "$$fmt" "exec_prefix" '@exec_prefix@' "$(exec_prefix)"; \
	printf "$$fmt" "pythondir" '@pythondir@' "$(pythondir)"; \
	printf "$$fmt" "pkgpythondir" '@pkgpythondir@' "$(pkgpythondir)"; \
	true

	cd systest && $(MAKE) $(AM_MAKEFLAGS) check-build

.PHONY: check-build

check-build:
	cd systest && $(MAKE) $(AM_MAKEFLAGS) check-build
