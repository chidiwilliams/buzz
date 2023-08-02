version := $$(poetry version -s)
version_escaped := $$(echo ${version} | sed -e 's/\./\\./g')

mac_app_path := ./dist/Buzz.app
mac_zip_path := ./dist/Buzz-${version}-mac.zip
mac_dmg_path := ./dist/Buzz-${version}-mac.dmg

bundle_linux: dist/Buzz
	bash scripts/bundle_linux.sh

bundle_windows: dist/Buzz
	iscc //DAppVersion=${version} installer.iss

bundle_mac: dist/Buzz.app codesign_all_mac zip_mac notarize_zip staple_app_mac dmg_mac

UNAME_S := $(shell uname -s)

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
	rm -f $(LIBWHISPER)
	rm -f whisper_cpp
	rm -f buzz/whisper_cpp.py
	rm -rf dist/* || true

test: buzz/whisper_cpp.py translation_mo
	pytest -vv --cov=buzz --cov-report=xml --cov-report=html --benchmark-skip

benchmarks: buzz/whisper_cpp.py translation_mo
	pytest -vv --benchmark-only --benchmark-json benchmarks.json

dist/Buzz dist/Buzz.app: buzz/whisper_cpp.py translation_mo
	pyinstaller --noconfirm Buzz.spec

version:
	poetry version ${version}
	echo "VERSION = \"${version}\"" > buzz/__version__.py
	sed -i "" "s/version=.*,/version=\'${version_escaped}\',/" Buzz.spec
	sed -i "" "s/\'version\':.*/'version': \'${version_escaped}\',/" setup.py

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
else
	ifeq ($(OS), Windows_NT)
		CMAKE_FLAGS += -DBUILD_SHARED_LIBS=ON
	endif
endif

$(LIBWHISPER) whisper_cpp:
	cmake -S whisper.cpp -B whisper.cpp/build/ $(CMAKE_FLAGS)
	cmake --build whisper.cpp/build --verbose
	cp whisper.cpp/build/bin/Debug/$(LIBWHISPER) . || true
	cp whisper.cpp/build/bin/Debug/main whisper_cpp || true
	cp whisper.cpp/build/$(LIBWHISPER) . || true
	cp whisper.cpp/build/bin/main whisper_cpp || true

buzz/whisper_cpp.py: $(LIBWHISPER)
	ctypesgen ./whisper.cpp/whisper.h -l$(LIBWHISPER) -o buzz/whisper_cpp.py

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
		--icon "./assets/buzz.icns" 175 120 \
		--hide-extension "Buzz.app" \
		--app-drop-link 425 120 \
		--codesign "$$BUZZ_CODESIGN_IDENTITY" \
		--notarize "$$BUZZ_KEYCHAIN_NOTARY_PROFILE" \
		"${mac_dmg_path}" \
		"dist/dmg/"

staple_app_mac:
	xcrun stapler staple ${mac_app_path}

notarize_zip:
	xcrun notarytool submit ${mac_zip_path} --keychain-profile "$$BUZZ_KEYCHAIN_NOTARY_PROFILE" --wait

zip_mac:
	ditto -c -k --keepParent "${mac_app_path}" "${mac_zip_path}"

codesign_all_mac: dist/Buzz.app
	codesign --force --options=runtime --sign "$$BUZZ_CODESIGN_IDENTITY" --timestamp dist/Buzz.app/Contents/Resources/ffmpeg
	codesign --force --options=runtime --sign "$$BUZZ_CODESIGN_IDENTITY" --timestamp dist/Buzz.app/Contents/Resources/whisper_cpp
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
	$(MAKE) translation_po locale=ca_ES
	$(MAKE) translation_po locale=es_ES
	$(MAKE) translation_po locale=pl_PL
	$(MAKE) translation_po locale=zh_CN
	$(MAKE) translation_po locale=zh_TW
	$(MAKE) translation_po locale=it_IT

TMP_POT_FILE_PATH := $(shell mktemp)
PO_FILE_PATH := locale/${locale}/LC_MESSAGES/buzz.po
translation_po:
	if [[ -f "${PO_FILE_PATH}" ]]; then \
		xgettext --from-code=UTF-8 -o ${TMP_POT_FILE_PATH} -l python buzz/gui.py; \
		sed -i.bak 's/CHARSET/UTF-8/' ${TMP_POT_FILE_PATH} && rm ${TMP_POT_FILE_PATH}.bak; \
		msgmerge -U ${PO_FILE_PATH} ${TMP_POT_FILE_PATH}; \
  	else \
  	  	mkdir -p locale/${locale}/LC_MESSAGES; \
		xgettext --from-code=UTF-8 -o ${PO_FILE_PATH} -l python buzz/gui.py; \
		sed -i.bak 's/CHARSET/UTF-8/' ${PO_FILE_PATH} && rm ${PO_FILE_PATH}.bak; \
	fi

translation_mo:
	for dir in locale/*/ ; do \
		msgfmt --check $$dir/LC_MESSAGES/buzz.po -o $$dir/LC_MESSAGES/buzz.mo; \
	done
