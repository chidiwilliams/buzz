//
//  Recorder.swift
//  Buzz
//
//  Created by Chidi Williams on 03/02/2023.
//

import Foundation
import AVFoundation

class Recorder: NSObject, AVCaptureAudioDataOutputSampleBufferDelegate {
    let alwaysMono = false
    var nChannels:UInt32 = 1
    let session : AVCaptureSession!
    static var isTranscribing = false
    static let realTimeQueue = DispatchQueue(label: "com.myapp.realtime",
                                             qos: DispatchQoS( qosClass:DispatchQoS.QoSClass.userInitiated, relativePriority: 0 ))
    static let transcriptionQueue = DispatchQueue(label: "transcription", qos: DispatchQoS(qosClass: DispatchQoS.QoSClass.userInitiated, relativePriority: 1))
    override init() {
        session = AVCaptureSession()
        super.init()
    }
    static var recorder:Recorder?
    static func record() ->Bool {
        if recorder == nil {
            recorder = Recorder()
            if !recorder!.setup(callback:record) {
                recorder = nil
                return false
            }
        }
        realTimeQueue.async {
            if !recorder!.session.isRunning {
                recorder!.session.startRunning()
                print("started running")
            }
        }
        transcriptionQueue.async {
            isTranscribing = true
            while isTranscribing {
                print("hello")
                sleep(5)
            }
        }
        return true
    }
    static func pause() {
        recorder!.session.stopRunning()
        isTranscribing = false
    }
    func setup( callback:@escaping (()->Bool)) -> Bool {
        let device = AVCaptureDevice.default( for: AVMediaType.audio )
        if device == nil { return false }
        if let format = getActiveFormat() {
            nChannels = format.mChannelLayoutTag == kAudioChannelLayoutTag_Stereo ? 2 : 1
            print("active format is \((nChannels==2) ? "Stereo" : "Mono")")
            if alwaysMono {
                print( "Overriding to mono" )
                nChannels = 1
            }
        }
        if #available(OSX 10.14, *) {
            let status = AVCaptureDevice.authorizationStatus( for:AVMediaType.audio )
            if status == .notDetermined {
                AVCaptureDevice.requestAccess(for: AVMediaType.audio ){ granted in
                    _ = callback()
                }
                return false
            } else if status != .authorized {
                return false
            }
        }
        var input : AVCaptureDeviceInput
        do {
            try device!.lockForConfiguration()
            try input = AVCaptureDeviceInput( device: device! )
            device!.unlockForConfiguration()
        } catch {
            device!.unlockForConfiguration()
            return false
        }
        let output = AVCaptureAudioDataOutput()
        output.setSampleBufferDelegate(self, queue: Recorder.realTimeQueue)
        let settings = [
            AVFormatIDKey: kAudioFormatLinearPCM,
//            AVNumberOfChannelsKey : nChannels,
            AVSampleRateKey : Recorder.SAMPLE_RATE,
            AVLinearPCMBitDepthKey : 32,
            AVLinearPCMIsFloatKey : true
        ] as [String : Any]
        output.audioSettings = settings
        session.beginConfiguration()
        if !session.canAddInput( input ) {
            return false
        }
        session.addInput( input )
        if !session.canAddOutput( output ) {
            return false
        }
        session.addOutput( output )
        session.commitConfiguration()
        return true
    }
    func getActiveFormat() -> AudioFormatListItem? {
        if #available(OSX 10.15, *) {
            let device = AVCaptureDevice.default( for: AVMediaType.audio )
            if device == nil { return nil }
            let list = device!.activeFormat.formatDescription.audioFormatList
            if list.count < 1 { return nil }
            return list[0]
        }
        return nil
    }
    func captureOutput(_ captureOutput: AVCaptureOutput,
                       didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection){
        var buffer: CMBlockBuffer? = nil
        var audioBufferList = AudioBufferList(
            mNumberBuffers: 1,
            mBuffers: AudioBuffer(mNumberChannels: nChannels, mDataByteSize: 0, mData: nil)
        )
        let status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer,
            bufferListSizeNeededOut: nil,
            bufferListOut: &audioBufferList,
            bufferListSize: MemoryLayout<AudioBufferList>.size,
            blockBufferAllocator: nil,
            blockBufferMemoryAllocator: nil,
            flags: UInt32(kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment),
            blockBufferOut: &buffer
        )
        if status != 0 {
            print("got error code \(status)")
            return
        }
        
        let abl = UnsafeMutableAudioBufferListPointer(&audioBufferList)
        for buff in abl {
            if buff.mData != nil {
                let count = Int(buff.mDataByteSize)/MemoryLayout<Float>.size
                let samples = UnsafeMutablePointer<Float>(OpaquePointer(buff.mData))
                process(samples:samples!, count:count)
            } else {
                print("No data!")
            }
        }
    }
    
    let MAX_SECONDS_BEHIND = 10
    static let SAMPLE_RATE = 16_000
    
    var circularBuffer: Array<Float> = []
    
    func process( samples: UnsafeMutablePointer<Float>, count: Int ) {
        let array = (Array(UnsafeBufferPointer(start: samples, count: count)))
        print(rms(array: array), array.count)
        
        if circularBuffer.count < MAX_SECONDS_BEHIND * Recorder.SAMPLE_RATE {
            print("appending")
            circularBuffer.append(contentsOf: array)
        }
    }
    
    func rms(array: Array<Float>) -> Float {
        var sumSquares = Float(0)
        var count = Float(0)
        for elem in array {
            sumSquares += elem * elem
            count += 1
        }
        return (sumSquares / count).squareRoot()
    }
}
