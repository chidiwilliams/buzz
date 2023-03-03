/*
 * Copyright (c) 2021 Taner Sener
 *
 * This file is part of FFmpegKit.
 *
 * FFmpegKit is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Lesser General License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * FFmpegKit is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Lesser General License for more details.
 *
 *  You should have received a copy of the GNU Lesser General License
 *  along with FFmpegKit.  If not, see <http://www.gnu.org/licenses/>.
 */

#ifndef FFMPEG_KIT_PACKAGES_H
#define FFMPEG_KIT_PACKAGES_H

#import <Foundation/Foundation.h>

/**
 * <p>Helper class to extract binary package information.
 */
@interface Packages : NSObject

/**
 * Returns the FFmpegKit binary package name.
 *
 * @return predicted FFmpegKit binary package name
 */
+ (NSString*)getPackageName;

/**
 * Returns enabled external libraries by FFmpeg.
 *
 * @return enabled external libraries
 */
+ (NSArray*)getExternalLibraries;

@end

#endif // FFMPEG_KIT_PACKAGES_H
