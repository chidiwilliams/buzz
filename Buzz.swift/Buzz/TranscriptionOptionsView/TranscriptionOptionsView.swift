//
//  TranscriptionOptionsView.swift
//  Buzz
//
//  Created by Chidi Williams on 19/02/2023.
//

import Foundation

import Foundation
import SwiftUI

struct TranscriptionOptionsView: View {
    @ObservedObject var options: TranscriptionOptions
    @ObservedObject var downloadTask = ModelDownloadTask()
    
    private let fileByteCountFormatter: ByteCountFormatter = {
        let formatter = ByteCountFormatter()
        return formatter
    }()
    
    func formatByte(value: Float) -> String {
        fileByteCountFormatter.string(fromByteCount: Int64(value))
    }
    
    var body: some View {
        Picker("Task:", selection: $options.task) {
            ForEach(WhisperTask.allCases, id: \.rawValue) { task in
                Text(task.rawValue.capitalized).tag(task)
            }
        }.pickerStyle(.radioGroup).horizontalRadioGroupLayout()
        HStack {
            Picker("Model:", selection: $options.model) {
                ForEach(WhisperModel.allCases, id: \.rawValue) { model in
                    Text(model.displayName).tag(model)
                }
            }
            
            Spacer()
            
            if ModelLoader.isAvailable(model: options.model) {
                Image(systemName: "checkmark.circle.fill")
                    .help("Downloaded")
            }
            
            if !ModelLoader.isAvailable(model: options.model) {
                if downloadTask.isDownloading {
                    CircularProgressView(current: $downloadTask.bytesWritten, total: $downloadTask.bytesExpected) {
                        downloadTask.cancel()
                    }
                    .help("\(formatByte(value: downloadTask.bytesWritten)) downloaded of \(formatByte(value: downloadTask.bytesExpected))")
                } else {
                    Button(action: {
                        downloadTask.start(model: options.model)
                    }) {
                        Image(systemName: "icloud.and.arrow.down.fill")
                    }
                    .help("Download model (\(formatByte(value: Float(ModelLoader.getModelByteSize(model: options.model)))))")
                }
            }
        }
        Picker("Language:", selection: $options.language) {
            ForEach(WhisperLanguage.allCases.sorted(by: { $0.fullName < $1.fullName }), id: \.rawValue) { language in
                Text(language.fullName).tag(language)
            }
        }
    }
}

struct TranscriptionOptionsView_Previews: PreviewProvider {
    private static var options = TranscriptionOptions()
    
    static var previews: some View {
        TranscriptionOptionsView(options: options)
    }
}
