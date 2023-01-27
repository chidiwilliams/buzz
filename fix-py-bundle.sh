#!/bin/zsh

if [ ! -d "$1" ]; then
   echo "usage: fix-py-bundle.sh <app-bundle>" >&2
   exit 1
fi

WRAPPER_NAME="$(basename $1 .app)"

pushd "$1" > /dev/null

   # move any shared objects and other dependencies to Frameworks
    find Contents/MacOS/ -iname '*.dylib' -mindepth 0 -maxdepth 1 -exec mv '{}' Contents/Frameworks/ ';'
    find Contents/MacOS/ -iname '*.so'    -mindepth 0 -maxdepth 1 -exec mv '{}' Contents/Frameworks/ ';'
    find Contents/MacOS/ -name 'Qt*'     -mindepth 0 -maxdepth 1 -exec mv '{}' Contents/Frameworks/ ';'
    find Contents/MacOS/ -type d          -mindepth 1 -maxdepth 1 -exec mv '{}' Contents/Frameworks/ ';'

   # add the missing rpath entries to actually look in Frameworks for shared objects
    install_name_tool -add_rpath '@executable_path' "Contents/MacOS/$WRAPPER_NAME"
    install_name_tool -add_rpath '@executable_path' Contents/MacOS/Python || true
    install_name_tool -add_rpath '@executable_path/../Frameworks/' "Contents/MacOS/$WRAPPER_NAME"
    install_name_tool -add_rpath '@executable_path/../Frameworks/' Contents/MacOS/Python || true

   # create symlinks for all directories that got moved to Frameworks since we don't have influence on
   # PYTHONPATH (would not be needed if it contained @executable_path/../Frameworks as well)
    pushd Contents/MacOS/ > /dev/null
    find ../Frameworks/ -type d -mindepth 1 -maxdepth 1 -exec ln -s '{}' . ';'
    popd  > /dev/null

    # refresh the ad-hoc signature (could our actual signing profile here..)
    # codesign -s - -f --deep .
popd > /dev/null
