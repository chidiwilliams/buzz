version := $$(poetry version -s)
version_escaped := $$(echo ${version} | sed -e 's/\./\\./g')

mac_app_path := ./dist/Buzz.app
mac_zip_path := ./dist/Buzz-${version}-mac.zip
mac_dmg_path := ./dist/Buzz-${version}-mac.dmg

bundle_windows: dist/Buzz
	iscc //DAppVersion=${version} installer.iss

bundle_mac: dist/Buzz.app codesign_all_mac zip_mac notarize_zip staple_app_mac dmg_mac

bundle_mac_unsigned: dist/Buzz.app zip_mac dmg_mac_unsigned

UNAME_S := $(shell uname -s)
UNAME_M := $(shell uname -m)

LIBWHISPER :=
ifeq ($(OS), Windows_NT)
	LIBWHISPER=whisper.dll
else
	ifeq ($(UNAME_S), Darwin)
		LIBWHISPER=libwhisper.dylib
	else
		LIBWHISPER=libwhisper.so
	endif
endif

clean:
ifeq ($(OS), Windows_NT)
	-del /f buzz\$(LIBWHISPER) 2> nul
	-del /f buzz\whisper_cpp.py 2> nul
	-rmdir /s /q whisper.cpp\build 2> nul
	-rmdir /s /q dist 2> nul
	-rm -f buzz/$(LIBWHISPER)
	-rm -f buzz/whisper_cpp.py
	-rm -rf whisper.cpp/build || true
	-rm -rf dist/* || true
else
	rm -f buzz/$(LIBWHISPER)
	rm -f buzz/whisper_cpp.py
	rm -f buzz/libwhisper-coreml.dylib || true
	rm -f buzz/whisper_cpp_coreml.py || true
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

CMAKE_FLAGS=
ifeq ($(UNAME_S),Darwin)
	AVX1_M := $(shell sysctl machdep.cpu.features)
	ifeq (,$(findstring AVX1.0,$(AVX1_M)))
		CMAKE_FLAGS += -DWHISPER_NO_AVX=ON
	endif
	ifeq (,$(findstring FMA,$(AVX1_M)))
		CMAKE_FLAGS += -DWHISPER_NO_FMA=ON
	endif
	AVX2_M := $(shell sysctl machdep.cpu.leaf7_features)
	ifeq (,$(findstring AVX2,$(AVX2_M)))
		CMAKE_FLAGS += -DWHISPER_NO_AVX2=ON
	endif
	CMAKE_FLAGS += -DCMAKE_OSX_ARCHITECTURES="x86_64;arm64"
else
	ifeq ($(OS), Windows_NT)
		CMAKE_FLAGS += -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release
	endif
endif

buzz/$(LIBWHISPER):
ifeq ($(OS), Windows_NT)
	cp dll_backup/whisper.dll buzz || copy dll_backup\whisper.dll buzz\whisper.dll
	cp dll_backup/SDL2.dll buzz || copy dll_backup\SDL2.dll buzz\SDL2.dll
else
	cmake -S whisper.cpp -B whisper.cpp/build/ $(CMAKE_FLAGS)
	cmake --build whisper.cpp/build --verbose
	cp whisper.cpp/build/bin/Debug/$(LIBWHISPER) buzz || true
	cp whisper.cpp/build/$(LIBWHISPER) buzz || true
endif
# Build CoreML support on ARM Macs
ifeq ($(shell uname -m), arm64)
ifeq ($(shell uname -s), Darwin)
	rm -rf whisper.cpp/build || true
	cmake -S whisper.cpp -B whisper.cpp/build/ $(CMAKE_FLAGS) -DWHISPER_COREML=1
	cmake --build whisper.cpp/build --verbose
	cp whisper.cpp/build/bin/Debug/$(LIBWHISPER) buzz/libwhisper-coreml.dylib || true
	cp whisper.cpp/build/$(LIBWHISPER) buzz/libwhisper-coreml.dylib || true
endif
endif

buzz/whisper_cpp.py: buzz/$(LIBWHISPER) translation_mo
	cd buzz && ctypesgen ../whisper.cpp/whisper.h -lwhisper -o whisper_cpp.py
ifeq ($(shell uname -m), arm64)
ifeq ($(shell uname -s), Darwin)
	cd buzz && ctypesgen ../whisper.cpp/whisper.h -lwhisper-coreml -o whisper_cpp_coreml.py
endif
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
	$(MAKE) translation_po locale=pt_BR

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
		python msgfmt.py -o $$dir/LC_MESSAGES/buzz.mo $$dir/LC_MESSAGES/buzz.po; \
	done
endif

lint:
	ruff check . --fix
	ruff format .
