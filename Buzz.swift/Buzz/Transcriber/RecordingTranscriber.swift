//
//  RecordingTranscriber.swift
//  Buzz
//
//  Created by Chidi Williams on 06/02/2023.
//

import Foundation
import whisper

class RecordingTranscriber {
    private let options: RecordingTranscriptionOptions
    private let recorder: AudioRecorder
    private var buffer: [Float] = []
    private var bufferSemaphore = DispatchSemaphore(value: 1)
    private let transcriptionQueue = DispatchQueue(label: "transcription.recording", qos: DispatchQoS.userInitiated)
    private var isRunning = false
    private static let SAMPLE_RATE = Int(WHISPER_SAMPLE_RATE)
    private static let STEP_SECS = 5
    private static let MAX_STEP_SIZE = RecordingTranscriber.STEP_SECS * RecordingTranscriber.SAMPLE_RATE
    private static let MAX_BACKLOG_SIZE = 2 * RecordingTranscriber.STEP_SECS * RecordingTranscriber.SAMPLE_RATE
    
    init(options: RecordingTranscriptionOptions) {
        self.options = options
        self.recorder = AudioRecorder(microphoneUniqueID: options.microphone?.uniqueID)
    }
    
    func start(callback: @escaping (Segment) -> Void) {
        recorder.record() { samples, sampleCount in
            self.bufferSemaphore.wait()
            if self.buffer.count < RecordingTranscriber.MAX_BACKLOG_SIZE {
                self.buffer.append(contentsOf: UnsafeBufferPointer(start: samples, count: sampleCount))
            }
            self.bufferSemaphore.signal()
        }
        
        let startTime = Date.now
        var lastSegmentStartTime = startTime
        
        transcriptionQueue.async {
            let modelPath: URL
            do {
                modelPath = try ModelLoader.getModelPath(model: self.options.model)
            } catch {
                fatalError(error.localizedDescription)
            }
            let ctx = whisper_init_from_file(modelPath.path(percentEncoded: false))
            
            var params: whisper_full_params = whisper_full_default_params(WHISPER_SAMPLING_GREEDY)
            params.print_realtime   = true
            params.print_progress   = false
            params.print_timestamps = false
            params.print_special    = false
            params.translate        = self.options.task == .translate
            params.language         = NSString(string: self.options.language.rawValue).utf8String
            params.n_threads        = 4
            params.offset_ms        = 0
            
            self.isRunning = true
            while self.isRunning {
                if self.buffer.count < RecordingTranscriber.MAX_STEP_SIZE {
                    continue
                }
                
                self.bufferSemaphore.wait()
                let step_size = min(self.buffer.count, RecordingTranscriber.MAX_STEP_SIZE)
                var next_step = Array(self.buffer[0..<step_size])
                self.buffer = Array(self.buffer[step_size..<self.buffer.count])
                self.bufferSemaphore.signal()
                
                let returnCode = whisper_full(ctx, params, &next_step, Int32(next_step.count))
                if returnCode != 0 {
                    print("whisper model return code \(returnCode), skipping...")
                    continue
                }
                
                var text = ""
                
                let n_segments = whisper_full_n_segments(ctx)
                for i in 0..<n_segments {
                    if let segment_text = whisper_full_get_segment_text(ctx, i) {
                        if let ns_string = NSString(utf8String: segment_text) {
                            text += String(ns_string)
                        }
                    }
                }
                
                text = text.trimmingCharacters(in: CharacterSet.whitespaces)
                
                let segmentEndTime = lastSegmentStartTime.addingTimeInterval(Double(step_size) / Double(RecordingTranscriber.SAMPLE_RATE))
                let segment = Segment(
                    startMS: Int(lastSegmentStartTime.timeIntervalSince(startTime)),
                    endMS: Int(segmentEndTime.timeIntervalSince(startTime)),
                    text: text)
                callback(segment)
                
                lastSegmentStartTime = segmentEndTime
            }
        }
    }
    
    func stop() {
        recorder.pause()
        isRunning = false
    }
}

