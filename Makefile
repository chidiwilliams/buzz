version := $$(poetry version -s)

mac_app_path := ./dist/Buzz.app
mac_zip_path := ./dist/Buzz-${version}-mac.zip
mac_dmg_path := ./dist/Buzz-${version}-mac.dmg

unix_zip_path := Buzz-${version}-unix.tar.gz

windows_zip_path := Buzz-${version}-windows.tar.gz

bundle_linux: dist/Buzz
	cd dist && tar -czf ${unix_zip_path} Buzz/ && cd -

dist/Buzz.exe: dist/Buzz
	iscc //DAppVersion=${version} installer.iss

bundle_mac: dist/Buzz
	make zip_mac

bundle_mac_local: dist/Buzz
	make codesign_all_mac
	make zip_mac
	make notarize_zip
	make staple_app_mac
	make dmg_mac

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
	rm -rf dist/* || true

test: $(LIBWHISPER)
	pytest --cov --cov-fail-under=67 --cov-report html

dist/Buzz: $(LIBWHISPER)
	pyinstaller --noconfirm Buzz.spec

version:
	poetry version ${version}
	echo "VERSION = \"${version}\"" > __version__.py

CMAKE_FLAGS=
ifeq ($(UNAME_S),Darwin)
	AVX1_M := $(shell sysctl machdep.cpu.features)
	ifeq (,$(findstring AVX1.0,$(AVX1_M)))
		CMAKE_FLAGS += -DWHISPER_NO_AVX
	endif
	AVX2_M := $(shell sysctl machdep.cpu.leaf7_features)
	ifeq (,$(findstring AVX2,$(AVX2_M)))
		CFLAGS += -DWHISPER_NO_AVX2
	endif
endif

$(LIBWHISPER):
	cmake -S whisper.cpp -B whisper.cpp/build/ $(CMAKE_FLAGS)
	cmake --build whisper.cpp/build --verbose
	cp whisper.cpp/build/$(LIBWHISPER) . || true

whisper_cpp.py: $(LIBWHISPER)
	ctypesgen ./whisper.cpp/whisper.h -l$(LIBWHISPER) -o whisper_cpp.py

staple_app_mac:
	xcrun stapler staple ${mac_app_path}

codesign_all_mac:
	make codesign_mac path="./dist/Buzz.app"
	make codesign_mac path="./dist/Buzz.app/Contents/MacOS/Buzz"
	for i in $$(find dist/Buzz.app/Contents/Resources -name "*.dylib" -o -name "*.so" -type f); \
	do \
		make codesign_mac path="$$i"; \
	done
	for i in $$(find dist/Buzz.app/Contents/Resources/torch/bin -name "*" -type f); \
	do \
		make codesign_mac path="$$i"; \
	done
	make codesign_mac path="./dist/Buzz.app/Contents/Resources/ffmpeg"
	make codesign_mac path="./dist/Buzz.app/Contents/MacOS/Buzz"
	make codesign_verify

codesign_mac:
	codesign --deep --force --options=runtime --entitlements ./entitlements.plist --sign "$$BUZZ_CODESIGN_IDENTITY" --timestamp ${path}

zip_mac:
	ditto -c -k --keepParent "${mac_app_path}" "${mac_zip_path}"

# Prints all the Mac developer identities used for code signing
print_identities_mac:
	security find-identity -p basic -v

notarize_zip:
	xcrun notarytool submit ${mac_zip_path} --keychain-profile "$$BUZZ_KEYCHAIN_NOTARY_PROFILE" --wait

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

# HELPERS

# Get the build logs for a notary upload
notarize_log:
	xcrun notarytool log ${id} --keychain-profile "$$BUZZ_KEYCHAIN_NOTARY_PROFILE"

codesign_verify:
	codesign --verify --deep --strict --verbose=2 dist/Buzz.app
