//
//  LiveRecordingView.swift
//  Buzz
//
//  Created by Chidi Williams on 04/02/2023.
//

import Foundation
import SwiftUI
import AVFoundation
import whisper

struct RecordingTranscriptionOptionsView: View {
    @Binding var recordingAction: SheetAction
    @ObservedObject var options = RecordingTranscriptionOptions()
    
    @State private var microphones: [AVCaptureDevice] = []
    
    @Environment(\.dismiss) var dismiss
    
    //        TODO: Add visualizer from https://medium.com/swlh/swiftui-create-a-sound-visualizer-cadee0b6ad37
    
    var body: some View {
        Form {
            Section(header: Text("Transcription").bold()) {
                TranscriptionOptionsView(options: options)
            }
            Spacer().frame(height: 24)
            Section(header: Text("Audio").bold()) {
                Picker("Microphone", selection: $options.microphone) {
                    ForEach(microphones, id: \.uniqueID) { microphone in
                        Text(microphone.localizedName).tag(microphone as AVCaptureDevice?)
                    }
                }
            }
            Spacer().frame(height: 24)
            Button("Record") {
                recordingAction = .success
                dismiss()
            }.keyboardShortcut(.defaultAction)
        }
        .padding(24)
        .onAppear() {
            let audioSession = AVCaptureDevice.DiscoverySession(deviceTypes: [.builtInMicrophone], mediaType: .audio, position: .unspecified)
            microphones = audioSession.devices
            options.microphone = (AVCaptureDevice.default(for: .audio) ?? microphones.first)
        }
    }
}

struct RecordingOptionsView_Previews: PreviewProvider {
    @State private var recordingOptions = RecordingTranscriptionOptions()
    @State private var recordingAction = SheetAction.none
    
    static var previews: some View {
        RecordingTranscriptionOptionsView(recordingAction: Binding(get: {SheetAction.none}, set: {_,_ in}))
    }
}
