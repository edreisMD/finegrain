// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "Finegrain", platforms: [.macOS(.v13)], products: [.executable(name: "Finegrain", targets: ["Finegrain"])], targets: [.executableTarget(name: "Finegrain")])
