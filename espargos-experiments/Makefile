# Optional measurement tools. Nothing here is part of the firmware build.
export MPLCONFIGDIR := $(CURDIR)/build/matplotlib
CC_ARM = /opt/Xilinx/Vitis/2023.2/gnu/aarch32/lin/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc
.PHONY: test capture-tool motion-baseline-tool
test:
	mkdir -p build/tests
	@set -e; for test in tests/test_*.py; do python3 "$$test"; done
capture-tool:
	mkdir -p build
	../scripts/container.sh $(CC_ARM) -O2 -Wall -Wextra -Werror -static -o espargos-experiments/build/radio-capture espargos-experiments/host/radio_capture.c -lm
motion-baseline-tool:
	mkdir -p build
	../scripts/container.sh $(CC_ARM) -O2 -Wall -Wextra -Werror -static -Ihost -o espargos-experiments/build/radar-integer-baseline espargos-experiments/tests/integer_motion_baseline.c host/radar_control.c host/radar_linux.c -lm
