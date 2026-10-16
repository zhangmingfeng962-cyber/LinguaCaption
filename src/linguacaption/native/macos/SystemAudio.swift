import AppKit
import AVFoundation
import CoreMedia
import Darwin
import ScreenCaptureKit

// stdout is exclusively little-endian float32 mono PCM at 48 kHz.
// All status and permission errors go to stderr. No video/audio is saved.
func logError(_ message: String) {
    FileHandle.standardError.write(Data((message + "\n").utf8))
}

@available(macOS 13.0, *)
final class AudioCapture: NSObject, SCStreamOutput, SCStreamDelegate {
    var stream: SCStream?
    let outputQueue = DispatchQueue(label: "local.linguacaption.audio", qos: .userInitiated)

    func start() async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else {
            throw NSError(domain: "LinguaCaption", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "No display available"])
        }
        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
        let config = SCStreamConfiguration()
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        config.queueDepth = 3
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.sampleRate = 48_000
        config.channelCount = 2
        let capture = SCStream(filter: filter, configuration: config, delegate: self)
        try capture.addStreamOutput(self, type: .audio, sampleHandlerQueue: outputQueue)
        stream = capture
        try await capture.startCapture()
        logError("READY")
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        logError("System capture stopped: \(error.localizedDescription)")
        exit(3)
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
                of type: SCStreamOutputType) {
        guard type == .audio, sampleBuffer.isValid,
              let format = sampleBuffer.formatDescription,
              let desc = CMAudioFormatDescriptionGetStreamBasicDescription(format)?.pointee else { return }
        let channels = Int(desc.mChannelsPerFrame)
        guard desc.mFormatID == kAudioFormatLinearPCM,
              desc.mFormatFlags & kAudioFormatFlagIsFloat != 0,
              desc.mFormatFlags & kAudioFormatFlagIsBigEndian == 0,
              desc.mBitsPerChannel == 32, desc.mSampleRate == 48_000, channels > 0 else {
            logError("Unsupported ScreenCaptureKit PCM format")
            exit(4)
        }
        let list = AudioBufferList.allocate(maximumBuffers: channels)
        defer { free(list.unsafeMutablePointer) }
        var retainedBuffer: CMBlockBuffer?
        let status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer, bufferListSizeNeededOut: nil,
            bufferListOut: list.unsafeMutablePointer,
            bufferListSize: AudioBufferList.sizeInBytes(maximumBuffers: channels),
            blockBufferAllocator: kCFAllocatorDefault, blockBufferMemoryAllocator: kCFAllocatorDefault,
            flags: UInt32(kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment),
            blockBufferOut: &retainedBuffer)
        guard status == noErr else { return }
        // Keep the CoreMedia memory alive until the PCM copy completes.
        withExtendedLifetime(retainedBuffer) {
            let frames = CMSampleBufferGetNumSamples(sampleBuffer)
            var mono = [Float](repeating: 0, count: frames)
            if desc.mFormatFlags & kAudioFormatFlagIsNonInterleaved != 0 {
                for buffer in list {
                    guard let data = buffer.mData, Int(buffer.mDataByteSize) >= frames * 4 else { return }
                    let samples = data.assumingMemoryBound(to: Float.self)
                    for frame in 0..<frames { mono[frame] += samples[frame] / Float(channels) }
                }
            } else {
                guard let buffer = list.first, let data = buffer.mData,
                      Int(buffer.mDataByteSize) >= frames * channels * 4 else { return }
                let samples = data.assumingMemoryBound(to: Float.self)
                for frame in 0..<frames {
                    for channel in 0..<channels {
                        mono[frame] += samples[frame * channels + channel] / Float(channels)
                    }
                }
            }
            mono.withUnsafeBytes { data in
                FileHandle.standardOutput.write(Data(data))
            }
        }
    }
}

@main
struct Main {
    static func main() async {
        guard #available(macOS 13.0, *) else {
            logError("Requires macOS 13 or later")
            exit(1)
        }
        // ActivationPolicy accessory avoids creating another Dock icon.
        NSApplication.shared.setActivationPolicy(.accessory)
        let capture = AudioCapture()
        do {
            try await capture.start()
            // Async sleep keeps Swift's main executor available for permission UI.
            while true { try await Task.sleep(nanoseconds: 1_000_000_000) }
        } catch {
            logError("ScreenCaptureKit: \(error.localizedDescription). Enable Screen & System Audio Recording permission and relaunch.")
            exit(2)
        }
    }
}
