//
//  TranscriptionViewer.swift
//  Buzz
//
//  Created by Chidi Williams on 05/02/2023.
//

import Foundation
import SwiftUI

struct VisualEffectView: NSViewRepresentable
{
    let material: NSVisualEffectView.Material
    let blendingMode: NSVisualEffectView.BlendingMode
    
    func makeNSView(context: Context) -> NSVisualEffectView
    {
        let visualEffectView = NSVisualEffectView()
        visualEffectView.material = material
        visualEffectView.blendingMode = blendingMode
        visualEffectView.state = NSVisualEffectView.State.active
        visualEffectView.wantsLayer = true
        visualEffectView.layer?.cornerRadius = 16.0
        visualEffectView.layer?.borderWidth = 0.0
        visualEffectView.layer?.borderColor = .clear
        return visualEffectView
    }
    
    func updateNSView(_ visualEffectView: NSVisualEffectView, context: Context)
    {
        visualEffectView.material = material
        visualEffectView.blendingMode = blendingMode
    }
}

struct FloatingTranscriptionView: View {
    @Binding var line: String
    
    var text: some View {
        Text(line)
            .padding()
            .font(.title3)
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
    }
    
    var body: some View {
        if line.isEmpty {
            text.background(.clear)
        } else {
            text.background(VisualEffectView(material: .fullScreenUI, blendingMode: .behindWindow))
        }
    }
}

struct FloatingTranscriptionView_Previews: PreviewProvider {
    @State private static var line = "On the mountains of truth you can never climb in vain: either you will reach a point higher up today, or you will be training your powers so that you will be able to climb higher tomorrow."
    
    static var previews: some View {
        FloatingTranscriptionView(line: $line)
    }
}
