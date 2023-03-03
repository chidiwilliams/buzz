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

#ifndef FFMPEG_KIT_SESSION_H
#define FFMPEG_KIT_SESSION_H

#import <Foundation/Foundation.h>
#import "Log.h"
#import "LogCallback.h"
#import "LogRedirectionStrategy.h"
#import "ReturnCode.h"
#import "SessionState.h"

/**
 * <p>Common interface for all <code>FFmpegKit</code> sessions.
 */
@protocol Session

@required

/**
 * Returns the session specific log callback.
 *
 * @return session specific log callback
 */
- (LogCallback)getLogCallback;

/**
 * Returns the session identifier.
 *
 * @return session identifier
 */
- (long)getSessionId;

/**
 * Returns session create time.
 *
 * @return session create time
 */
- (NSDate*)getCreateTime;

/**
 * Returns session start time.
 *
 * @return session start time
 */
- (NSDate*)getStartTime;

/**
 * Returns session end time.
 *
 * @return session end time
 */
- (NSDate*)getEndTime;

/**
 * Returns the time taken to execute this session.
 *
 * @return time taken to execute this session in milliseconds or zero (0) if the session is
 * not over yet
 */
- (long)getDuration;

/**
 * Returns command arguments as an array.
 *
 * @return command arguments as an array
 */
- (NSArray*)getArguments;

/**
 * Returns command arguments as a concatenated string.
 *
 * @return command arguments as a concatenated string
 */
- (NSString*)getCommand;

/**
 * Returns all log entries generated for this session. If there are asynchronous
 * messages that are not delivered yet, this method waits for them until the given timeout.
 *
 * @param waitTimeout wait timeout for asynchronous messages in milliseconds
 * @return list of log entries generated for this session
 */
- (NSArray*)getAllLogsWithTimeout:(int)waitTimeout;

/**
 * Returns all log entries generated for this session. If there are asynchronous
 * messages that are not delivered yet, this method waits for them.
 *
 * @return list of log entries generated for this session
 */
- (NSArray*)getAllLogs;

/**
 * Returns all log entries delivered for this session. Note that if there are asynchronous
 * messages that are not delivered yet, this method will not wait for them and will return
 * immediately.
 *
 * @return list of log entries received for this session
 */
- (NSArray*)getLogs;

/**
 * Returns all log entries generated for this session as a concatenated string. If there are
 * asynchronous messages that are not delivered yet, this method waits for them until
 * the given timeout.
 *
 * @param waitTimeout wait timeout for asynchronous messages in milliseconds
 * @return all log entries generated for this session as a concatenated string
 */
- (NSString*)getAllLogsAsStringWithTimeout:(int)waitTimeout;

/**
 * Returns all log entries generated for this session as a concatenated string. If there are
 * asynchronous messages that are not delivered yet, this method waits for them.
 *
 * @return all log entries generated for this session as a concatenated string
 */
- (NSString*)getAllLogsAsString;

/**
 * Returns all log entries delivered for this session as a concatenated string. Note that if
 * there are asynchronous messages that are not delivered yet, this method will not wait
 * for them and will return immediately.
 *
 * @return list of log entries received for this session
 */
- (NSString*)getLogsAsString;

/**
 * Returns the log output generated while running the session.
 *
 * @return log output generated
 */
- (NSString*)getOutput;

/**
 * Returns the state of the session.
 *
 * @return state of the session
 */
- (SessionState)getState;

/**
 * Returns the return code for this session. Note that return code is only set for sessions
 * that end with SessionStateCompleted state. If a session is not started, still running or failed then
 * this method returns nil.
 *
 * @return the return code for this session if the session has completed, nil if session is
 * not started, still running or failed
 */
- (ReturnCode*)getReturnCode;

/**
 * Returns the stack trace of the exception received while executing this session.
 * <p>
 * The stack trace is only set for sessions that end with SessionStateFailed state. For sessions that has
 * SessionStateCompleted state this method returns nil.
 *
 * @return stack trace of the exception received while executing this session, nil if session
 * is not started, still running or completed
 */
- (NSString*)getFailStackTrace;

/**
 * Returns session specific log redirection strategy.
 *
 * @return session specific log redirection strategy
 */
- (LogRedirectionStrategy)getLogRedirectionStrategy;

/**
 * Returns whether there are still asynchronous messages being transmitted for this
 * session or not.
 *
 * @return true if there are still asynchronous messages being transmitted, false
 * otherwise
 */
- (BOOL)thereAreAsynchronousMessagesInTransmit;

/**
 * Adds a new log entry for this session.
 *
 * It is invoked internally by <code>FFmpegKit</code> library methods. Must not be used by user
 * applications.
 *
 * @param log log entry
 */
- (void)addLog:(Log*)log;

/**
 * Starts running the session.
 */
- (void)startRunning;

/**
 * Completes running the session with the provided return code.
 *
 * @param returnCode return code of the execution
 */
- (void)complete:(ReturnCode*)returnCode;

/**
 * Ends running the session with a failure.
 *
 * @param exception execution received
 */
- (void)fail:(NSException*)exception;

/**
 * Returns whether it is an <code>FFmpeg</code> session or not.
 *
 * @return true if it is an <code>FFmpeg</code> session, false otherwise
 */
- (BOOL)isFFmpeg;

/**
 * Returns whether it is an <code>FFprobe</code> session or not.
 *
 * @return true if it is an <code>FFprobe</code> session, false otherwise
 */
- (BOOL)isFFprobe;

/**
 * Returns whether it is a <code>MediaInformation</code> session or not.
 *
 * @return true if it is a <code>MediaInformation</code> session, false otherwise
 */
- (BOOL)isMediaInformation;

/**
 * Cancels running the session.
 */
- (void)cancel;

@end

#endif // FFMPEG_KIT_SESSION_H
