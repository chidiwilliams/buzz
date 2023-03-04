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

#ifndef FFMPEG_KIT_MEDIA_INFORMATION_SESSION_H
#define FFMPEG_KIT_MEDIA_INFORMATION_SESSION_H

#import <Foundation/Foundation.h>
#import "AbstractSession.h"
#import "MediaInformation.h"
#import "MediaInformationSessionCompleteCallback.h"

/**
 * <p>A custom FFprobe session, which produces a <code>MediaInformation</code> object using the
 * FFprobe output.
 */
@interface MediaInformationSession : AbstractSession

/**
 * Creates a new media information session.
 *
 * @param arguments command arguments
 */
- (instancetype)init:(NSArray*)arguments;

/**
 * Creates a new media information session.
 *
 * @param arguments        command arguments
 * @param completeCallback session specific complete callback
 */
- (instancetype)init:(NSArray*)arguments withCompleteCallback:(MediaInformationSessionCompleteCallback)completeCallback;

/**
 * Creates a new media information session.
 *
 * @param arguments        command arguments
 * @param completeCallback session specific complete callback
 * @param logCallback      session specific log callback
 */
- (instancetype)init:(NSArray*)arguments withCompleteCallback:(MediaInformationSessionCompleteCallback)completeCallback withLogCallback:(LogCallback)logCallback;

/**
 * Returns the media information extracted in this session.
 *
 * @return media information extracted or nil if the command failed or the output can not be
 * parsed
 */
- (MediaInformation*)getMediaInformation;

/**
 * Sets the media information extracted in this session.
 *
 * @param mediaInformation media information extracted
 */
- (void)setMediaInformation:(MediaInformation*)mediaInformation;

/**
 * Returns the session specific complete callback.
 *
 * @return session specific complete callback
 */
- (MediaInformationSessionCompleteCallback)getCompleteCallback;

@end

#endif // FFMPEG_KIT_MEDIA_INFORMATION_SESSION_H
