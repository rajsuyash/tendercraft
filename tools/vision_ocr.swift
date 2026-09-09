// macOS Vision OCR adapter — the LOCAL proof for M1, not the production path.
//
// Reads image file paths from argv and prints the recognised text for each, separated by a
// delimiter the caller splits on. Nothing else. No shell, no globbing, no reading of any path
// the caller did not name: `app/ocr.py` generates every path inside a temp directory it owns,
// so document content can never select a file or a command (G-6).
//
// WHY THIS EXISTS: ~52% of pages in a real customer's tender folder carry no extractable text,
// and the unreadable half is almost entirely the BIDDER's own documents — their proven-supply
// records, licences and declarations, which is exactly the evidence the product needs. The
// engine has no OCR at all (docs/PRD.md §4 still lists the provider as an open TODO).
//
// WHY VISION: it ships with macOS, so this costs nothing, adds no dependency, and no customer
// document leaves the machine — which also sidesteps the data-residency question a cloud OCR
// provider would raise before it could even be evaluated.
//
// WHAT THIS IS NOT: the engine image is Linux. This adapter cannot run in production. M2 adds a
// Linux adapter and validates it against the same pages. Shipping this as if it were the
// production answer would leave scans silently unread wherever it actually matters.

import Foundation
import Vision
import CoreGraphics
import ImageIO

let pageDelimiter = "\u{001E}TENDERCRAFT_PAGE_BREAK\u{001E}"

/// Recognise text in one image. Returns "" rather than throwing: one unreadable page must not
/// fail a 57-page document, and the caller already treats an empty page as illegible.
func recognise(path: String) -> String {
    let url = URL(fileURLWithPath: path)
    guard
        let source = CGImageSourceCreateWithURL(url as CFURL, nil),
        let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
    else { return "" }

    let request = VNRecognizeTextRequest()
    // .accurate: these are certificates and licence numbers, where a wrong digit is worse than
    // a slow page. `usesLanguageCorrection` off — correcting "IS 1855" or "CM/L-0000062931"
    // toward dictionary words is exactly the failure to avoid on this corpus.
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = ["en-US"]

    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    do {
        try handler.perform([request])
    } catch {
        return ""
    }

    guard let observations = request.results else { return "" }
    return observations
        .compactMap { $0.topCandidates(1).first?.string }
        .joined(separator: "\n")
}

let paths = Array(CommandLine.arguments.dropFirst())
if paths.isEmpty {
    FileHandle.standardError.write("usage: vision_ocr <image> [image ...]\n".data(using: .utf8)!)
    exit(2)
}

let texts = paths.map(recognise)
print(texts.joined(separator: pageDelimiter))
