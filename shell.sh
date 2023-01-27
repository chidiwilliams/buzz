BUZZ_DIR=$(mktemp -d "${TMPDIR:-/tmp}"/buzz.XXXX)

cd $BUZZ_DIR

xcode-select --install || true

# Set up Apple certificates. Source: https://github.com/cirruslabs/macos-image-templates/blob/baa16d28efa9cb476738e7134646be163215adb2/templates/xcode.pkr.hcl#L118
sudo security delete-certificate -Z FF6797793A3CD798DC5B2ABEF56F73EDC9F83A64 /Library/Keychains/System.keychain || true
curl -o add-certificate.swift https://raw.githubusercontent.com/actions/runner-images/fb3b6fd69957772c1596848e2daaec69eabca1bb/images/macos/provision/configuration/add-certificate.swift
swiftc add-certificate.swift
curl -o AppleWWDRCAG3.cer https://www.apple.com/certificateauthority/AppleWWDRCAG3.cer
curl -o DeveloperIDG2CA.cer https://www.apple.com/certificateauthority/DeveloperIDG2CA.cer
sudo ./add-certificate AppleWWDRCAG3.cer
sudo ./add-certificate DeveloperIDG2CA.cer
rm add-certificate* *.cer

# Set up signing certificates
echo $MACOS_CERTIFICATE | base64 --decode > certificate.p12
KEYCHAIN_PATH=build-$(openssl rand -hex 6).keychain
security create-keychain -p password $KEYCHAIN_PATH
security default-keychain -s $KEYCHAIN_PATH
security unlock-keychain -p password $KEYCHAIN_PATH
security import certificate.p12 -k $KEYCHAIN_PATH -P $P12_PASSWORD -T /usr/bin/codesign -T /usr/bin/pkgbuild
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k password $KEYCHAIN_PATH
xcrun notarytool store-credentials --apple-id "$APPLE_ID" --password "$APPLE_APP_PASSWORD" --team-id "$APPLE_TEAM_ID" notarytool --validate
security find-identity

# Install brew
if ! [ -x "$(command -v bash)" ]; then
  echo 'Installing bash...'
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
  brew update
fi

brew install xz ffmpeg gettext cmake create-dmg

# Install pyenv
if ! [ -x "$(command -v pyenv)" ]; then
  echo "Installing pyenv..."
  brew install pyenv
  echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
  echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
  echo 'eval "$(pyenv init -)"' >> ~/.zshrc
  source ~/.zshrc
fi

# Install Python
if ! [[ $(python -V) == "Python 3.10.7" ]]; then
  echo "Installing Python..."
  pyenv install 3.10.7
  pyenv global 3.10.7
  source ~/.zshrc
fi
python3 --version

# Install Poetry
if ! [ -x "$(command -v poetry)" ]; then
  curl -sSL https://install.python-poetry.org | python3 -
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
  source ~/.zshrc

  poetry config experimental.new-installer false
  poetry config virtualenvs.create true
  poetry config virtualenvs.in-project true
fi

# Clone
git clone --recurse-submodules https://github.com/chidiwilliams/buzz
cd buzz

# Install project dependencies
poetry install

# Build
source .venv/bin/activate
make bundle_mac
