/*
 * Copyright (c) 2020-2021 Taner Sener
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

#ifndef FFPROBE_KIT_H
#define FFPROBE_KIT_H

#import <string.h>
#import <stdlib.h>
#import <Foundation/Foundation.h>
#import "FFprobeSession.h"
#import "MediaInformationJsonParser.h"

/**
 * <p>Main class to run <code>FFprobe</code> commands. Supports executing commands both synchronously and
 * asynchronously.
 * <pre>
 * FFprobeSession *session = [FFprobeKit execute:@"-hide_banner -v error -show_entries format=size -of default=noprint_wrappers=1 file1.mp4"];
 *
 * FFprobeSession *asyncSession = [FFprobeKit executeAsync:@"-hide_banner -v error -show_entries format=size -of default=noprint_wrappers=1 file1.mp4" withCompleteCallback:completeCallback];
 * </pre>
 * <p>Provides overloaded <code>execute</code> methods to define session specific callbacks.
 * <pre>
 * FFprobeSession *session = [FFprobeKit executeAsync:@"-hide_banner -v error -show_entries format=size -of default=noprint_wrappers=1 file1.mp4" withCompleteCallback:completeCallback withLogCallback:logCallback];
 * </pre>
 * <p>It can extract media information for a file or a url, using getMediaInformation method.
 * <pre>
 *      MediaInformationSession *session = [FFprobeKit getMediaInformation:@"file1.mp4"];
 * </pre>
 */
@interface FFprobeKit : NSObject

/**
 * <p>Synchronously executes FFprobe with arguments provided.
 *
 * @param arguments FFprobe command options/arguments as string array
 * @return FFprobe session created for this execution
 */
+ (FFprobeSession*)executeWithArguments:(NSArray*)arguments;

/**
 * <p>Starts an asynchronous FFprobe execution with arguments provided.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete.
 * You must use an FFprobeSessionCompleteCallback if you want to be notified about the result.
 *
 * @param arguments        FFprobe command options/arguments as string array
 * @param completeCallback callback that will be called when the execution has completed
 * @return FFprobe session created for this execution
 */
+ (FFprobeSession*)executeWithArgumentsAsync:(NSArray*)arguments withCompleteCallback:(FFprobeSessionCompleteCallback)completeCallback;

/**
 * <p>Starts an asynchronous FFprobe execution with arguments provided.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete.
 * You must use an FFprobeSessionCompleteCallback if you want to be notified about the result.
 *
 * @param arguments        FFprobe command options/arguments as string array
 * @param completeCallback callback that will be notified when execution has completed
 * @param logCallback      callback that will receive logs
 * @return FFprobe session created for this execution
 */
+ (FFprobeSession*)executeWithArgumentsAsync:(NSArray*)arguments withCompleteCallback:(FFprobeSessionCompleteCallback)completeCallback withLogCallback:(LogCallback)logCallback;

/**
 * <p>Starts an asynchronous FFprobe execution with arguments provided.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete.
 * You must use an FFprobeSessionCompleteCallback if you want to be notified about the result.
 *
 * @param arguments        FFprobe command options/arguments as string array
 * @param completeCallback callback that will be called when the execution has completed
 * @param queue            dispatch queue that will be used to run this asynchronous operation
 * @return FFprobe session created for this execution
 */
+ (FFprobeSession*)executeWithArgumentsAsync:(NSArray*)arguments withCompleteCallback:(FFprobeSessionCompleteCallback)completeCallback onDispatchQueue:(dispatch_queue_t)queue;

/**
 * <p>Starts an asynchronous FFprobe execution with arguments provided.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete.
 * You must use an FFprobeSessionCompleteCallback if you want to be notified about the result.
 *
 * @param arguments        FFprobe command options/arguments as string array
 * @param completeCallback callback that will be notified when execution has completed
 * @param logCallback      callback that will receive logs
 * @param queue            dispatch queue that will be used to run this asynchronous operation
 * @return FFprobe session created for this execution
 */
+ (FFprobeSession*)executeWithArgumentsAsync:(NSArray*)arguments withCompleteCallback:(FFprobeSessionCompleteCallback)completeCallback withLogCallback:(LogCallback)logCallback onDispatchQueue:(dispatch_queue_t)queue;

/**
 * <p>Synchronously executes FFprobe command provided. Space character is used to split command
 * into arguments. You can use single or double quote characters to specify arguments inside
 * your command.
 *
 * @param command FFprobe command
 * @return FFprobe session created for this execution
 */
+ (FFprobeSession*)execute:(NSString*)command;

/**
 * <p>Starts an asynchronous FFprobe execution for the given command. Space character is used to split the command
 * into arguments. You can use single or double quote characters to specify arguments inside your command.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete. You must use an
 * FFprobeSessionCompleteCallback if you want to be notified about the result.
 *
 * @param command          FFprobe command
 * @param completeCallback callback that will be called when the execution has completed
 * @return FFprobe session created for this execution
 */
+ (FFprobeSession*)executeAsync:(NSString*)command withCompleteCallback:(FFprobeSessionCompleteCallback)completeCallback;

/**
 * <p>Starts an asynchronous FFprobe execution for the given command. Space character is used to split the command
 * into arguments. You can use single or double quote characters to specify arguments inside your command.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete. You must use an
 * FFprobeSessionCompleteCallback if you want to be notified about the result.
 *
 * @param command          FFprobe command
 * @param completeCallback callback that will be notified when execution has completed
 * @param logCallback      callback that will receive logs
 * @return FFprobe session created for this execution
 */
+ (FFprobeSession*)executeAsync:(NSString*)command withCompleteCallback:(FFprobeSessionCompleteCallback)completeCallback withLogCallback:(LogCallback)logCallback;

/**
 * <p>Starts an asynchronous FFprobe execution for the given command. Space character is used to split the command
 * into arguments. You can use single or double quote characters to specify arguments inside your command.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete. You must use an
 * FFprobeSessionCompleteCallback if you want to be notified about the result.
 *
 * @param command          FFprobe command
 * @param completeCallback callback that will be called when the execution has completed
 * @param queue            dispatch queue that will be used to run this asynchronous operation
 * @return FFprobe session created for this execution
 */
+ (FFprobeSession*)executeAsync:(NSString*)command withCompleteCallback:(FFprobeSessionCompleteCallback)completeCallback onDispatchQueue:(dispatch_queue_t)queue;

/**
 * <p>Starts an asynchronous FFprobe execution for the given command. Space character is used to split the command
 * into arguments. You can use single or double quote characters to specify arguments inside your command.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete. You must use an
 * FFprobeSessionCompleteCallback if you want to be notified about the result.
 *
 * @param command          FFprobe command
 * @param completeCallback callback that will be called when the execution has completed
 * @param logCallback      callback that will receive logs
 * @param queue            dispatch queue that will be used to run this asynchronous operation
 * @return FFprobe session created for this execution
 */
+ (FFprobeSession*)executeAsync:(NSString*)command withCompleteCallback:(FFprobeSessionCompleteCallback)completeCallback withLogCallback:(LogCallback)logCallback onDispatchQueue:(dispatch_queue_t)queue;

/**
 * <p>Extracts media information for the file specified with path.
 *
 * @param path path or uri of a media file
 * @return media information session created for this execution
 */
+ (MediaInformationSession*)getMediaInformation:(NSString*)path;

/**
 * <p>Extracts media information for the file specified with path.
 *
 * @param path        path or uri of a media file
 * @param waitTimeout max time to wait until media information is transmitted
 * @return media information session created for this execution
 */
+ (MediaInformationSession*)getMediaInformation:(NSString*)path withTimeout:(int)waitTimeout;

/**
 * <p>Starts an asynchronous FFprobe execution to extract the media information for the specified file.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete. You must use an
 * MediaInformationSessionCompleteCallback if you want to be notified about the result.
 *
 * @param path             path or uri of a media file
 * @param completeCallback callback that will be called when the execution has completed
 * @return media information session created for this execution
 */
+ (MediaInformationSession*)getMediaInformationAsync:(NSString*)path withCompleteCallback:(MediaInformationSessionCompleteCallback)completeCallback;

/**
 * <p>Starts an asynchronous FFprobe execution to extract the media information for the specified file.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete. You must use an
 * MediaInformationSessionCompleteCallback if you want to be notified about the result.
 *
 * @param path             path or uri of a media file
 * @param completeCallback callback that will be notified when execution has completed
 * @param logCallback      callback that will receive logs
 * @param waitTimeout      max time to wait until media information is transmitted
 * @return media information session created for this execution
 */
+ (MediaInformationSession*)getMediaInformationAsync:(NSString*)path withCompleteCallback:(MediaInformationSessionCompleteCallback)completeCallback withLogCallback:(LogCallback)logCallback withTimeout:(int)waitTimeout;

/**
 * <p>Starts an asynchronous FFprobe execution to extract the media information for the specified file.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete. You must use an
 * MediaInformationSessionCompleteCallback if you want to be notified about the result.
 *
 * @param path             path or uri of a media file
 * @param completeCallback callback that will be called when the execution has completed
 * @param queue            dispatch queue that will be used to run this asynchronous operation
 * @return media information session created for this execution
 */
+ (MediaInformationSession*)getMediaInformationAsync:(NSString*)path withCompleteCallback:(MediaInformationSessionCompleteCallback)completeCallback onDispatchQueue:(dispatch_queue_t)queue;

/**
 * <p>Starts an asynchronous FFprobe execution to extract the media information for the specified file.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete. You must use an
 * MediaInformationSessionCompleteCallback if you want to be notified about the result.
 *
 * @param path             path or uri of a media file
 * @param completeCallback callback that will be notified when execution has completed
 * @param logCallback      callback that will receive logs
 * @param queue            dispatch queue that will be used to run this asynchronous operation
 * @param waitTimeout      max time to wait until media information is transmitted
 * @return media information session created for this execution
 */
+ (MediaInformationSession*)getMediaInformationAsync:(NSString*)path withCompleteCallback:(MediaInformationSessionCompleteCallback)completeCallback withLogCallback:(LogCallback)logCallback onDispatchQueue:(dispatch_queue_t)queue withTimeout:(int)waitTimeout;

/**
 * <p>Extracts media information using the command provided asynchronously.
 *
 * @param command FFprobe command that prints media information for a file in JSON format
 * @return media information session created for this execution
 */
+ (MediaInformationSession*)getMediaInformationFromCommand:(NSString*)command;

/**
 * <p>Starts an asynchronous FFprobe execution to extract media information using a command. The command passed to
 * this method must generate the output in JSON format in order to successfully extract media information from it.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete. You must use an
 * MediaInformationSessionCompleteCallback if you want to be notified about the result.
 *
 * @param command          FFprobe command that prints media information for a file in JSON format
 * @param completeCallback callback that will be notified when execution has completed
 * @param logCallback      callback that will receive logs
 * @param queue            dispatch queue that will be used to run this asynchronous operation
 * @param waitTimeout      max time to wait until media information is transmitted
 * @return media information session created for this execution
 */
+ (MediaInformationSession*)getMediaInformationFromCommandAsync:(NSString*)command withCompleteCallback:(MediaInformationSessionCompleteCallback)completeCallback withLogCallback:(LogCallback)logCallback onDispatchQueue:(dispatch_queue_t)queue withTimeout:(int)waitTimeout;

/**
 * <p>Starts an asynchronous FFprobe execution to extract media information using command arguments. The command
 * passed to this method must generate the output in JSON format in order to successfully extract media information
 * from it.
 *
 * <p>Note that this method returns immediately and does not wait the execution to complete. You must use an
 * MediaInformationSessionCompleteCallback if you want to be notified about the result.
 *
 * @param arguments        FFprobe command that prints media information for a file in JSON format
 * @param completeCallback callback that will be notified when execution has completed
 * @param logCallback      callback that will receive logs
 * @param queue            dispatch queue that will be used to run this asynchronous operation
 * @param waitTimeout      max time to wait until media information is transmitted
 * @return media information session created for this execution
 */
+ (MediaInformationSession*)getMediaInformationFromCommandArgumentsAsync:(NSArray*)arguments withCompleteCallback:(MediaInformationSessionCompleteCallback)completeCallback withLogCallback:(LogCallback)logCallback onDispatchQueue:(dispatch_queue_t)queue withTimeout:(int)waitTimeout;

/**
 * <p>Lists all FFprobe sessions in the session history.
 *
 * @return all FFprobe sessions in the session history
 */
+ (NSArray*)listFFprobeSessions;

/**
 * <p>Lists all MediaInformation sessions in the session history.
 *
 * @return all MediaInformation sessions in the session history
 */
+ (NSArray*)listMediaInformationSessions;

@end

#endif // FFPROBE_KIT_H
