//
//  AudioRecorder.swift
//  Buzz
//
//  Created by Chidi Williams on 03/02/2023.
//

import Foundation
import AVFoundation
import whisper

class AudioRecorder: NSObject, AVCaptureAudioDataOutputSampleBufferDelegate {
    var session: AVCaptureSession
    let recordingQueue = DispatchQueue(label: "recording",
        qos: DispatchQoS(qosClass: .userInitiated, relativePriority: 0))
    static let SAMPLE_RATE = WHISPER_SAMPLE_RATE
    var microphone: AVCaptureDevice?
    var callback: ((UnsafeMutablePointer<Float>?, Int) -> Void)?
    
    init(microphoneUniqueID: String?) {
        session = AVCaptureSession()
        if let microphoneUniqueID = microphoneUniqueID {
            self.microphone = AVCaptureDevice(uniqueID: microphoneUniqueID)
        } else {
            self.microphone = AVCaptureDevice.default(for: .audio)
        }
        super.init()
        configureSession()
        
    }
    
    func record(callback: @escaping ((UnsafeMutablePointer<Float>?, Int) -> Void))  {
        self.callback = callback
        session.startRunning()
    }
    
    func pause()  {
        session.stopRunning()
    }
    
    func configureSession() {
        if let device = self.microphone {
            if #available(OSX 10.14, *) {
                let status = AVCaptureDevice.authorizationStatus(for: .audio)
                if status == .notDetermined {
                    AVCaptureDevice.requestAccess(for: .audio) { granted in
                        self.configureSession()
                    }
                    return
                }
                if status != .authorized {
                    return
                }
            }
            
            var input: AVCaptureDeviceInput
            do {
                try device.lockForConfiguration()
                try input = AVCaptureDeviceInput(device: device)
                device.unlockForConfiguration()
            } catch {
                device.unlockForConfiguration()
                return
            }
            
            let output = AVCaptureAudioDataOutput()
            output.setSampleBufferDelegate(self, queue: recordingQueue)
            output.audioSettings = [
                AVFormatIDKey: kAudioFormatLinearPCM,
                AVSampleRateKey: AudioRecorder.SAMPLE_RATE,
                AVLinearPCMBitDepthKey: 32,
                AVLinearPCMIsFloatKey: true,
                AVNumberOfChannelsKey: 1
            ] as [String : Any]
            
            session.beginConfiguration()
            if !session.canAddInput(input) {
                return
            }
            session.addInput(input)
            
            if !session.canAddOutput(output) {
                return
            }
            session.addOutput(output)
            session.commitConfiguration()
        }
        
    }
    
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        var blockBuffer: CMBlockBuffer? = nil
        
        var audioBufferList = AudioBufferList( mNumberBuffers: 1, mBuffers: AudioBuffer( mNumberChannels: 0, mDataByteSize: 0, mData: nil ))
        let status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer,
            bufferListSizeNeededOut: nil,
            bufferListOut: &audioBufferList,
            bufferListSize: MemoryLayout.size(ofValue: audioBufferList),
            blockBufferAllocator: kCFAllocatorSystemDefault,
            blockBufferMemoryAllocator: kCFAllocatorSystemDefault,
            flags: UInt32(kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment), blockBufferOut: &blockBuffer)
        if status != 0 {
            print("CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer failed with error code: \(status)")
            return
        }
        
        let audioBufferListPointer = UnsafeMutableAudioBufferListPointer(&audioBufferList)
        for buffer in audioBufferListPointer {
            if buffer.mData != nil {
                let count = Int(buffer.mDataByteSize) / MemoryLayout<Float>.size
                let samples = UnsafeMutablePointer<Float>(OpaquePointer(buffer.mData))
                if let callback = callback {
                    callback(samples, count)
                }
            }
        }
    }
}
