//
//  TranscriptionListRowContentView.swift
//  Buzz
//
//  Created by Chidi Williams on 20/02/2023.
//

import Foundation
import SwiftUI

struct TranscriptionListRowContentView: View {
    @ObservedObject var transcription: Transcription
    
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(transcription.title)")
                .bold()
            Text("\(transcription.timeEnded?.formatted() ?? transcription.timeStarted.formatted())")
                .font(.caption)
            
            if transcription.isInProgressFileTranscription() {
                ProgressView()
                    .progressViewStyle(.linear)
            }
        }
    }
}

struct TranscriptionListRowContentView_Previews: PreviewProvider {
    static var previews: some View {
        TranscriptionListRowContentView(transcription: {
            Transcription(title: "Transcription", segments: [
            
            ])
        }())
    }
}
