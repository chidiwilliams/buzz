# Change also in pyproject.toml and buzz/__version__.py
version := 1.4.4

mac_app_path := ./dist/Buzz.app
mac_zip_path := ./dist/Buzz-${version}-mac.zip
mac_dmg_path := ./dist/Buzz-${version}-mac.dmg

bundle_windows: dist/Buzz
	iscc installer.iss

bundle_mac: dist/Buzz.app codesign_all_mac zip_mac notarize_zip staple_app_mac dmg_mac

bundle_mac_unsigned: dist/Buzz.app zip_mac dmg_mac_unsigned

clean:
ifeq ($(OS), Windows_NT)
	-rmdir /s /q buzz\whisper_cpp
	-rmdir /s /q whisper.cpp\build
	-rmdir /s /q dist
	-Remove-Item -Recurse -Force buzz\whisper_cpp
	-Remove-Item -Recurse -Force whisper.cpp\build
	-Remove-Item -Recurse -Force dist\*
	-rm -rf buzz/whisper_cpp
	-rm -rf whisper.cpp/build
	-rm -rf dist/*
	-rm -rf buzz/__pycache__ buzz/**/__pycache__ buzz/**/**/__pycache__ buzz/**/**/**/__pycache__
	-for /d /r buzz %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
else
	rm -rf buzz/whisper_cpp || true
	rm -rf whisper.cpp/build || true
	rm -rf dist/* || true
	find buzz -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
endif

COVERAGE_THRESHOLD := 70

test: buzz/whisper_cpp
	pytest -s -vv --cov=buzz --cov-report=xml --cov-report=html --benchmark-skip --cov-fail-under=${COVERAGE_THRESHOLD} --cov-config=.coveragerc

benchmarks: buzz/whisper_cpp
	pytest -s -vv --benchmark-only --benchmark-json benchmarks.json

dist/Buzz dist/Buzz.app: buzz/whisper_cpp
	pyinstaller --noconfirm Buzz.spec

version:
	echo "VERSION = \"${version}\"" > buzz/__version__.py

buzz/whisper_cpp: translation_mo
ifeq ($(OS), Windows_NT)
	# Build Whisper with Vulkan support.
	# The _DISABLE_CONSTEXPR_MUTEX_CONSTRUCTOR is needed to prevent mutex lock issues on Windows
	# https://github.com/actions/runner-images/issues/10004#issuecomment-2156109231
	# -DCMAKE_[C|CXX]_COMPILER_WORKS=TRUE is used to prevent issue in building test program that fails on CI
	# GGML_NATIVE=OFF ensures we don't use -march=native (which would target the build machine's CPU)
	cmake -S whisper.cpp -B whisper.cpp/build/ -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DCMAKE_INSTALL_RPATH='$$ORIGIN' -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON -DCMAKE_C_FLAGS="-D_DISABLE_CONSTEXPR_MUTEX_CONSTRUCTOR"  -DCMAKE_CXX_FLAGS="-D_DISABLE_CONSTEXPR_MUTEX_CONSTRUCTOR" -DCMAKE_C_COMPILER_WORKS=TRUE -DCMAKE_CXX_COMPILER_WORKS=TRUE -DGGML_VULKAN=1 -DGGML_NATIVE=OFF
	cmake --build whisper.cpp/build -j --config Release --verbose

	-mkdir buzz/whisper_cpp
	cp whisper.cpp/build/bin/Release/whisper-cli.exe buzz/whisper_cpp/
	cp whisper.cpp/build/bin/Release/whisper-server.exe buzz/whisper_cpp/
	cp dll_backup/SDL2.dll buzz/whisper_cpp
endif

ifeq ($(shell uname -s), Linux)
	# Build Whisper with Vulkan support
	# GGML_NATIVE=OFF ensures we don't use -march=native (which would target the build machine's CPU)
	# This enables portable SSE4.2/AVX/AVX2 optimizations that work on most x86_64 CPUs
	rm -rf whisper.cpp/build || true
	-mkdir -p buzz/whisper_cpp
	cmake -S whisper.cpp -B whisper.cpp/build/ -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DCMAKE_INSTALL_RPATH='$$ORIGIN' -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON -DGGML_VULKAN=1 -DGGML_NATIVE=OFF
	cmake --build whisper.cpp/build -j --config Release --verbose
	cp whisper.cpp/build/bin/whisper-cli buzz/whisper_cpp/ || true
	cp whisper.cpp/build/bin/whisper-server buzz/whisper_cpp/ || true
	cp -P whisper.cpp/build/src/libwhisper.so* buzz/whisper_cpp/ || true
	cp -P whisper.cpp/build/ggml/src/libggml.so* buzz/whisper_cpp/ || true
	cp -P whisper.cpp/build/ggml/src/libggml-base.so* buzz/whisper_cpp/ || true
	cp -P whisper.cpp/build/ggml/src/libggml-cpu.so* buzz/whisper_cpp/ || true
	cp -P whisper.cpp/build/ggml/src/ggml-vulkan/libggml-vulkan.so* buzz/whisper_cpp/ || true
endif

# Build on Macs
ifeq ($(shell uname -s), Darwin)
	-rm -rf whisper.cpp/build || true
	-mkdir -p buzz/whisper_cpp

ifeq ($(shell uname -m), arm64)
	cmake -S whisper.cpp -B whisper.cpp/build/ -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DWHISPER_COREML=1
else
    # Intel
	cmake -S whisper.cpp -B whisper.cpp/build/ -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DGGML_VULKAN=0 -DGGML_METAL=0
endif

	cmake --build whisper.cpp/build -j --config Release --verbose
	cp whisper.cpp/build/bin/whisper-cli buzz/whisper_cpp/ || true
	cp whisper.cpp/build/bin/whisper-server buzz/whisper_cpp/ || true
	cp whisper.cpp/build/src/libwhisper.dylib buzz/whisper_cpp/ || true
	cp whisper.cpp/build/ggml/src/libggml* buzz/whisper_cpp/ || true
endif

# Prints all the Mac developer identities used for code signing
print_identities_mac:
	security find-identity -p basic -v

dmg_mac:
	ditto -x -k "${mac_zip_path}" dist/dmg
	create-dmg \
		--volname "Buzz" \
		--volicon "./assets/buzz.icns" \
		--window-pos 200 120 \
		--window-size 600 300 \
		--icon-size 100 \
		--icon "Buzz.app" 175 120 \
		--hide-extension "Buzz.app" \
		--app-drop-link 425 120 \
		--codesign "$$BUZZ_CODESIGN_IDENTITY" \
		--notarize "$$BUZZ_KEYCHAIN_NOTARY_PROFILE" \
		--filesystem APFS \
		"${mac_dmg_path}" \
		"dist/dmg/"

dmg_mac_unsigned:
	ditto -x -k "${mac_zip_path}" dist/dmg
	create-dmg \
		--volname "Buzz" \
		--volicon "./assets/buzz.icns" \
		--window-pos 200 120 \
		--window-size 600 300 \
		--icon-size 100 \
		--icon "Buzz.app" 175 120 \
		--hide-extension "Buzz.app" \
		--app-drop-link 425 120 \
		"${mac_dmg_path}" \
		"dist/dmg/"

staple_app_mac:
	xcrun stapler staple ${mac_app_path}

notarize_zip:
	xcrun notarytool submit ${mac_zip_path} --keychain-profile "$$BUZZ_KEYCHAIN_NOTARY_PROFILE" --wait

zip_mac:
	ditto -c -k --keepParent "${mac_app_path}" "${mac_zip_path}"

codesign_all_mac: dist/Buzz.app
	for i in $$(find dist/Buzz.app/Contents/Resources/torch/bin -name "*" -type f); \
	do \
		codesign --force --options=runtime --sign "$$BUZZ_CODESIGN_IDENTITY" --timestamp "$$i"; \
	done
	for i in $$(find dist/Buzz.app/Contents/Resources -name "*.dylib" -o -name "*.so" -type f); \
	do \
		codesign --force --options=runtime --sign "$$BUZZ_CODESIGN_IDENTITY" --timestamp "$$i"; \
	done
	for i in $$(find dist/Buzz.app/Contents/MacOS -name "*.dylib" -o -name "*.so" -o -name "Qt*" -o -name "Python" -type f); \
	do \
		codesign --force --options=runtime --sign "$$BUZZ_CODESIGN_IDENTITY" --timestamp "$$i"; \
	done
	codesign --force --options=runtime --sign "$$BUZZ_CODESIGN_IDENTITY" --timestamp dist/Buzz.app/Contents/MacOS/Buzz
	codesign --force --options=runtime --sign "$$BUZZ_CODESIGN_IDENTITY" --entitlements ./entitlements.plist --timestamp dist/Buzz.app
	codesign --verify --deep --strict --verbose=2 dist/Buzz.app

# HELPERS

# Get the build logs for a notary upload
notarize_log:
	xcrun notarytool log ${id} --keychain-profile "$$BUZZ_KEYCHAIN_NOTARY_PROFILE"

# Make GGML model from whisper. Example: make ggml model_path=/Users/chidiwilliams/.cache/whisper/medium.pt
ggml:
	python3 ./whisper.cpp/models/convert-pt-to-ggml.py ${model_path} .venv/lib/python3.12/site-packages/whisper dist

upload_brew:
	brew bump-cask-pr --version ${version} --verbose buzz

UPGRADE_VERSION_BRANCH := upgrade-to-${version}
gh_upgrade_pr:
	git checkout main && git pull
	git checkout -B ${UPGRADE_VERSION_BRANCH}

	make version version=${version}

	git commit -am "Upgrade to ${version}"
	git push --set-upstream origin ${UPGRADE_VERSION_BRANCH}

	gh pr create --fill
	gh pr merge ${UPGRADE_VERSION_BRANCH} --auto --squash

# Internationalization

translation_po_all:
	$(MAKE) translation_po locale=en_US
	$(MAKE) translation_po locale=ca_ES
	$(MAKE) translation_po locale=es_ES
	$(MAKE) translation_po locale=pl_PL
	$(MAKE) translation_po locale=zh_CN
	$(MAKE) translation_po locale=zh_TW
	$(MAKE) translation_po locale=it_IT
	$(MAKE) translation_po locale=lv_LV
	$(MAKE) translation_po locale=uk_UA
	$(MAKE) translation_po locale=ja_JP
	$(MAKE) translation_po locale=da_DK
	$(MAKE) translation_po locale=de_DE
	$(MAKE) translation_po locale=nl
	$(MAKE) translation_po locale=pt_BR

TMP_POT_FILE_PATH := $(shell mktemp)
PO_FILE_PATH := buzz/locale/${locale}/LC_MESSAGES/buzz.po
translation_po:
	mkdir -p buzz/locale/${locale}/LC_MESSAGES
	xgettext --from-code=UTF-8 --add-location=file -o "${TMP_POT_FILE_PATH}" -l python $(shell find buzz -name '*.py')
	sed -i.bak 's/CHARSET/UTF-8/' ${TMP_POT_FILE_PATH}
	if [ ! -f ${PO_FILE_PATH} ]; then \
		msginit --no-translator --input=${TMP_POT_FILE_PATH} --output-file=${PO_FILE_PATH}; \
	fi
	rm ${TMP_POT_FILE_PATH}.bak
	msgmerge -U ${PO_FILE_PATH} ${TMP_POT_FILE_PATH}

# On windows we can have two ways to compile locales, one for CI the other for local builds
# Will try both and ignore errors if they fail
translation_mo:
ifeq ($(OS), Windows_NT)
	-forfiles /p buzz\locale /c "cmd /c python ..\..\msgfmt.py -o @path\LC_MESSAGES\buzz.mo @path\LC_MESSAGES\buzz.po"
	-for dir in buzz/locale/*/ ; do \
		python msgfmt.py -o $$dir/LC_MESSAGES/buzz.mo $$dir/LC_MESSAGES/buzz.po; \
	done
else
	for dir in buzz/locale/*/ ; do \
		python3 msgfmt.py -o $$dir/LC_MESSAGES/buzz.mo $$dir/LC_MESSAGES/buzz.po; \
	done
endif

lint:
	ruff check . --fix
	ruff format .
