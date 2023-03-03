//
//  ProgressView.swift
//  Buzz
//
//  Created by Chidi Williams on 27/02/2023.
//

import Foundation
import SwiftUI

struct CircularProgressView: View {
    @Binding var current: Float
    @Binding var total: Float
    var stopAction: () -> Void = {}
    
    var body: some View {
        Button(action: stopAction) {
            ZStack() {
                Circle()
                    .trim(from: 0, to: CGFloat(Float(current) / Float(total)))
                    .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 2, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .frame(width: 15, height: 15)
                Image(systemName: "stop.fill")
                    .resizable()
                    .frame(width: 5, height: 5)
                    .foregroundColor(.accentColor)
            }
        }
        .buttonStyle(.plain)
    }
}


struct CircularProgressView_Previews: PreviewProvider {
    static let timer = Timer.publish(every: 0.5, on: .main, in: .common).autoconnect()
    static var progress: Float = 0.0
    
    static var previews: some View {
        CircularProgressView(
            current: Binding(get: {progress}, set: {
                _,_ in
            }), total: Binding(get: {1}, set: {_, _ in}))
        .onReceive(timer, perform: { _ in
            progress += 0.2
            progress = progress < 1.0 ? progress : 0.0
        })
    }
}
