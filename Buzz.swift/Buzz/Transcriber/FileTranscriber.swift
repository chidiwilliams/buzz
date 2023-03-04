//
//  FileTranscriber.swift
//  Buzz
//
//  Created by Chidi Williams on 06/02/2023.
//

import Foundation
import whisper
import ffmpegkit
import AVFoundation

class FileTranscriber {
    let transcriptionOptions: FileTranscriptionOptions
    
    private let transcriptionQueue = DispatchQueue(label: "transcription.file", qos: DispatchQoS.userInitiated)
    private var isRunning = false
    private let SAMPLE_RATE = WHISPER_SAMPLE_RATE
    
    init(transcriptionOptions: FileTranscriptionOptions) {
        self.transcriptionOptions = transcriptionOptions
    }
    
    func fileToBuffer(wavFile: URL) throws -> AVAudioPCMBuffer {
        let wavAudioFile = try AVAudioFile(forReading: wavFile)
        let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: wavAudioFile.fileFormat.sampleRate, channels: wavAudioFile.fileFormat.channelCount, interleaved: false)!
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: UInt32(wavAudioFile.length))!
        try wavAudioFile.read(into: buffer)
        return buffer
    }
    
    func transcribe() -> FileTranscription {
        let filePath = self.transcriptionOptions.file
        
        let transcription = FileTranscription(file: filePath)
        
        transcriptionQueue.async {
            let wavFile = FileManager.default.temporaryDirectory
                .appendingPathComponent(UUID().uuidString)
                .appendingPathExtension("wav")
            
            guard let session = FFmpegKit.execute("""
                                                  -i "\(filePath.path(percentEncoded: false))" -ac 1 -acodec pcm_s16le -ar \(self.SAMPLE_RATE) "\(wavFile.path(percentEncoded: false))"
                                                  """) else {
                print("unable to create session")
                return
            }
            if (ReturnCode.isSuccess(session.getReturnCode())) {
                let buf = try! self.fileToBuffer(wavFile: wavFile)
                
                let modelPath: URL
                do {
                    modelPath = try ModelLoader.getModelPath(model: self.transcriptionOptions.model)
                } catch {
                    fatalError(error.localizedDescription)
                }
                
                let ctx = whisper_init_from_file(modelPath.path(percentEncoded: false))
                
                self.isRunning = true
                
                withUnsafeMutablePointer(to: &self.isRunning, {isRunning in
                    var params = whisper_full_default_params(WHISPER_SAMPLING_GREEDY)
                    params.print_realtime   = true
                    params.print_progress   = false
                    params.print_timestamps = false
                    params.print_special    = false
                    params.translate        = self.transcriptionOptions.task == .translate
                    params.language         = NSString(string: self.transcriptionOptions.language.rawValue).utf8String
                    params.n_threads        = 4
                    params.offset_ms        = 0
                    params.encoder_begin_callback_user_data = UnsafeMutableRawPointer(mutating: isRunning)
                    params.encoder_begin_callback = { _, userData in
                        return userData?.load(as: Bool.self) ?? true
                    }
                    
                    let ret = whisper_full(ctx, params, buf.floatChannelData?.pointee, Int32(buf.frameLength))
                    assert(ret == 0, "Failed to run the model")
                    
                    let n_segments = whisper_full_n_segments(ctx)
                    
                    for i in 0..<n_segments {
                        let t0 = whisper_full_get_segment_t0(ctx, i)
                        let t1 = whisper_full_get_segment_t1(ctx, i)
                        
                        if let segment_text = whisper_full_get_segment_text(ctx, i) {
                            if let ns_string = NSString(utf8String: segment_text) {
                                DispatchQueue.main.async {
                                    transcription.segments.append(
                                        Segment(startMS: Int(t0), endMS: Int(t1), text: String(ns_string).trimmingCharacters(in: .whitespaces))
                                    )
                                }
                            }
                        }
                    }
                    
                    whisper_print_timings(ctx)
                    whisper_free(ctx)
                })
                
                DispatchQueue.main.async {
                    transcription.status = .completed
                }
            }
        }
        
        return transcription
    }
    
    func stop()  {
        isRunning = true
    }
}
