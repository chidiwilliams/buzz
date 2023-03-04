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

#ifndef FFMPEG_KIT_STREAM_INFORMATION_H
#define FFMPEG_KIT_STREAM_INFORMATION_H

#import <Foundation/Foundation.h>

extern NSString* const StreamKeyIndex;
extern NSString* const StreamKeyType;
extern NSString* const StreamKeyCodec;
extern NSString* const StreamKeyCodecLong;
extern NSString* const StreamKeyFormat;
extern NSString* const StreamKeyWidth;
extern NSString* const StreamKeyHeight;
extern NSString* const StreamKeyBitRate;
extern NSString* const StreamKeySampleRate;
extern NSString* const StreamKeySampleFormat;
extern NSString* const StreamKeyChannelLayout;
extern NSString* const StreamKeySampleAspectRatio;
extern NSString* const StreamKeyDisplayAspectRatio;
extern NSString* const StreamKeyAverageFrameRate;
extern NSString* const StreamKeyRealFrameRate;
extern NSString* const StreamKeyTimeBase;
extern NSString* const StreamKeyCodecTimeBase;
extern NSString* const StreamKeyTags;

/**
 * Stream information class.
 */
@interface StreamInformation : NSObject

- (instancetype)init:(NSDictionary*)streamDictionary;

/**
 * Returns stream index.
 *
 * @return stream index, starting from zero
 */
- (NSNumber*)getIndex;

/**
 * Returns stream type.
 *
 * @return stream type; audio or video
 */
- (NSString*)getType;

/**
 * Returns stream codec.
 *
 * @return stream codec
 */
- (NSString*)getCodec;

/**
 * Returns stream codec in long format.
 *
 * @return stream codec with additional profile and mode information
 */
- (NSString*)getCodecLong;

/**
 * Returns stream format.
 *
 * @return stream format
 */
- (NSString*)getFormat;

/**
 * Returns width.
 *
 * @return width in pixels
 */
- (NSNumber*)getWidth;

/**
 * Returns height.
 *
 * @return height in pixels
 */
- (NSNumber*)getHeight;

/**
 * Returns bitrate.
 *
 * @return bitrate in kb/s
 */
- (NSString*)getBitrate;

/**
 * Returns sample rate.
 *
 * @return sample rate in hz
 */
- (NSString*)getSampleRate;

/**
 * Returns sample format.
 *
 * @return sample format
 */
- (NSString*)getSampleFormat;

/**
 * Returns channel layout.
 *
 * @return channel layout
 */
- (NSString*)getChannelLayout;

/**
 * Returns sample aspect ratio.
 *
 * @return sample aspect ratio
 */
- (NSString*)getSampleAspectRatio;

/**
 * Returns display aspect ratio.
 *
 * @return display aspect ratio
 */
- (NSString*)getDisplayAspectRatio;

/**
 * Returns average frame rate.
 *
 * @return average frame rate in fps
 */
- (NSString*)getAverageFrameRate;

/**
 * Returns real frame rate.
 *
 * @return real frame rate in tbr
 */
- (NSString*)getRealFrameRate;

/**
 * Returns time base.
 *
 * @return time base in tbn
 */
- (NSString*)getTimeBase;

/**
 * Returns codec time base.
 *
 * @return codec time base in tbc
 */
- (NSString*)getCodecTimeBase;

/**
 * Returns all tags.
 *
 * @return tags dictionary
 */
- (NSDictionary*)getTags;

/**
 * Returns the stream property associated with the key.
 *
 * @return stream property as string or nil if the key is not found
 */
- (NSString*)getStringProperty:(NSString*)key;

/**
 * Returns the stream property associated with the key.
 *
 * @return stream property as number or nil if the key is not found
 */
- (NSNumber*)getNumberProperty:(NSString*)key;

/**
 * Returns the stream properties associated with the key.
 *
 * @return stream properties in a dictionary or nil if the key is not found
*/
- (NSDictionary*)getProperties:(NSString*)key;

/**
 * Returns all stream properties defined.
 *
 * @return all stream properties in a dictionary or nil if no properties are defined
*/
- (NSDictionary*)getAllProperties;

@end

#endif // FFMPEG_KIT_STREAM_INFORMATION_H
