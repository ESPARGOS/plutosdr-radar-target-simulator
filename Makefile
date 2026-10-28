.PHONY: prepare test fpga web tools capture-tool deploy
prepare:
	./scripts/bootstrap_hdl.sh
	python3 scripts/generate_rom.py
	python3 scripts/prepare_hdl.py
test: prepare
	./scripts/container.sh bash tests/run.sh
fpga: prepare
	./scripts/container.sh make -C vendor/adi-hdl/projects/pluto
web:
	python3 host/server.py --demo
tools:
	mkdir -p build
	./scripts/container.sh /opt/Xilinx/Vitis/2023.2/gnu/aarch32/lin/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc -O2 -Wall -Wextra -Werror -static -o build/rtsctl host/rtsctl.c
	./scripts/container.sh /opt/Xilinx/Vitis/2023.2/gnu/aarch32/lin/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc -O2 -Wall -Wextra -Werror -static -o build/radar.cgi host/radar_cgi.c -lm
	./scripts/container.sh /opt/Xilinx/Vitis/2023.2/gnu/aarch32/lin/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc -O2 -Wall -Wextra -Werror -static -o build/radio-pn host/radio_pn.c
capture-tool:
	mkdir -p build
	./scripts/container.sh /opt/Xilinx/Vitis/2023.2/gnu/aarch32/lin/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc -O2 -Wall -Wextra -Werror -static -o build/radio-capture host/radio_capture.c -lm
deploy: tools
	./scripts/deploy.sh

.PHONY: firmware test-local test-analysis
firmware:
	python3 scripts/package_firmware.py

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
