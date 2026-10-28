.PHONY: prepare test fpga web tools capture-tool deploy
prepare:
	./scripts/bootstrap_hdl.sh
	python3 scripts/generate_rom.py
	python3 scripts/prepare_hdl.py
test: prepare
	./scripts/container.sh bash tests/run.sh
fpga: prepare
	./scripts/container.sh python3 scripts/build_fpga.py
web:
	python3 host/server.py --demo
tools:
	python3 scripts/build_tools.py
capture-tool:
	mkdir -p build
	./scripts/container.sh /opt/Xilinx/Vitis/2023.2/gnu/aarch32/lin/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc -O2 -Wall -Wextra -Werror -static -o build/radio-capture host/radio_capture.c -lm
deploy: tools
	./scripts/deploy.sh

.PHONY: firmware test-local test-analysis
firmware: tools
	python3 scripts/package_firmware.py $(FIRMWARE_ARGS)

test-local: prepare
	bash tests/run.sh

test-analysis:
	python3 tests/test_analysis.py
	python3 tests/test_signal_quality.py
	python3 tests/test_raw_spurs.py
	python3 tests/test_adc_images.py
	python3 tests/test_native_tx.py

.PHONY: test-web
test-web:
	python3 scripts/check_web.py

.PHONY: test-native test-ui-model test-provenance
test-native:
	mkdir -p build/tests
	$(CC) -std=c11 -O2 -Wall -Wextra -Werror -Ihost -Itests host/radar_control.c tests/fake_device.c tests/test_native_control.c -lm -o build/tests/native-control
	build/tests/native-control
	python3 tests/test_native_api.py
	python3 tests/test_startup.py
	python3 tests/test_scene_contract.py
test-ui-model:
	node --test tests/*.test.js
test-provenance:
	python3 tests/test_build_provenance.py
