version := $$(poetry version -s)
version_escaped := $$(echo ${version} | sed -e 's/\./\\./g')

mac_app_path := ./dist/Buzz.app
mac_zip_path := ./dist/Buzz-${version}-mac.zip
mac_dmg_path := ./dist/Buzz-${version}-mac.dmg

unix_zip_path := Buzz-${version}-unix.tar.gz

windows_zip_path := Buzz-${version}-windows.tar.gz

bundle_linux: dist/Buzz
	cd dist && tar -czf ${unix_zip_path} Buzz/ && cd -

bundle_windows: dist/Buzz
	iscc //DAppVersion=${version} installer.iss
	cd dist && tar -czf ${windows_zip_path} Buzz/ && cd -

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

test: buzz/whisper_cpp.py
	pytest -vv --cov=buzz --cov-report=xml --cov-report=html

dist/Buzz dist/Buzz.app: buzz/whisper_cpp.py
	pyinstaller --noconfirm Buzz.spec

version:
	poetry version ${version}
	echo "VERSION = \"${version}\"" > buzz/__version__.py
	sed -i "" "s/version=.*,/version=\'${version_escaped}\',/" Buzz.spec

CMAKE_FLAGS=
ifeq ($(UNAME_S),Darwin)
	AVX1_M := $(shell sysctl machdep.cpu.features)
	ifeq (,$(findstring AVX1.0,$(AVX1_M)))
		CMAKE_FLAGS += -DWHISPER_NO_AVX=ON
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

GET_PR_URL = $(shell gh pr create --fill | grep 'pull\/\d*')
SET_PR_URL = $(eval PR_URL=$(GET_PR_URL))
BRANCH := upgrade-to-${version}
gh_upgrade_pr:
	git checkout main && git pull
	git checkout -B ${BRANCH}

	make version version=${version}

	git commit -am "Upgrade to ${version}"
	git push --set-upstream origin ${BRANCH}

	gh pr create --fill
	gh pr merge ${BRANCH} --auto --squash
	$(SET_PR_URL)
	gh pr merge ${BRANCH} --auto --squash

	if [[ -z "$(which gh)" ]]; then
	  printf ":hand: This script requires the GitHub CLI to run. Please install it and try again.\n"
	fi

	while ! gh pr checks "$$PR_URL" | grep -q 'pending'; do
	  printf ":stopwatch: PR checks still pending, retrying in 10 seconds...\n"
	  sleep 10
	done

	if ! gh pr checks "$$PR_URL" | grep -q 'fail'; then
	  printf ":x: PR checks failed!\n"
	  exit 1
	fi

	if ! gh pr checks "$$PR_URL" | grep  -q 'pass'; then
	  printf ":white_check_mark: PR checks passed!\n"
	  exit 0
	fi

	printf ":confused: An unknown error occurred!\n"
	exit 1
