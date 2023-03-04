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

#ifndef FFMPEG_KIT_ABSTRACT_SESSION_H
#define FFMPEG_KIT_ABSTRACT_SESSION_H

#import <Foundation/Foundation.h>
#import "Session.h"

/**
 * Defines how long default "getAll" methods wait, in milliseconds.
 */
extern int const AbstractSessionDefaultTimeoutForAsynchronousMessagesInTransmit;

/**
 * Abstract session implementation which includes common features shared by <code>FFmpeg</code>,
 * <code>FFprobe</code> and <code>MediaInformation</code> sessions.
 */
@interface AbstractSession : NSObject<Session>

/**
 * Creates a new abstract session.
 *
 * @param arguments              command arguments
 * @param logCallback            session specific log callback
 * @param logRedirectionStrategy session specific log redirection strategy
 */
- (instancetype)init:(NSArray*)arguments withLogCallback:(LogCallback)logCallback withLogRedirectionStrategy:(LogRedirectionStrategy)logRedirectionStrategy;

/**
 * Waits for all asynchronous messages to be transmitted until the given timeout.
 *
 * @param timeout wait timeout in milliseconds
 */
- (void)waitForAsynchronousMessagesInTransmit:(int)timeout;

@end

#endif // FFMPEG_KIT_ABSTRACT_SESSION_H
