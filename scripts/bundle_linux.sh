PYINSTALLER_BUILD_PATH="dist/Buzz"
PACKAGE_PATH="dist/package"

mkdir -p $PACKAGE_PATH/opt
mkdir -p $PACKAGE_PATH/usr/share/applications
mkdir -p $PACKAGE_PATH/usr/share/icons/hicolor/scalable/apps
cp -r $PYINSTALLER_BUILD_PATH $PACKAGE_PATH/opt/buzz
cp buzz.desktop $PACKAGE_PATH/usr/share/applications

find $PACKAGE_PATH/opt/hello-world -type f -exec chmod 644 -- {} +
find $PACKAGE_PATH/opt/hello-world -type d -exec chmod 755 -- {} +
find $PACKAGE_PATH/usr/share -type f -exec chmod 644 -- {} +
chmod +x $PACKAGE_PATH/opt/buzz/Buzz

fpm -C $PACKAGE_PATH -s dir -t deb -n "buzz" -v 0.1.0 -p buzz.deb
