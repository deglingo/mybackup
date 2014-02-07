#

MB_SYSTEST_FILES = \
	mybackup-systest \
	mybackup-systest.conf \
	mybackup-systest-common \
	mybackup-systest-tools

.PHONY: check-build

check-build: check-build.stamp-h

check-build.stamp-h: $(MB_SYSTEST_FILES) @MB_SYSTEST_MODULES@
	echo >$@
