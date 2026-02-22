import Accelerate
import CoreMedia
import Foundation
import ScreenCaptureKit

// MARK: - Configuration

let targetSampleRate: Double = 16000
let nativeChannels: Int = 1

// MARK: - Argument Parsing

func parseArgs() -> (checkPermission: Bool, sampleRate: Int) {
    let args = CommandLine.arguments
    var checkPermission = false
    var sampleRate = 16000

    var i = 1
    while i < args.count {
        switch args[i] {
        case "--check-permission":
            checkPermission = true
        case "--sample-rate":
            if i + 1 < args.count, let rate = Int(args[i + 1]) {
                sampleRate = rate
                i += 1
            }
        default:
            break
        }
        i += 1
    }
    return (checkPermission, sampleRate)
}

// MARK: - Error Reporting (JSON to stderr)

func reportError(_ message: String) {
    let json = "{\"error\": \"\(message)\"}\n"
    if let data = json.data(using: .utf8) {
        FileHandle.standardError.write(data)
    }
}

func reportStatus(_ message: String) {
    let json = "{\"status\": \"\(message)\"}\n"
    if let data = json.data(using: .utf8) {
        FileHandle.standardError.write(data)
    }
}

// MARK: - Resampler

/// Downsample audio from a source sample rate to the target rate using vDSP.
func resample(
    input: UnsafeBufferPointer<Float>, from sourceSampleRate: Double,
    to destSampleRate: Double
) -> [Float] {
    guard sourceSampleRate > destSampleRate else {
        return Array(input)
    }

    let ratio = sourceSampleRate / destSampleRate
    let outputCount = Int(Double(input.count) / ratio)
    guard outputCount > 0 else { return [] }

    var output = [Float](repeating: 0, count: outputCount)

    // Generate the indices into the source buffer for each output sample
    var control = [Float](repeating: 0, count: outputCount)
    var start = Float(0)
    var step = Float(ratio)
    vDSP_vramp(&start, &step, &control, 1, vDSP_Length(outputCount))

    // Ensure we don't read past the end of the source buffer
    let maxIndex = Float(input.count - 2)
    for i in 0..<outputCount {
        control[i] = min(control[i], maxIndex)
    }

    // Linear interpolation using vDSP
    vDSP_vlint(
        input.baseAddress!, control, 1,
        &output, 1,
        vDSP_Length(outputCount),
        vDSP_Length(input.count)
    )

    return output
}

// MARK: - Stream Output Handler

@available(macOS 13.0, *)
class AudioCaptureDelegate: NSObject, SCStreamOutput {
    let targetRate: Double
    let stdoutHandle = FileHandle.standardOutput

    init(targetRate: Double) {
        self.targetRate = targetRate
    }

    func stream(
        _ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
        of type: SCStreamOutputType
    ) {
        guard type == .audio else { return }
        guard CMSampleBufferDataIsReady(sampleBuffer) else { return }

        guard let formatDesc = CMSampleBufferGetFormatDescription(sampleBuffer) else {
            return
        }
        let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(formatDesc)
        guard let sourceFormat = asbd?.pointee else { return }

        let sourceSampleRate = sourceFormat.mSampleRate
        let sourceChannels = Int(sourceFormat.mChannelsPerFrame)

        // Get audio buffer list
        var blockBuffer: CMBlockBuffer?
        var audioBufferList = AudioBufferList()
        let status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer,
            bufferListSizeNeededOut: nil,
            bufferListOut: &audioBufferList,
            bufferListSize: MemoryLayout<AudioBufferList>.size,
            blockBufferAllocator: nil,
            blockBufferMemoryAllocator: nil,
            flags: kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment,
            blockBufferOut: &blockBuffer
        )

        guard status == noErr else { return }

        let buffer = audioBufferList.mBuffers
        guard let data = buffer.mData else { return }
        let frameCount =
            Int(buffer.mDataByteSize) / MemoryLayout<Float>.size / sourceChannels

        let floatPtr = data.bindMemory(
            to: Float.self, capacity: frameCount * sourceChannels)

        // Mix down to mono if multichannel
        var monoSamples: [Float]
        if sourceChannels > 1 {
            monoSamples = [Float](repeating: 0, count: frameCount)
            for frame in 0..<frameCount {
                var sum: Float = 0
                for ch in 0..<sourceChannels {
                    sum += floatPtr[frame * sourceChannels + ch]
                }
                monoSamples[frame] = sum / Float(sourceChannels)
            }
        } else {
            monoSamples = Array(
                UnsafeBufferPointer(start: floatPtr, count: frameCount))
        }

        // Resample to target rate if needed
        let outputSamples: [Float]
        if abs(sourceSampleRate - targetRate) > 1.0 {
            outputSamples = monoSamples.withUnsafeBufferPointer { buf in
                resample(input: buf, from: sourceSampleRate, to: targetRate)
            }
        } else {
            outputSamples = monoSamples
        }

        // Write raw float32 to stdout
        outputSamples.withUnsafeBytes { rawBuf in
            let data = Data(rawBuf)
            stdoutHandle.write(data)
        }
    }
}

// MARK: - Permission Check

@available(macOS 12.3, *)
func checkPermission() {
    let semaphore = DispatchSemaphore(value: 0)
    var permissionGranted = false

    SCShareableContent.getExcludingDesktopWindows(
        false, onScreenWindowsOnly: false
    ) { content, error in
        if error != nil {
            permissionGranted = false
        } else {
            permissionGranted = content != nil
        }
        semaphore.signal()
    }

    let result = semaphore.wait(timeout: .now() + 10)
    if result == .timedOut {
        reportError("permission_check_timeout")
        exit(1)
    }

    if permissionGranted {
        reportStatus("permission_granted")
        exit(0)
    } else {
        reportError("screen_recording_permission_denied")
        exit(1)
    }
}

// MARK: - Main Capture Loop

@available(macOS 13.0, *)
func startCapture(sampleRate: Int) {
    // Get shareable content to create a filter
    SCShareableContent.getExcludingDesktopWindows(
        false, onScreenWindowsOnly: false
    ) { content, error in
        if let error = error {
            reportError(
                "failed_to_get_content: \(error.localizedDescription)")
            exit(1)
        }

        guard let content = content else {
            reportError("no_shareable_content")
            exit(1)
        }

        // Use the first display as the capture target (required even for audio-only)
        guard let display = content.displays.first else {
            reportError("no_display_found")
            exit(1)
        }

        // Create filter excluding current process audio
        let filter = SCContentFilter(
            display: display,
            excludingApplications: content.applications.filter {
                $0.bundleIdentifier == Bundle.main.bundleIdentifier
            },
            exceptingWindows: []
        )

        // Configure for audio-only capture
        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.channelCount = 1
        config.sampleRate = sampleRate

        // Minimize video overhead — we only want audio
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)

        let delegate = AudioCaptureDelegate(targetRate: Double(sampleRate))

        do {
            let stream = SCStream(
                filter: filter, configuration: config, delegate: nil)
            try stream.addStreamOutput(
                delegate, type: .audio,
                sampleHandlerQueue: DispatchQueue(
                    label: "buzz.screen-audio", qos: .userInteractive))

            stream.startCapture { error in
                if let error = error {
                    reportError(
                        "capture_start_failed: \(error.localizedDescription)")
                    exit(1)
                }
                reportStatus("capturing")
            }
        } catch {
            reportError(
                "stream_setup_failed: \(error.localizedDescription)")
            exit(1)
        }
    }

    // Handle SIGTERM and SIGINT for clean shutdown
    signal(SIGTERM) { _ in
        reportStatus("stopped")
        exit(0)
    }
    signal(SIGINT) { _ in
        reportStatus("stopped")
        exit(0)
    }

    // Keep the process alive
    dispatchMain()
}

// MARK: - Entry Point

let (checkPerm, sampleRate) = parseArgs()

if #available(macOS 13.0, *) {
    if checkPerm {
        checkPermission()
    } else {
        startCapture(sampleRate: sampleRate)
    }
} else if #available(macOS 12.3, *) {
    if checkPerm {
        checkPermission()
    } else {
        reportError("macos_13_0_required_for_audio_capture")
        exit(1)
    }
} else {
    reportError("macos_12_3_required")
    exit(1)
}
