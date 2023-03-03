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

#ifndef FFMPEG_KIT_MEDIA_INFORMATION_H
#define FFMPEG_KIT_MEDIA_INFORMATION_H

#import <Foundation/Foundation.h>
#import "Chapter.h"
#import "StreamInformation.h"

extern NSString* const MediaKeyMediaProperties;
extern NSString* const MediaKeyFilename;
extern NSString* const MediaKeyFormat;
extern NSString* const MediaKeyFormatLong;
extern NSString* const MediaKeyStartTime;
extern NSString* const MediaKeyDuration;
extern NSString* const MediaKeySize;
extern NSString* const MediaKeyBitRate;
extern NSString* const MediaKeyTags;

/**
 * Media information class.
 */
@interface MediaInformation : NSObject

- (instancetype)init:(NSDictionary*)mediaDictionary withStreams:(NSArray*)streams withChapters:(NSArray*)chapters;

/**
 * Returns file name.
 *
 * @return media file name
 */
- (NSString*)getFilename;

/**
 * Returns format.
 *
 * @return media format
 */
- (NSString*)getFormat;

/**
 * Returns long format.
 *
 * @return media long format
 */
- (NSString*)getLongFormat;

/**
 * Returns duration.
 *
 * @return media duration in milliseconds
 */
- (NSString*)getDuration;

/**
 * Returns start time.
 *
 * @return media start time in milliseconds
 */
- (NSString*)getStartTime;

/**
 * Returns size.
 *
 * @return media size in bytes
 */
- (NSString*)getSize;

/**
 * Returns bitrate.
 *
 * @return media bitrate in kb/s
 */
- (NSString*)getBitrate;

/**
 * Returns all tags.
 *
 * @return tags dictionary
 */
- (NSDictionary*)getTags;

/**
 * Returns all streams.
 *
 * @return streams array
 */
- (NSArray*)getStreams;

/**
 * Returns all chapters.
 *
 * @return chapters array
 */
- (NSArray*)getChapters;

/**
 * Returns the media property associated with the key.
 *
 * @return media property as string or nil if the key is not found
 */
- (NSString*)getStringProperty:(NSString*)key;

/**
 * Returns the media property associated with the key.
 *
 * @return media property as number or nil if the key is not found
 */
- (NSNumber*)getNumberProperty:(NSString*)key;

/**
 * Returns the media properties associated with the key.
 *
 * @return media properties in a dictionary or nil if the key is not found
*/
- (NSDictionary*)getProperties:(NSString*)key;

/**
 * Returns all media properties.
 *
 * @return all media properties in a dictionary or nil if no media properties are defined
*/
- (NSDictionary*)getMediaProperties;

/**
 * Returns all properties defined.
 *
 * @return all properties in a dictionary or nil if no properties are defined
*/
- (NSDictionary*)getAllProperties;

@end

#endif // FFMPEG_KIT_MEDIA_INFORMATION_H
