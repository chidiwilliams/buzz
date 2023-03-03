//
//  FileTranscription.swift
//  Buzz
//
//  Created by Chidi Williams on 20/02/2023.
//

import Foundation

class FileTranscription: Transcription {
    @Published var file: URL
    @Published var status: Status = .inProgress(Status.Progress())
    
    enum Status: Codable, Equatable, Hashable {
        struct Progress: Codable, Equatable, Hashable {
            var current = 0.0
            var total = 100.0
        }
        
        case inProgress(Progress), completed
    }
    
    private enum CodingKeys: String, CodingKey {
        case file, status
    }
    
    init(file: URL) {
        self.file = file
        super.init(title: file.lastPathComponent)
    }
    
    static func ==(lhs: FileTranscription, rhs: FileTranscription) -> Bool {
        return lhs.file == rhs.file && lhs.status == rhs.status && (lhs as Transcription) == (rhs as Transcription)
    }
    
    override func hash(into hasher: inout Hasher) {
        hasher.combine(file)
        hasher.combine(status)
        super.hash(into: &hasher)
    }
    
    required init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        file = try values.decode(URL.self, forKey: .file)
        status = try values.decode(Status.self, forKey: .status)
        try super.init(from: decoder)
    }
    
    override func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(file, forKey: .file)
        try container.encode(status, forKey: .status)
        try super.encode(to: encoder)
    }
}

