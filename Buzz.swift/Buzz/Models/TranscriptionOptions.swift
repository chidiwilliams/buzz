//
//  TranscriptionOptions.swift
//  Buzz
//
//  Created by Chidi Williams on 19/02/2023.
//

import Foundation
import AVFoundation

class TranscriptionOptions: ObservableObject {
    @Published var model: WhisperModel = .tiny
    @Published var task: WhisperTask = .transcribe
    @Published var language: WhisperLanguage = .en
}

class FileTranscriptionOptions: TranscriptionOptions {
    @Published var file: URL
    
    init(file: URL) {
        self.file = file
    }
}

class RecordingTranscriptionOptions: TranscriptionOptions {
    @Published var microphone: AVCaptureDevice? = nil
}

