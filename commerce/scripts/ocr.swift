import Foundation
import Vision
import AppKit
// Local label evidence only. No OCR string is executed or treated as an instruction.
guard CommandLine.arguments.count == 2 else { exit(2) }
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
let handler = VNImageRequestHandler(url: url, options: [:])
do {
 try handler.perform([request])
 let lines = (request.results ?? []).compactMap { observation -> [String: Any]? in
  guard let candidate = observation.topCandidates(1).first else { return nil }
  return ["text": candidate.string, "confidence": candidate.confidence,
   "box": [observation.boundingBox.origin.x, observation.boundingBox.origin.y, observation.boundingBox.width, observation.boundingBox.height]]
 }
 let data = try JSONSerialization.data(withJSONObject: ["engine":"Apple Vision local OCR", "lines":lines],options:[.sortedKeys])
 FileHandle.standardOutput.write(data)
} catch { FileHandle.standardError.write(Data("Local OCR unavailable\n".utf8));exit(1) }
