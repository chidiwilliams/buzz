//
//  FileTranscriptionOptionsView.swift
//  Buzz
//
//  Created by Chidi Williams on 19/02/2023.
//

import Foundation
import SwiftUI

struct FileTranscriptionOptionsView: View {
    @ObservedObject var options: TranscriptionOptions
    
    @Binding var action: SheetAction
    
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        Form {
            Section(header: Text("Transcription").bold()) {
                TranscriptionOptionsView(options: options)
            }
            Spacer().frame(height: 24)
            Button("Run") {
                action = .success
                dismiss()
            }.keyboardShortcut(.defaultAction)
        }
        .padding(24)
    }
}

struct FileTranscriptionOptionsView_Previews: PreviewProvider {
    private static var transcriptionOptions = TranscriptionOptions()
    private static var action: SheetAction = .none
    
    static var previews: some View {
        FileTranscriptionOptionsView(
            options: transcriptionOptions, action: Binding(get: {action}, set: {_,_ in}))
    }
}
