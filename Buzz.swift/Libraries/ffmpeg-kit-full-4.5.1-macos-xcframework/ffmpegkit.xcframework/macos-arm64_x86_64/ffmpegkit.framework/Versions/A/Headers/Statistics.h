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

#ifndef FFMPEG_KIT_STATISTICS_H
#define FFMPEG_KIT_STATISTICS_H

#import <Foundation/Foundation.h>

/**
 * Statistics entry for an FFmpeg execute session.
 */
@interface Statistics : NSObject

- (instancetype)init:(long)sessionId videoFrameNumber:(int)videoFrameNumber videoFps:(float)videoFps videoQuality:(float)videoQuality size:(int64_t)size time:(int)time bitrate:(double)bitrate speed:(double)speed;

- (long)getSessionId;

- (int)getVideoFrameNumber;

- (float)getVideoFps;

- (float)getVideoQuality;

- (long)getSize;

- (int)getTime;

- (double)getBitrate;

- (double)getSpeed;

@end

#endif // FFMPEG_KIT_STATISTICS_H
