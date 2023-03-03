//
//  ModelLoader.swift
//  Buzz
//
//  Created by Chidi Williams on 08/02/2023.
//

import Foundation

class ModelLoader {
    static func isAvailable(model: WhisperModel) -> Bool {
        do {
            let modelPath = try getModelPath(model: model)
            return FileManager.default.fileExists(atPath: modelPath.path(percentEncoded: false))
        } catch {
            print(error)
            return false
        }
    }
    
    static func getModelPath(model: WhisperModel) throws -> URL  {
        return try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appending(path: "Buzz")
            .appending(path: "Models")
            .appendingPathComponent("ggml-whisper-\(model.id).bin")
    }
    
    static func getModelByteSize(model: WhisperModel) -> Int64 {
        switch model {
        case .tiny, .tiny_en:
            return 77_700_000
        case .base, .base_en:
            return 148_000_000
        case .small, .small_en:
            return 488_000_000
        case .medium, .medium_en:
            return 1_530_000_000
        case .large:
            return 3_090_000_000
        }
    }
    
    static func getModelDownloadURL(model: WhisperModel) -> URL? {
        return URL(string: "https://huggingface.co/datasets/ggerganov/whisper.cpp/resolve/main/ggml-\(model.id).bin")
    }
}
