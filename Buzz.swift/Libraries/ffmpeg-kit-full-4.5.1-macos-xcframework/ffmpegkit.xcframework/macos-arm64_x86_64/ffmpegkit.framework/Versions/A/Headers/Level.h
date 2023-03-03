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

#ifndef FFMPEG_KIT_LEVEL_H
#define FFMPEG_KIT_LEVEL_H

/**
 * <p>Enumeration type for log levels.
 */
typedef NS_ENUM(NSUInteger, Level) {
    
    /**
     * This log level is defined by FFmpegKit. It is used to specify logs printed to stderr by
     * FFmpeg. Logs that has this level are not filtered and always redirected.
     */
    LevelAVLogStdErr = -16,

    /**
     * Print no output.
     */
    LevelAVLogQuiet = -8,

    /**
     * Something went really wrong and we will crash now.
     */
    LevelAVLogPanic = 0,

    /**
     * Something went wrong and recovery is not possible.
     * For example, no header was found for a format which depends
     * on headers or an illegal combination of parameters is used.
     */
    LevelAVLogFatal = 8,

    /**
     * Something went wrong and cannot losslessly be recovered.
     * However, not all future data is affected.
     */
    LevelAVLogError = 16,

    /**
     * Something somehow does not look correct. This may or may not
     * lead to problems. An example would be the use of '-vstrict -2'.
     */
    LevelAVLogWarning = 24,

    /**
     * Standard information.
     */
    LevelAVLogInfo = 32,

    /**
     * Detailed information.
     */
    LevelAVLogVerbose = 40,

    /**
     * Stuff which is only useful for libav* developers.
     */
    LevelAVLogDebug = 48,
    
    /**
     * Extremely verbose debugging, useful for libav* development.
     */
    LevelAVLogTrace = 56

};

#endif // FFMPEG_KIT_LEVEL_H
