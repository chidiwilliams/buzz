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

#ifndef FFMPEG_KIT_FFPROBE_SESSION_H
#define FFMPEG_KIT_FFPROBE_SESSION_H

#import <Foundation/Foundation.h>
#import "AbstractSession.h"
#import "FFprobeSessionCompleteCallback.h"

/**
 * <p>An FFprobe session.
 */
@interface FFprobeSession : AbstractSession

/**
 * Builds a new FFprobe session.
 *
 * @param arguments command arguments
 */
- (instancetype)init:(NSArray*)arguments;

/**
 * Builds a new FFprobe session.
 *
 * @param arguments        command arguments
 * @param completeCallback session specific complete callback
 */
- (instancetype)init:(NSArray*)arguments withCompleteCallback:(FFprobeSessionCompleteCallback)completeCallback;

/**
 * Builds a new FFprobe session.
 *
 * @param arguments        command arguments
 * @param completeCallback session specific complete callback
 * @param logCallback      session specific log callback
 */
- (instancetype)init:(NSArray*)arguments withCompleteCallback:(FFprobeSessionCompleteCallback)completeCallback withLogCallback:(LogCallback)logCallback;

/**
 * Builds a new FFprobe session.
 *
 * @param arguments               command arguments
 * @param completeCallback        session specific complete callback
 * @param logCallback             session specific log callback
 * @param logRedirectionStrategy  session specific log redirection strategy
 */
- (instancetype)init:(NSArray*)arguments withCompleteCallback:(FFprobeSessionCompleteCallback)completeCallback withLogCallback:(LogCallback)logCallback withLogRedirectionStrategy:(LogRedirectionStrategy)logRedirectionStrategy;

/**
 * Returns the session specific complete callback.
 *
 * @return session specific complete callback
 */
- (FFprobeSessionCompleteCallback)getCompleteCallback;

@end

#endif // FFMPEG_KIT_FFPROBE_SESSION_H
