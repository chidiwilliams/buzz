/*
 * Copyright (c) 2021 Taner Sener
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

#ifndef FFMPEG_KIT_CHAPTER_H
#define FFMPEG_KIT_CHAPTER_H

#import <Foundation/Foundation.h>

extern NSString* const ChapterKeyId;
extern NSString* const ChapterKeyTimeBase;
extern NSString* const ChapterKeyStart;
extern NSString* const ChapterKeyStartTime;
extern NSString* const ChapterKeyEnd;
extern NSString* const ChapterKeyEndTime;
extern NSString* const ChapterKeyTags;

/**
 * Chapter class.
 */
@interface Chapter : NSObject

- (instancetype)init:(NSDictionary*)chapterDictionary;

- (NSNumber*)getId;

- (NSString*)getTimeBase;

- (NSNumber*)getStart;

- (NSString*)getStartTime;

- (NSNumber*)getEnd;

- (NSString*)getEndTime;

- (NSDictionary*)getTags;

/**
 * Returns the chapter property associated with the key.
 *
 * @return chapter property as string or nil if the key is not found
 */
- (NSString*)getStringProperty:(NSString*)key;

/**
 * Returns the chapter property associated with the key.
 *
 * @return chapter property as number or nil if the key is not found
 */
- (NSNumber*)getNumberProperty:(NSString*)key;

/**
 * Returns the chapter properties associated with the key.
 *
 * @return chapter properties in a dictionary or nil if the key is not found
*/
- (NSDictionary*)getProperties:(NSString*)key;

/**
 * Returns all chapter properties defined.
 *
 * @return all chapter properties in a dictionary or nil if no properties are defined
*/
- (NSDictionary*)getAllProperties;

@end

#endif // FFMPEG_KIT_CHAPTER_H
