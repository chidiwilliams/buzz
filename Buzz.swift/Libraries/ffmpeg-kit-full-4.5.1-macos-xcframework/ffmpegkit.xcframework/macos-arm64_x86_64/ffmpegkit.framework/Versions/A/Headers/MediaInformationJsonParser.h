/*
 * Copyright (c) 2018-2021 Taner Sener
 *
 * This file is part of FFmpegKit.
 *
 * FFmpegKit is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Lesser General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * FFmpegKit is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License
 * along with FFmpegKit.  If not, see <http://www.gnu.org/licenses/>.
 */

#ifndef FFMPEG_KIT_MEDIA_INFORMATION_PARSER_H
#define FFMPEG_KIT_MEDIA_INFORMATION_PARSER_H

#import <Foundation/Foundation.h>
#import "MediaInformation.h"

/**
 * A parser that constructs MediaInformation from FFprobe's json output.
 */
@interface MediaInformationJsonParser : NSObject

/**
 * Extracts <code>MediaInformation</code> from the given FFprobe json output.
 *
 * @param ffprobeJsonOutput FFprobe json output
 * @return created MediaInformation instance of nil if a parsing error occurs
 */
+ (MediaInformation*)from:(NSString*)ffprobeJsonOutput;

/**
 * Extracts <code>MediaInformation</code> from the given FFprobe json output.
 *
 * @param ffprobeJsonOutput FFprobe json output
 * @param error error to save the parsing error if a parsing error occurs
 * @return created MediaInformation instance
 */
+ (MediaInformation*)from:(NSString*)ffprobeJsonOutput with:(NSError*)error;

@end

#endif // FFMPEG_KIT_MEDIA_INFORMATION_PARSER_H
