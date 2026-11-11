.PHONY: prepare test fpga web tools deploy
prepare:
	./scripts/bootstrap_hdl.sh
	python3 scripts/generate_rom.py
	python3 scripts/generate_fractional_rom.py
	python3 scripts/generate_standard_filters.py
	python3 scripts/prepare_hdl.py
	python3 scripts/prepare_standard_hdl.py
test: prepare
	./scripts/container.sh bash tests/run.sh
fpga: prepare
	./scripts/container.sh python3 scripts/build_fpga.py
web:
	python3 host/server.py --demo
tools:
	python3 scripts/build_tools.py
deploy: tools
	./scripts/deploy.sh

.PHONY: firmware test-local
firmware: tools
	python3 scripts/package_firmware.py $(FIRMWARE_ARGS)

test-local: prepare
	bash tests/run.sh

.PHONY: test-web
test-web:
	python3 scripts/check_web.py

.PHONY: test-native test-ui-model test-provenance
test-native:
	mkdir -p build/tests
	$(CC) -std=c11 -O2 -Wall -Wextra -Werror -Ihost tests/test_latency.c -lm -o build/tests/latency
	build/tests/latency
	$(CC) -std=c11 -O2 -Wall -Wextra -Werror -Ihost tests/test_radio_timing.c -o build/tests/radio-timing
	build/tests/radio-timing
	$(CC) -std=c11 -O2 -Wall -Wextra -Werror -Ihost -Itests host/radar_control.c tests/fake_device.c tests/test_native_control.c -lm -o build/tests/native-control
	build/tests/native-control
	python3 tests/test_native_api.py
	python3 tests/test_startup.py
	python3 tests/test_scene_contract.py
test-ui-model:
	node --test tests/*.test.js
test-provenance:
	python3 tests/test_build_provenance.py

.PHONY: release test-release
test-release:
	mkdir -p build/tests
	python3 tests/test_release.py

RELEASE_BASE ?= build/firmware/original.itb
release: tools
	python3 scripts/package_firmware.py --base "$(RELEASE_BASE)" --output build/release-firmware
	python3 scripts/package_release.py
