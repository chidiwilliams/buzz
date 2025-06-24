version := $$(poetry version -s)
version_escaped := $$(echo ${version} | sed -e 's/\./\\./g')

mac_app_path := ./dist/Buzz.app
mac_zip_path := ./dist/Buzz-${version}-mac.zip
mac_dmg_path := ./dist/Buzz-${version}-mac.dmg

bundle_windows: dist/Buzz
	iscc //DAppVersion=${version} installer.iss

bundle_mac: dist/Buzz.app codesign_all_mac zip_mac notarize_zip staple_app_mac dmg_mac

bundle_mac_unsigned: dist/Buzz.app zip_mac dmg_mac_unsigned

clean:
ifeq ($(OS), Windows_NT)
	-rmdir /s /q buzz\whisper_cpp 2> nul
	-rmdir /s /q buzz\whisper-server.exe 2> nul
	-rmdir /s /q whisper.cpp\build 2> nul
	-rmdir /s /q dist 2> nul
	-Remove-Item -Recurse -Force buzz\whisper_cpp
	-Remove-Item -Recurse -Force buzz\whisper-server.exe
	-Remove-Item -Recurse -Force whisper.cpp\build
	-Remove-Item -Recurse -Force dist\*
	-rm -rf buzz/whisper_cpp
	-rm -fr buzz/whisper-server.exe
	-rm -rf whisper.cpp/build
	-rm -rf dist/*
else
	rm -rf buzz/whisper_cpp || true
	rm -fr buzz/whisper_cpp_vulkan || true
	rm -rf whisper.cpp/build || true
	rm -rf dist/* || true
endif

COVERAGE_THRESHOLD := 75

test: buzz/whisper_cpp.py translation_mo
	pytest -s -vv --cov=buzz --cov-report=xml --cov-report=html --benchmark-skip --cov-fail-under=${COVERAGE_THRESHOLD} --cov-config=.coveragerc

benchmarks: buzz/whisper_cpp.py translation_mo
	pytest -s -vv --benchmark-only --benchmark-json benchmarks.json

dist/Buzz dist/Buzz.app: buzz/whisper_cpp.py translation_mo
	pyinstaller --noconfirm Buzz.spec

version:
	poetry version ${version}
	echo "VERSION = \"${version}\"" > buzz/__version__.py

buzz/whisper_cpp:
ifeq ($(OS), Windows_NT)
	# Build Whisper for CPU
	# The _DISABLE_CONSTEXPR_MUTEX_CONSTRUCTOR is needed to prevent mutex lock issues on Windows
	# https://github.com/actions/runner-images/issues/10004#issuecomment-2156109231
	cmake -S whisper.cpp -B whisper.cpp/build/ -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DCMAKE_INSTALL_RPATH='$$ORIGIN' -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON -D_DISABLE_CONSTEXPR_MUTEX_CONSTRUCTOR=ON
	cmake --build whisper.cpp/build -j --config Release --verbose

	-mkdir buzz/whisper_cpp
	cp dll_backup/SDL2.dll buzz/whisper_cpp
	cp whisper.cpp/build/bin/Release/whisper.dll buzz/whisper_cpp
	cp whisper.cpp/build/bin/Release/ggml.dll buzz/whisper_cpp
	cp whisper.cpp/build/bin/Release/ggml-base.dll buzz/whisper_cpp
	cp whisper.cpp/build/bin/Release/ggml-cpu.dll buzz/whisper_cpp

	# Build Whisper with Vulkan support. On Windows whisper-server.exe wil lbe used as dll approach is unreliable,
	# it often does not see the GPU
	cmake -S whisper.cpp -B whisper.cpp/build/ -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DCMAKE_INSTALL_RPATH='$$ORIGIN' -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON -D_DISABLE_CONSTEXPR_MUTEX_CONSTRUCTOR=ON  -DGGML_VULKAN=1
	cmake --build whisper.cpp/build -j --config Release --verbose

	cp whisper.cpp/build/bin/Release/whisper-server.exe buzz/
endif

ifeq ($(shell uname -s), Linux)
	# Build Whisper for CPU
	-rm -rf whisper.cpp/build || true
	-mkdir -p buzz/whisper_cpp
	cmake -S whisper.cpp -B whisper.cpp/build/ -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DCMAKE_INSTALL_RPATH='$$ORIGIN' -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON
	cmake --build whisper.cpp/build -j --config Release --verbose
	cp whisper.cpp/build/src/libwhisper.so buzz/whisper_cpp/libwhisper.so || true
	cp whisper.cpp/build/ggml/src/libggml.so buzz/whisper_cpp || true
	cp whisper.cpp/build/ggml/src/libggml-base.so buzz/whisper_cpp || true
	cp whisper.cpp/build/ggml/src/libggml-cpu.so buzz/whisper_cpp || true

	# Build Whisper for Vulkan
	rm -rf whisper.cpp/build || true
	-mkdir -p buzz/whisper_cpp_vulkan
	cmake -S whisper.cpp -B whisper.cpp/build/ -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DCMAKE_INSTALL_RPATH='$$ORIGIN' -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON -DGGML_VULKAN=1
	cmake --build whisper.cpp/build -j --config Release --verbose
	cp whisper.cpp/build/src/libwhisper.so buzz/whisper_cpp_vulkan/whisper-vulkan.so || true
	cp whisper.cpp/build/ggml/src/libggml.so buzz/whisper_cpp_vulkan || true
	cp whisper.cpp/build/ggml/src/libggml-base.so buzz/whisper_cpp_vulkan || true
	cp whisper.cpp/build/ggml/src/libggml-cpu.so buzz/whisper_cpp_vulkan || true
	cp whisper.cpp/build/ggml/src/ggml-vulkan/libggml-vulkan.so buzz/whisper_cpp_vulkan || true
endif

# Build on Macs
ifeq ($(shell uname -s), Darwin)
	-rm -rf whisper.cpp/build || true
	-mkdir -p buzz/whisper_cpp

ifeq ($(shell uname -m), arm64)
	cmake -S whisper.cpp -B whisper.cpp/build/ -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DWHISPER_COREML=1
else
	cmake -S whisper.cpp -B whisper.cpp/build/ -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON
endif

	cmake --build whisper.cpp/build -j --config Release --verbose
	cp whisper.cpp/build/src/libwhisper.dylib buzz/whisper_cpp/ || true
	cp whisper.cpp/build/ggml/src/libggml* buzz/whisper_cpp/ || true
endif

buzz/whisper_cpp.py: buzz/whisper_cpp translation_mo
	cd buzz && ctypesgen ../whisper.cpp/include/whisper.h -I../whisper.cpp/ggml/include -lwhisper -o ./whisper_cpp/whisper_cpp.py

ifeq ($(shell uname -s), Linux)
	cd buzz && ctypesgen ../whisper.cpp/include/whisper.h -I../whisper.cpp/ggml/include -lwhisper-vulkan -o ./whisper_cpp_vulkan/whisper_cpp_vulkan.py
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

VENV_PATH := $(shell poetry env info -p)

# Make GGML model from whisper. Example: make ggml model_path=/Users/chidiwilliams/.cache/whisper/medium.pt
ggml:
	python3 ./whisper.cpp/models/convert-pt-to-ggml.py ${model_path} $(VENV_PATH)/src/whisper dist

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

TMP_POT_FILE_PATH := $(shell mktemp)
PO_FILE_PATH := buzz/locale/${locale}/LC_MESSAGES/buzz.po
translation_po:
	mkdir -p buzz/locale/${locale}/LC_MESSAGES
	xgettext --from-code=UTF-8 -o "${TMP_POT_FILE_PATH}" -l python $(shell find buzz -name '*.py')
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
