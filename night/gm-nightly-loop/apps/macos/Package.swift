// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "GMNightly", platforms: [.macOS(.v13)], products: [.executable(name: "GMNightly", targets: ["GMNightly"])], targets: [.executableTarget(name: "GMNightly")])
