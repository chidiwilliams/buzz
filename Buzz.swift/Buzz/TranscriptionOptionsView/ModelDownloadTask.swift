//
//  ModelDownloadTask.swift
//  Buzz
//
//  Created by Chidi Williams on 28/02/2023.
//

import Foundation

class ModelDownloadTask: NSObject, ObservableObject, URLSessionDownloadDelegate {
    @Published var bytesWritten: Float = 0
    @Published var bytesExpected: Float = 0
    @Published var isDownloading = false
    
    private lazy var urlSession = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
    private var downloadTask: URLSessionDownloadTask?
    private var model: WhisperModel?
    
    func start(model: WhisperModel) {
        isDownloading = true
        guard let downloadURL = ModelLoader.getModelDownloadURL(model: model) else { return }
        let downloadTask = urlSession.downloadTask(with: downloadURL)
        downloadTask.resume()
        self.downloadTask = downloadTask
        self.model = model
        self.bytesExpected = Float(ModelLoader.getModelByteSize(model: model))
    }
    
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
        do {
            let modelPath = try ModelLoader.getModelPath(model: model!)
            try FileManager.default.createDirectory(at: modelPath.deletingLastPathComponent(), withIntermediateDirectories: true)
            
            if FileManager.default.fileExists(atPath: modelPath.path()) {
                try FileManager.default.removeItem(at: modelPath)
            }
            
            try FileManager.default.moveItem(at: location, to: modelPath)
            DispatchQueue.main.async {
                self.isDownloading = false
            }
        } catch {
            fatalError(error.localizedDescription)
        }
    }
    
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didWriteData bytesWritten: Int64, totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64) {
        DispatchQueue.main.async {
            self.bytesWritten = Float(totalBytesWritten)
            self.bytesExpected = Float(totalBytesExpectedToWrite)
        }
    }
    
    func cancel() {
        downloadTask?.cancel()
        self.isDownloading = false
    }
}
