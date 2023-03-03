//
//  TranscriptionExporter.swift
//  Buzz
//
//  Created by Chidi Williams on 18/02/2023.
//

import Foundation
import AppKit

class TranscriptionExporter {
    private static let exportNameDateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "dd-MMM-yyyy HH-mm-ss" // 27-Dec-2022 14:11:54
        return formatter
    }()
    
    static func export(transcription: Transcription, format: ExportFormat) {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.utf8PlainText]
        panel.nameFieldStringValue = getDefaultExportFilename(transcription: transcription, format: format)
        guard panel.runModal() == .OK else {
            return
        }
        
        guard let url = panel.url else {
            return
        }
        
        var output = ""
        
        switch (format) {
        case .TXT:
            for (index, segment) in transcription.segments.enumerated() {
                output = output.appending(segment.text)
                if index < transcription.segments.count - 1 {
                    output = output.appending(" ")
                }
            }
            output = output.appending("\n")
        case .SRT:
            for (index, segment) in transcription.segments.enumerated() {
                guard let startMS = segment.startMS else {
                    return
                }
                guard let endMS = segment.endMS else {
                    return
                }
                output = output
                    .appending("\(index + 1)\n")
                    .appending("\(toTimestamp(ms: startMS, ms_separator: ",")) --> \(toTimestamp(ms: endMS, ms_separator: ","))\n")
                    .appending("\(segment.text)\n\n")
            }
        case .VTT:
            output = output.appending("WEBVTT\n\n")
            transcription.segments.forEach() { segment in
                guard let startMS = segment.startMS else {
                    return
                }
                guard let endMS = segment.endMS else {
                    return
                }
                output = output
                    .appending("\(toTimestamp(ms: startMS)) --> \(toTimestamp(ms: endMS))\n")
                    .appending("\(segment.text)\n\n")
            }
        }
        
        do {
            try output.write(to: url, atomically: true, encoding: .utf8)
            NSWorkspace.shared.activateFileViewerSelecting([url])
        } catch {
            print("Failed to write output to file: \(error)")
        }
    }
    
    private static func getDefaultExportFilename(transcription: Transcription, format: ExportFormat) -> String {
        return "\(transcription.title) (Transcribed on \(exportNameDateFormatter.string(from: .now)).\(format.rawValue.lowercased())"
    }
}
