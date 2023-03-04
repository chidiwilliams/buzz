//
//  TranscriptionView.swift
//  Buzz
//
//  Created by Chidi Williams on 06/02/2023.
//

import Foundation
import SwiftUI

func toTimestamp(ms: Int, ms_separator: String = ".") -> String {
    var _ms = ms
    let hr = _ms / (1000 * 60 * 60)
    _ms = _ms - hr * 1000 * 60 * 60
    let min = _ms / (1000 * 60)
    _ms = _ms - min * 1000 * 60
    let sec = _ms / 1000
    _ms = _ms - sec * 1000
    return "\(String(format: "%02d", hr)):\(String(format: "%02d", min)):\(String(format: "%02d", sec))\(ms_separator)\(String(format: "%03d", _ms))"
}

extension Transcription {
    func isInProgressFileTranscription() -> Bool {
        if let transcription = self as? FileTranscription {
            switch transcription.status {
            case .inProgress(let progress):
                return progress.current != progress.total
            case .completed:
                return false
            }
        }
        return false
    }
}

struct TranscriptionView: View {
    @ObservedObject var transcription: Transcription
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading) {
                Text("Started: \(transcription.timeStarted.formatted())")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.top, 16)
                Text(transcription.title)
                    .bold()
                    .font(.title)
                    .padding(.vertical, 24)
                
                if transcription.isInProgressFileTranscription() {
                    ProgressView()
                } else {
                    ForEach(transcription.segments, id: \.self) { segment in
                        VStack(alignment: .leading) {
                            if let startMS = segment.startMS {
                                if let endMS = segment.endMS {
                                    Text("\(toTimestamp(ms:startMS)) → \(toTimestamp(ms:endMS))")
                                        .font(.caption2)
                                        .padding(.bottom, 1)
                                        .foregroundColor(.secondary)
                                }
                            }
                            Text(segment.text)
                        }
                        .padding(.bottom, 24)
                    }
                }
            }
            .frame(maxWidth: .infinity)
            .textSelection(.enabled)
        }
        .padding()
        .frame(minWidth: 200)
        .toolbar() {
        }
    }
}

struct TranscriptionView_Previews: PreviewProvider {
    private static var recordingTranscription: Transcription = {
        Transcription(title: "Test", segments: [
            Segment(
                startMS: 0,
                endMS: 2780,
                text: "Without education, we are in a horrible and deadly danger of taking educated people seriously."
            ),
            Segment(
                startMS: 2781,
                endMS: 5382,
                text: "To love means loving the unlovable. To forgive means pardoning the unpardonable. Faith means believing the unbelievable. Hope means hoping when everything seems hopeless."
            )
        ])
    }()
    
    private static var inProgressFileTranscription: FileTranscription = {
        FileTranscription(file: URL(filePath: ""))
    }()
    
    static var previews: some View {
        TranscriptionView(transcription: recordingTranscription)
            .previewDisplayName("Recording Transcription")
        TranscriptionView(transcription: inProgressFileTranscription)
            .previewDisplayName("File Transcription - In Progress")
    }
}
