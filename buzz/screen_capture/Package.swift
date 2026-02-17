// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "BuzzScreenAudio",
    platforms: [.macOS(.v12)],
    targets: [
        .executableTarget(
            name: "buzz-screen-audio",
            path: "Sources",
            linkerSettings: [
                .linkedFramework("ScreenCaptureKit"),
                .linkedFramework("CoreMedia"),
                .linkedFramework("CoreAudio"),
                .linkedFramework("Accelerate"),
                .linkedFramework("AVFoundation"),
            ]
        )
    ]
)
