# https://www.pythonguis.com/tutorials/packaging-pyqt5-applications-linux-pyinstaller/

PYINSTALLER_BUILD_PATH="dist/Buzz"
PACKAGE_PATH="dist/package"
VERSION=$(poetry version -s)
DEB_PATH="dist/buzz-$VERSION.deb"

mkdir -p $PACKAGE_PATH/opt
mkdir -p $PACKAGE_PATH/usr/share/applications
mkdir -p $PACKAGE_PATH/usr/share/icons/hicolor/scalable/apps

cp -r $PYINSTALLER_BUILD_PATH $PACKAGE_PATH/opt/buzz
cp buzz.desktop $PACKAGE_PATH/usr/share/applications

# Copy icons
cp buzz/assets/buzz.svg $PACKAGE_PATH/usr/share/icons/hicolor/scalable/apps/buzz.svg

# Set permissions
find $PACKAGE_PATH/opt/buzz -type f -exec chmod 644 -- {} +
find $PACKAGE_PATH/opt/buzz -type d -exec chmod 755 -- {} +
find $PACKAGE_PATH/usr/share -type f -exec chmod 644 -- {} +
chmod +x $PACKAGE_PATH/opt/buzz/Buzz

fpm -C $PACKAGE_PATH -s dir -t deb -n "buzz" -v $VERSION -p $DEB_PATH
