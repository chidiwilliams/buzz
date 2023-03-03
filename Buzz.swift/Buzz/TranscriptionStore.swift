//
//  TranscriptionStore.swift
//  Buzz
//
//  Created by Chidi Williams on 17/02/2023.
//

import Foundation

class TranscriptionStore: ObservableObject {
    private enum TranscriptionType: Codable, Hashable, Identifiable {
        var id: String { UUID().uuidString }
        
        case transcription(Transcription)
        case file(FileTranscription)
        
        
        func unwrap() -> Transcription {
            switch self {
            case .transcription(let recording):
                return recording
            case .file(let fileTranscription):
                return fileTranscription
            }
        }
    }
    
    @Published var transcriptions: [Transcription] = []
    
    private static func getFileURL() -> URL {
        try! FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: false)
            .appending(path: "Buzz")
            .appendingPathComponent("transcriptions.data")
    }
    
    static func load(completion: @escaping (Result<[Transcription], Error>) -> Void) {
        DispatchQueue.global(qos: .background).async {
            let fileURL = getFileURL()
            guard let file = try? FileHandle(forReadingFrom: fileURL) else {
                DispatchQueue.main.async {
                    completion(.success([]))
                }
                return
            }
            
            guard let transcriptions = try? JSONDecoder().decode([TranscriptionType].self, from: file.availableData) else {
                try? FileManager.default.removeItem(at: fileURL)
                DispatchQueue.main.async {
                    completion(.success([]))
                }
                return
            }
            DispatchQueue.main.async {
                completion(.success(transcriptions.map({ $0.unwrap() })))
            }
        }
    }
    
    private static func wrap(transcription: Transcription) -> TranscriptionType {
        if let transcription = transcription as? FileTranscription {
            return .file(transcription)
        }
        return .transcription(transcription)
    }
    
    static func save(transcriptions: [Transcription], completion: @escaping (Result<Int, Error>) -> Void) {
        DispatchQueue.global(qos: .background).async {
            do {
                let data = try JSONEncoder().encode(transcriptions.map(wrap))
                
                let outFile = getFileURL()
                
                try FileManager.default.createDirectory(at: outFile.deletingLastPathComponent(), withIntermediateDirectories: true)
                
                try data.write(to: outFile)
                DispatchQueue.main.async {
                    completion(.success(transcriptions.count))
                }
            } catch {
                DispatchQueue.main.async {
                    completion(.failure(error))
                }
            }
        }
    }
}
