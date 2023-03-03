//
//  Transcription.swift
//  Buzz
//
//  Created by Chidi Williams on 17/02/2023.
//

import Foundation

class Transcription: ObservableObject, Hashable, Identifiable, Codable {
    @Published var id = UUID()
    @Published var title: String
    @Published var timeStarted: Date = Date.now
    @Published var timeEnded: Date?
    @Published var segments: [Segment]
    
    private enum CodingKeys: String, CodingKey {
        case id, title, timeStarted, timeEnded, segments
    }
    
    init(title: String, segments: [Segment] = []) {
        self.segments = segments
        self.title = title
    }
    
    static func ==(lhs: Transcription, rhs: Transcription) -> Bool {
        return lhs.id == rhs.id
        && lhs.title == rhs.title
        && lhs.timeStarted == rhs.timeStarted
        && lhs.segments == rhs.segments
    }
    
    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
        hasher.combine(title)
        hasher.combine(timeStarted)
        hasher.combine(segments)
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(title, forKey: .title)
        try container.encode(timeStarted, forKey: .timeStarted)
        try container.encode(timeEnded, forKey: .timeEnded)
        try container.encode(segments, forKey: .segments)
    }
    
    required init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(UUID.self, forKey: .id)
        title = try values.decode(String.self, forKey: .title)
        timeStarted = try values.decode(Date.self, forKey: .timeStarted)
        timeEnded = try values.decode(Date?.self, forKey: .timeEnded)
        segments = try values.decode([Segment].self, forKey: .segments)
    }
}

struct Segment: Equatable, Hashable, Codable, Identifiable {
    var id = UUID()
    var startMS: Int?
    var endMS: Int?
    let text: String
}
