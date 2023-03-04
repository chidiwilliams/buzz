//
//  HighlightTextView.swift
//  Buzz
//
//  Created by Chidi Williams on 04/03/2023.
//

import SwiftUI

struct HighlightTextView: View {
    var text: String
    var highlights: [String]
    
    var body: some View {
        highlights
        // Replace each occurence of a highlight in text with "==>$0=="
            .reduce(text) { $0.replacingOccurrences(of: $1, with: "==>$0==", options: [.regularExpression, .caseInsensitive]) }
        // Split by "==". Each occurence will now be prefixed by ">"
            .components(separatedBy: "==")
            .reduce(Text("")) {
                if $1.hasPrefix(">") {
                    var highlighted = AttributedString($1.dropFirst())
                    highlighted.backgroundColor = .yellow
                    return $0 + Text(highlighted)
                } else {
                    return $0 + Text($1)
                }
            }
    }
}

struct HighlightTextView_Previews: PreviewProvider {
    static var previews: some View {
        HighlightTextView(text: "Hello, world.", highlights: ["hel", "o"])
    }
}
