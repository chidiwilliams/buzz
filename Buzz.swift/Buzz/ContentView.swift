//
//  ContentView.swift
//  Buzz
//
//  Created by Chidi Williams on 29/01/2023.
//

import SwiftUI
import AVFoundation

struct ContentView: View {
    @State private var isRecordingOptionsSheetPresented = false
    @State private var isFileTranscriptionOptionsSheetPresented = false
    @Environment(\.openWindow) private var openWindow
    @State var recordingOptions = RecordingTranscriptionOptions()
    @State var recordingAction: SheetAction = .none
    @State var fileTranscriptionAction: SheetAction = .none
    @State var isRecording = false
    @State var recorder: AudioRecorder? = nil
    @State var transcriptionWindow: NSWindow? = nil
    @State var line = ""
    @State var transcriber: RecordingTranscriber?
    @State var currentRecordingTranscription: Transcription?
    @StateObject private var transcriptionStore = TranscriptionStore()
    @State var selectedTranscription: Transcription? = nil
    @StateObject var fileTranscriptionOptions = FileTranscriptionOptions(file: URL(filePath: ""))
    
    private func saveTranscriptions() {
        TranscriptionStore.save(transcriptions: transcriptionStore.transcriptions) { result in
            if case .failure(let failure) = result {
                fatalError(failure.localizedDescription)
            }
        }
    }
    
    private func onDismissFileTranscriptionSheet() {
        if fileTranscriptionAction == .success {
            let transcriber = FileTranscriber(transcriptionOptions: self.fileTranscriptionOptions)
            let transcription = transcriber.transcribe()
            transcriptionStore.transcriptions.append(transcription)
            selectedTranscription = transcription
        }
    }
    
    private func onDismissRecordingSheet() {
        if recordingAction == .success {
            //            reset line
            line = ""
            
            //            TODO: can this be a view model instead?
            let transcriber = RecordingTranscriber(options: recordingOptions)
            currentRecordingTranscription = Transcription(title: "New Recording")
            transcriber.start() { segment in
                DispatchQueue.main.async {
                    line = segment.text
                    currentRecordingTranscription?.segments.insert(segment, at: 0)
                }
            }
            self.transcriber = transcriber
            
            
            let width = 500
            let height = 75
            var x: Int
            if let screen = NSScreen.main {
                x = Int(screen.frame.midX) - width / 2
            } else {
                x = 0
            }
            let y = height
            
            transcriptionWindow = NSWindow(
                contentRect: NSRect(x: x, y: y, width: width, height: height),
                styleMask: [.fullSizeContentView, .resizable], backing: .buffered, defer: false
            )
            transcriptionWindow?.contentView = NSHostingView(rootView: FloatingTranscriptionView(line: $line))
            transcriptionWindow?.setContentSize(NSSize(width: width, height: height))
            transcriptionWindow?.level = .screenSaver
            transcriptionWindow?.backgroundColor = .clear
            transcriptionWindow?.isMovableByWindowBackground = true
            transcriptionWindow?.makeKeyAndOrderFront(nil)
            
            isRecording = true
            // reset recording action state
            recordingAction = .none
        }
    }
    
    private func onClickRecord() {
        if isRecording {
            isRecording = false
            
            transcriber?.stop()
            currentRecordingTranscription?.timeEnded = .now
            
            transcriptionWindow?.resignKey()
            transcriptionWindow?.close()
            
            transcriptionStore.transcriptions.append(self.currentRecordingTranscription!)
        } else {
            isRecordingOptionsSheetPresented = true
        }
    }
    
    private func onClickImport() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.allowedContentTypes = [.audiovisualContent]
        guard panel.runModal() == .OK else {
            return
        }
        
        guard let url = panel.url else {
            return
        }
        
        fileTranscriptionOptions.file = url
        isFileTranscriptionOptionsSheetPresented = true
    }
    
    var body: some View {
        NavigationSplitView(sidebar: {
            List(transcriptionStore.transcriptions.sorted(by: { $0.timeStarted > $1.timeStarted }), id: \.self, selection: $selectedTranscription) { transcription in
                TranscriptionListRowContentView(transcription: transcription)
                    .padding(.vertical, 8)
                    .padding(.horizontal, 12)
            }
        }, detail: {
            if let transcription = selectedTranscription {
                TranscriptionView(transcription: transcription)
            }
        })
        .toolbar() {
            Button(action: onClickRecord) {
                Image(systemName: isRecording ?
                      "stop.circle" : "record.circle")
                Text(isRecording ? "Stop" : "Record")
            }
            .help(isRecording ? "Stop" : "Record")
            .sheet(isPresented: $isRecordingOptionsSheetPresented, onDismiss: onDismissRecordingSheet) {
                RecordingTranscriptionOptionsView(recordingAction: $recordingAction, options: recordingOptions)
                    .frame(width: 360)
            }
            
            Button(action: onClickImport) {
                Image(systemName: "square.and.arrow.down")
                Text("Import")
            }
            .help("Import")
            .sheet(isPresented: $isFileTranscriptionOptionsSheetPresented, onDismiss: onDismissFileTranscriptionSheet) {
                FileTranscriptionOptionsView(
                    options: fileTranscriptionOptions,
                    action: $fileTranscriptionAction
                )
                .frame(width: 360)
            }
            
            if let transcription = selectedTranscription {
                Menu(content: {
                    ForEach(ExportFormat.allCases, id: \.rawValue) { exportFormat in
                        Button(exportFormat.rawValue) {
                            TranscriptionExporter.export(transcription: transcription, format: exportFormat)
                        }
                    }
                }, label: {
                    Image(systemName: "square.and.arrow.up")
                    Text("Export")
                })
            }
        }
        .onAppear() {
            TranscriptionStore.load() { result in
                switch result {
                case .failure(let error):
                    fatalError(error.localizedDescription)
                case .success(let transcriptions):
                    transcriptionStore.transcriptions = transcriptions
                    selectedTranscription = transcriptions.first
                }
            }
        }
        .onReceive(
            NotificationCenter.default.publisher(for: NSApplication.willResignActiveNotification),
            perform: { _ in saveTranscriptions() })
        
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView(
        )
    }
}
