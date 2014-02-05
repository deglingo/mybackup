#

# note: tools must be first and docs must be before systest!
SUBDIRS = tools bin mybackup docs systest

.PHONY: listvars

_VARLIST = \
	PACKAGE \
	PYTHON \
	PYTHON_VERSION \
	prefix \
	exec_prefix \
	sysconfdir \
	pkgsysconfdir \
	bindir \
	libdir \
	localstatedir \
	pkglocalstatedir \
	pythondir \
	pkgpythondir

listvars: _listvars
	sh ./_listvars >&2

_listvars: _listvars.in config.status
	./config.status --file=$@

_listvars.in: Makefile
	@(	for v in $(_VARLIST); do \
			echo "$$v=\"@$$v@\""; \
		done; \
		for v in $(_VARLIST); do \
			echo "printf \"%-20s | %-30s | %-20s\\n\" \"$$v\" '@$$v@' \""'$$'"{$$v}\""; \
		done; \
	) >$@.tmp
	@mv -f $@.tmp $@
	@#echo "** $@ **"; cat $@

.PHONY: check-build

check-build:
	cd systest && $(MAKE) $(AM_MAKEFLAGS) check-build
