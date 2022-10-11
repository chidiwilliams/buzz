version := $$(poetry version -s)

mac_app_path := ./dist/Buzz.app
mac_zip_path := ./dist/Buzz-${version}-mac.zip
mac_dmg_path := ./dist/Buzz-${version}-mac.dmg

unix_zip_path := ./dist/Buzz-${version}-unix.tar.gz

windows_zip_path := ./dist/Buzz-${version}-windows.tar.gz

buzz:
	make clean
	pyinstaller --noconfirm Buzz.spec

clean:
	rm -r dist/* || true

test:
	pytest --cov --cov-fail-under=63

version:
	poetry version ${version}

bundle_linux:
	make buzz
	tar -czf ${unix_zip_path} dist/Buzz

bundle_windows:
	make buzz
	tar -czf ${windows_zip_path} dist/Buzz

# MAC


bundle_mac:
	make buzz

bundle_mac_local:
	make buzz
	make codesign_all_mac
	make zip_mac
	make notarize_zip
	make staple_app_mac
	make dmg_mac

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
