// Translucent usage widget for claude-usage, with Chainsaw Man / Reze themes.
// A Dock app: a normal window that can be pinned above everything. Polls the local
// `claude-usage serve` feed at /widget.json, and starts that server if needed.
// Character art and an optional looping background video are files the user
// picks per theme (right-click menu); nothing copyrighted ships in the app.
import AppKit
import AVFoundation
import UniformTypeIdentifiers

let port = 8899
let base = URL(string: "http://127.0.0.1:\(port)/")!
// build.sh records the venv's `claude-usage`; a downloaded release has none,
// so fall back to where pipx / pip --user / Homebrew put it.
let serverBin = ([Bundle.main.object(forInfoDictionaryKey: "CUServerBin") as? String].compactMap { $0 } + [
    "~/.local/bin/claude-usage", "/opt/homebrew/bin/claude-usage", "/usr/local/bin/claude-usage",
].map { NSString(string: $0).expandingTildeInPath })
    .first { FileManager.default.isExecutableFile(atPath: $0) } ?? "claude-usage"
let supportDir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    .appendingPathComponent("ClaudeUsageWidget", isDirectory: true)

func rgb(_ v: UInt32, _ a: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((v >> 16) & 0xff) / 255, green: CGFloat((v >> 8) & 0xff) / 255, blue: CGFloat(v & 0xff) / 255, alpha: a)
}

// Series order is the stack order (claude, codex, deepseek); each theme's trio
// keeps the cool hue in the middle so adjacent segments separate. Both trios
// were checked with the dataviz palette validator on their card surface.
struct Theme {
    let id: String
    let name: String
    let header: String
    let accent: NSColor        // header text and card hairline
    let series: [NSColor]
    let gradient: [NSColor]    // card tint, top-left -> bottom-right
}

let themes = [
    Theme(id: "chainsaw", name: "电锯人", header: "DEVIL HUNTER", accent: rgb(0xd92b35),
          series: [rgb(0xd92b35), rgb(0x3b8ccc), rgb(0xcc7019), rgb(0xe8c547)],  // blood, saw steel, Pochita, Power's horns
          gradient: [rgb(0x120c0d, 0.72), rgb(0x4a0c10, 0.62)]),        // black into dried blood
    Theme(id: "reze", name: "蕾塞", header: "REZE", accent: rgb(0xb9a6ff),
          series: [rgb(0xdc6a32), rgb(0x7f72e6), rgb(0x2ba370), rgb(0xe86fa8)],  // blast orange, her hair, her eyes, Power pink
          gradient: [rgb(0x120d24, 0.74), rgb(0x3a1f52, 0.62)]),        // typhoon night into violet
]
let theme = themes.first { $0.id == UserDefaults.standard.string(forKey: "theme") } ?? themes[0]
let series = theme.series
let bone = rgb(0xece4d4)
let ash = rgb(0xece4d4, 0.62)

func compact(_ n: Double) -> String {
    switch n {
    case 1e9...: return String(format: "%.1fB", n / 1e9)
    case 1e6...: return String(format: "%.1fM", n / 1e6)
    case 1e3...: return String(format: "%.0fK", n / 1e3)
    default: return String(format: "%.0f", n)
    }
}

func label(_ text: String, size: CGFloat, weight: NSFont.Weight = .regular, color: NSColor = bone) -> NSTextField {
    let l = NSTextField(labelWithString: text)
    l.font = .systemFont(ofSize: size, weight: weight)
    l.textColor = color
    return l
}

func impact(_ size: CGFloat) -> NSFont {
    NSFont(name: "Impact", size: size) ?? .systemFont(ofSize: size, weight: .black)
}

struct Day { let date: String; let values: [Double]; var power: Double = 0 }  // claude, codex, deepseek

// Seven stacked columns, one segment per tool, 2px surface gap between segments.
final class WeekView: NSView {
    var days: [Day] = [] { didSet { needsDisplay = true } }
    override func draw(_ dirtyRect: NSRect) {
        guard !days.isEmpty else { return }
        let maxTotal = max(days.map { $0.values.reduce(0, +) }.max() ?? 0, 1)
        let slot = bounds.width / CGFloat(days.count)
        let barW = min(16, slot - 10)
        for (i, day) in days.enumerated() {
            var y: CGFloat = 0
            let x = CGFloat(i) * slot + (slot - barW) / 2
            let segs = day.values.enumerated().filter { $0.element > 0 }
            for (k, (idx, v)) in segs.enumerated() {
                if k > 0 { y += 2 }
                let h = max(1, CGFloat(v / maxTotal) * bounds.height - (k > 0 ? 2 : 0))
                series[idx].setFill()
                if k == segs.count - 1 {  // round only the top of the topmost segment
                    let p = NSBezierPath(roundedRect: NSRect(x: x, y: y, width: barW, height: h), xRadius: min(3, barW / 2), yRadius: min(3, h / 2))
                    p.append(NSBezierPath(rect: NSRect(x: x, y: y, width: barW, height: h / 2)))
                    p.fill()
                } else {
                    NSRect(x: x, y: y, width: barW, height: h).fill()
                }
                y += h
            }
            if day.power > 0 {  // Power's share, as a thin bar to the right (it overlaps the stack)
                series[3].setFill()
                NSRect(x: x + barW + 1.5, y: 0, width: 2.5, height: max(1, CGFloat(day.power / maxTotal) * bounds.height)).fill()
            }
            if segs.isEmpty {  // keep quiet days visible as a baseline tick
                ash.withAlphaComponent(0.35).setFill()
                NSRect(x: x, y: 0, width: barW, height: 1).fill()
            }
        }
    }
}

// The chainsaw: a row of teeth along the top edge of the card.
final class TeethView: NSView {
    override func draw(_ dirtyRect: NSRect) {
        let tooth: CGFloat = 9
        let p = NSBezierPath()
        p.move(to: NSPoint(x: 0, y: 0))
        var x: CGFloat = 0
        while x < bounds.width {
            p.line(to: NSPoint(x: x + tooth * 0.7, y: bounds.height))  // raked like a saw chain
            p.line(to: NSPoint(x: x + tooth, y: 0))
            x += tooth
        }
        p.close()
        rgb(0x9aa3ab).setFill()
        p.fill()
        rgb(0xd92b35).setFill()  // blood line under the chain
        NSRect(x: 0, y: 0, width: bounds.width, height: 2).fill()
    }
}

// Reze's choker: a black band with the grenade pin ring hanging from it.
final class ChokerView: NSView {
    override func draw(_ dirtyRect: NSRect) {
        rgb(0x0b0a12).setFill()
        NSRect(x: 0, y: bounds.height - 6, width: bounds.width, height: 6).fill()
        rgb(0xb9a6ff, 0.5).setFill()
        NSRect(x: 0, y: bounds.height - 7, width: bounds.width, height: 1).fill()
        let steel = rgb(0xc9cdd8)
        steel.setStroke()
        steel.setFill()
        // Hangs right of the header and date, clear of all text.
        let px: CGFloat = 196
        NSRect(x: px, y: bounds.height - 12, width: 2, height: 7).fill()        // the pin
        let ring = NSBezierPath(ovalIn: NSRect(x: px - 4.5, y: bounds.height - 23, width: 11, height: 11))
        ring.lineWidth = 1.8
        ring.stroke()
    }
}

// Faint festival fireworks behind the numbers.
final class FireworksView: NSView {
    override func draw(_ dirtyRect: NSRect) {
        let bursts: [(CGFloat, CGFloat, CGFloat, NSColor)] = [
            // Kept in the art column, behind the character, so no number sits on a burst.
            (0.72, 0.84, 24, rgb(0xdc6a32, 0.20)), (0.93, 0.62, 16, rgb(0xb9a6ff, 0.18)), (0.80, 0.30, 12, rgb(0x2ba370, 0.14)),
        ]
        for (fx, fy, r, color) in bursts {
            let c = NSPoint(x: bounds.width * fx, y: bounds.height * fy)
            color.setStroke()
            for k in 0..<14 {
                let a = CGFloat(k) / 14 * 2 * .pi
                let p = NSBezierPath()
                p.move(to: NSPoint(x: c.x + cos(a) * r * 0.35, y: c.y + sin(a) * r * 0.35))
                p.line(to: NSPoint(x: c.x + cos(a) * r, y: c.y + sin(a) * r))
                p.lineWidth = 1.2
                p.lineCapStyle = .round
                p.stroke()
            }
        }
    }
}

// Borderless windows refuse key status by default; the zoom/pin shortcuts need it.
final class WidgetWindow: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

/// Dock / Finder icon: the theme card with a three-tool stacked bar.
func appIcon() -> NSImage {
    NSImage(size: NSSize(width: 512, height: 512), flipped: false) { r in
        let card = NSBezierPath(roundedRect: r.insetBy(dx: 40, dy: 40), xRadius: 90, yRadius: 90)
        NSGradient(colors: theme.gradient.map { $0.withAlphaComponent(1) })?.draw(in: card, angle: -45)
        theme.accent.setStroke(); card.lineWidth = 10; card.stroke()
        for (i, h) in [150.0, 250.0, 200.0].enumerated() {
            series[i].setFill()
            NSBezierPath(roundedRect: NSRect(x: 120 + Double(i) * 100, y: 120, width: 72, height: h), xRadius: 14, yRadius: 14).fill()
        }
        return true
    }
}

final class WidgetController: NSObject, NSApplicationDelegate {
    let window: NSWindow
    let header = NSTextField(labelWithString: "DEVIL HUNTER")
    let date = label("", size: 11, weight: .medium, color: ash)
    let values = (0..<4).map { _ in label("–", size: 16, weight: .heavy) }
    let extras = (0..<4).map { _ in label("", size: 11, color: ash) }
    let week = WeekView()
    let status = label("正在读取用量…", size: 10, color: ash)
    // Plan limits, one line each: Claude 5-hour, Claude week, Codex week.
    let limitLines = (0..<3).map { _ in label("", size: 10.5, color: ash) }
    let pinButton = NSButton()
    let character = NSImageView()
    let card = NSView()
    let videoLayer = AVPlayerLayer()
    var looper: AVPlayerLooper?
    let tint = NSView()
    var startedServer = false

    static let cardSize = NSSize(width: 410, height: 258)
    static let overhang: CGFloat = 34   // how far a cut-out character pokes above the card
    static let artWidth: CGFloat = 140

    override init() {
        let cs = Self.cardSize
        let size = NSSize(width: cs.width, height: cs.height + Self.overhang)
        window = WidgetWindow(contentRect: NSRect(origin: .zero, size: size), styleMask: [.borderless], backing: .buffered, defer: false)
        super.init()
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        window.appearance = NSAppearance(named: .darkAqua)
        window.isMovableByWindowBackground = true

        let root = NSView(frame: NSRect(origin: .zero, size: size))
        window.contentView = root

        // Card: frosted glass, darkened, with a blood-red hairline.
        card.frame = NSRect(origin: .zero, size: cs)
        card.wantsLayer = true
        card.layer?.cornerRadius = 14
        card.layer?.masksToBounds = true
        card.layer?.borderWidth = 1
        card.layer?.borderColor = theme.accent.withAlphaComponent(0.7).cgColor
        let blur = NSVisualEffectView(frame: card.bounds)
        blur.material = .hudWindow
        blur.blendingMode = .behindWindow
        blur.state = .active
        card.addSubview(blur)
        // Optional looping background video sits between the glass and the tint.
        let videoHost = NSView(frame: card.bounds)
        videoHost.wantsLayer = true
        videoLayer.frame = videoHost.bounds
        videoLayer.videoGravity = .resizeAspectFill
        videoHost.layer?.addSublayer(videoLayer)
        card.addSubview(videoHost)
        tint.frame = card.bounds
        tint.wantsLayer = true
        let grad = CAGradientLayer()
        grad.frame = tint.bounds
        grad.colors = theme.gradient.map(\.cgColor)
        grad.startPoint = CGPoint(x: 0, y: 1)
        grad.endPoint = CGPoint(x: 1, y: 0)
        tint.layer?.addSublayer(grad)
        card.addSubview(tint)
        if theme.id == "reze" {
            card.addSubview(FireworksView(frame: card.bounds))
            card.addSubview(ChokerView(frame: NSRect(x: 0, y: cs.height - 24, width: cs.width, height: 24)))
        } else {
            card.addSubview(TeethView(frame: NSRect(x: 0, y: cs.height - 7, width: cs.width, height: 7)))
        }
        root.addSubview(card)

        // Character art (added after the card so a cut-out can overlap its top edge).
        character.imageScaling = .scaleProportionallyUpOrDown
        character.imageAlignment = .alignBottom
        character.wantsLayer = true
        root.addSubview(character)

        header.font = impact(18)
        header.stringValue = theme.header
        header.textColor = theme.accent
        let headRow = NSStackView(views: [header, date])
        headRow.alignment = .firstBaseline
        headRow.spacing = 8

        let names = ["Claude", "Codex", "DeepSeek", "Power"]
        var rows: [NSView] = [headRow]
        for i in 0..<4 {
            let mark = NSView()  // a short blade-shaped key in the series color
            mark.wantsLayer = true
            mark.layer?.backgroundColor = series[i].cgColor
            mark.layer?.cornerRadius = 1.5
            mark.translatesAutoresizingMaskIntoConstraints = false
            NSLayoutConstraint.activate([mark.widthAnchor.constraint(equalToConstant: 12), mark.heightAnchor.constraint(equalToConstant: 5)])
            let name = label(names[i], size: 12, weight: .semibold, color: ash)
            name.translatesAutoresizingMaskIntoConstraints = false
            name.widthAnchor.constraint(equalToConstant: 62).isActive = true
            extras[i].setContentCompressionResistancePriority(.required, for: .horizontal)
            let row = NSStackView(views: [mark, name, values[i], NSView(), extras[i]])
            row.spacing = 7
            row.alignment = .centerY
            rows.append(row)
            // Limit lines sit under their tool, indented past the color key.
            for line in (i == 0 ? [limitLines[0], limitLines[1]] : i == 1 ? [limitLines[2]] : []) {
                let pad = NSView()
                pad.translatesAutoresizingMaskIntoConstraints = false
                pad.widthAnchor.constraint(equalToConstant: 12).isActive = true
                let lineRow = NSStackView(views: [pad, line])
                lineRow.spacing = 7
                rows.append(lineRow)
            }
        }
        week.translatesAutoresizingMaskIntoConstraints = false
        week.heightAnchor.constraint(equalToConstant: 32).isActive = true
        let weekRow = NSStackView(views: [week, label("近 7 天", size: 10, color: ash)])
        weekRow.alignment = .bottom
        rows += [weekRow, status]

        let stack = NSStackView(views: rows)
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 5
        stack.translatesAutoresizingMaskIntoConstraints = false
        card.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 16),
            stack.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -(Self.artWidth + 6)),
            stack.topAnchor.constraint(equalTo: card.topAnchor, constant: theme.id == "reze" ? 20 : 16),
        ])
        for r in rows.dropFirst() { r.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true }

        // Always-visible controls, top-right of the card: zoom out, zoom in, pin.
        let tools: [(String, String, Selector)] = [
            ("minus.magnifyingglass", "缩小 (⌘-)", #selector(zoomOut)),
            ("plus.magnifyingglass", "放大 (⌘=)", #selector(zoomIn)),
            ("pin", "置顶：不被其他窗口盖住 (⌘P)", #selector(togglePin)),
        ]
        let buttons = tools.map { sym, tip, action -> NSButton in
            let b = action == #selector(togglePin) ? pinButton : NSButton()
            b.image = NSImage(systemSymbolName: sym, accessibilityDescription: tip)
            b.isBordered = false
            b.contentTintColor = ash
            b.toolTip = tip
            b.target = self
            b.action = action
            return b
        }
        let toolRow = NSStackView(views: buttons)
        toolRow.spacing = 6
        toolRow.edgeInsets = NSEdgeInsets(top: 3, left: 7, bottom: 3, right: 7)
        toolRow.wantsLayer = true  // dark pill so the icons read over character art
        toolRow.layer?.backgroundColor = rgb(0x0b0a12, 0.7).cgColor
        toolRow.layer?.cornerRadius = 11
        toolRow.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(toolRow, positioned: .above, relativeTo: character)
        NSLayoutConstraint.activate([
            toolRow.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -8),
            toolRow.topAnchor.constraint(equalTo: card.topAnchor, constant: theme.id == "reze" ? 10 : 12),
        ])

        let menu = NSMenu()
        menu.addItem(withTitle: "打开完整统计", action: #selector(openDashboard), keyEquivalent: "").target = self
        let themeItem = menu.addItem(withTitle: "主题", action: nil, keyEquivalent: "")
        let themeMenu = NSMenu()
        for t in themes {
            let item = themeMenu.addItem(withTitle: t.name, action: #selector(switchTheme(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = t.id
            item.state = t.id == theme.id ? .on : .off
        }
        themeItem.submenu = themeMenu
        menu.addItem(.separator())
        menu.addItem(withTitle: "放大", action: #selector(zoomIn), keyEquivalent: "").target = self
        menu.addItem(withTitle: "缩小", action: #selector(zoomOut), keyEquivalent: "").target = self
        menu.addItem(withTitle: "原始大小", action: #selector(zoomReset), keyEquivalent: "").target = self
        menu.addItem(withTitle: "置顶 / 取消置顶", action: #selector(togglePin), keyEquivalent: "").target = self
        menu.addItem(.separator())
        menu.addItem(withTitle: "选择角色图片…", action: #selector(pickCharacter), keyEquivalent: "").target = self
        menu.addItem(withTitle: "移除角色图片", action: #selector(removeCharacter), keyEquivalent: "").target = self
        menu.addItem(withTitle: "选择背景视频…", action: #selector(pickVideo), keyEquivalent: "").target = self
        menu.addItem(withTitle: "移除背景视频", action: #selector(removeVideo), keyEquivalent: "").target = self
        menu.addItem(.separator())
        menu.addItem(withTitle: "退出", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "")
        root.menu = menu
        let dbl = NSClickGestureRecognizer(target: self, action: #selector(openDashboard))
        dbl.numberOfClicksRequired = 2
        root.addGestureRecognizer(dbl)
        root.addGestureRecognizer(NSMagnificationGestureRecognizer(target: self, action: #selector(pinch(_:))))

        loadCharacter()
        loadVideo()

        // Default spot: top-right of the menu-bar screen; afterwards wherever it was dragged.
        if !window.setFrameUsingName("ClaudeUsageWidget-csm"), let vf = NSScreen.screens.first?.visibleFrame {
            window.setFrameOrigin(NSPoint(x: vf.maxX - size.width - 24, y: vf.maxY - size.height - 16))
        }
        window.setFrameAutosaveName("ClaudeUsageWidget-csm")
        let saved = UserDefaults.standard.double(forKey: "scale")
        setScale(saved > 0 ? saved : 1)
        setPinned(UserDefaults.standard.bool(forKey: "pinned"))
        window.makeKeyAndOrderFront(nil)

        refresh()
        Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in self?.refresh() }
    }

    // MARK: size

    static let scaleRange: ClosedRange<CGFloat> = 0.6...2.5
    var scale: CGFloat = 1

    /// The content keeps its 410-wide layout; the view's bounds stay at that
    /// size while its frame grows or shrinks, so everything redraws sharp.
    func setScale(_ s: CGFloat) {
        guard let root = window.contentView else { return }
        scale = min(max(s, Self.scaleRange.lowerBound), Self.scaleRange.upperBound)
        UserDefaults.standard.set(Double(scale), forKey: "scale")
        let logical = NSSize(width: Self.cardSize.width, height: Self.cardSize.height + Self.overhang)
        var f = window.frame
        let size = NSSize(width: (logical.width * scale).rounded(), height: (logical.height * scale).rounded())
        f.origin.y += f.height - size.height   // grow down from the top-left corner
        f.size = size
        window.setFrame(f, display: true)
        root.setBoundsSize(logical)
        root.needsDisplay = true
    }

    @objc func zoomIn() { setScale(scale + 0.1) }
    @objc func zoomOut() { setScale(scale - 0.1) }
    @objc func zoomReset() { setScale(1) }
    @objc func pinch(_ g: NSMagnificationGestureRecognizer) {
        setScale(scale * (1 + g.magnification))
        g.magnification = 0
    }

    // MARK: pin

    var pinned = false

    /// Pinned: floats above every app (and full-screen apps) on every Space.
    /// Unpinned: an ordinary window that other apps can cover.
    func setPinned(_ on: Bool) {
        pinned = on
        UserDefaults.standard.set(on, forKey: "pinned")
        window.level = on ? .floating : .normal
        window.collectionBehavior = on ? [.canJoinAllSpaces, .fullScreenAuxiliary] : []
        pinButton.image = NSImage(systemSymbolName: on ? "pin.fill" : "pin", accessibilityDescription: "置顶")
        pinButton.contentTintColor = on ? theme.accent : ash
    }

    @objc func togglePin() { setPinned(!pinned) }

    // MARK: app

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil)  // clicking the Dock icon brings the card back
        return true
    }

    func buildMainMenu() {
        let bar = NSMenu()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "打开完整统计", action: #selector(openDashboard), keyEquivalent: "d").target = self
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "退出", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let view = NSMenu(title: "显示")
        view.addItem(withTitle: "放大", action: #selector(zoomIn), keyEquivalent: "=").target = self
        view.addItem(withTitle: "缩小", action: #selector(zoomOut), keyEquivalent: "-").target = self
        view.addItem(withTitle: "原始大小", action: #selector(zoomReset), keyEquivalent: "0").target = self
        view.addItem(.separator())
        view.addItem(withTitle: "置顶 / 取消置顶", action: #selector(togglePin), keyEquivalent: "p").target = self
        for m in [appMenu, view] { bar.addItem(withTitle: "", action: nil, keyEquivalent: "").submenu = m }
        NSApp.mainMenu = bar
    }

    // MARK: character art

    // Each theme keeps its own files: character-<theme>.<ext>, video-<theme>.<ext>.
    func mediaFile(_ kind: String) -> URL? {
        (try? FileManager.default.contentsOfDirectory(at: supportDir, includingPropertiesForKeys: nil))?
            .first { $0.deletingPathExtension().lastPathComponent == "\(kind)-\(theme.id)" }
    }
    var characterFile: URL? { mediaFile("character") }

    func storeMedia(_ kind: String, types: [UTType], message: String) -> Bool {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = types
        panel.message = message
        NSApp.activate(ignoringOtherApps: true)
        guard panel.runModal() == .OK, let src = panel.url else { return false }
        do {
            try FileManager.default.createDirectory(at: supportDir, withIntermediateDirectories: true)
            if let old = mediaFile(kind) { try FileManager.default.removeItem(at: old) }
            try FileManager.default.copyItem(at: src, to: supportDir.appendingPathComponent("\(kind)-\(theme.id)").appendingPathExtension(src.pathExtension))
            return true
        } catch {
            status.stringValue = "保存失败：\(error.localizedDescription)"
            return false
        }
    }

    func loadVideo() {
        guard let url = mediaFile("video") else {
            looper = nil
            videoLayer.player = nil
            (tint.layer?.sublayers?.first as? CAGradientLayer)?.opacity = 1
            return
        }
        let player = AVQueuePlayer()
        player.isMuted = true
        player.preventsDisplaySleepDuringVideoPlayback = false
        looper = AVPlayerLooper(player: player, templateItem: AVPlayerItem(url: url))
        videoLayer.player = player
        // The full-strength tint stays on so the numbers stay readable over any clip.
        player.play()
    }

    @objc func pickVideo() {
        if storeMedia("video", types: [.movie], message: "选一段视频当背景（会静音循环播放）") { loadVideo() }
    }

    @objc func removeVideo() {
        if let old = mediaFile("video") { try? FileManager.default.removeItem(at: old) }
        loadVideo()
    }

    @objc func switchTheme(_ sender: NSMenuItem) {
        guard let id = sender.representedObject as? String, id != theme.id else { return }
        UserDefaults.standard.set(id, forKey: "theme")
        // Theme is fixed for the process lifetime; relaunch to rebuild the card.
        let cfg = NSWorkspace.OpenConfiguration()
        cfg.createsNewApplicationInstance = true
        NSWorkspace.shared.openApplication(at: Bundle.main.bundleURL, configuration: cfg) { _, _ in
            DispatchQueue.main.async { NSApp.terminate(nil) }
        }
    }

    func loadCharacter() {
        let cs = Self.cardSize, w = Self.artWidth
        guard let url = characterFile, let img = NSImage(contentsOf: url) else {
            character.image = nil
            return
        }
        character.image = img
        let hasAlpha = img.representations.contains { $0.hasAlpha }
        if hasAlpha {
            // Cut-out: stands on the card's bottom edge and pokes out of the top.
            character.frame = NSRect(x: cs.width - w - 4, y: 0, width: w, height: cs.height + Self.overhang)
            character.layer?.mask = nil
            character.layer?.cornerRadius = 0
        } else {
            // Photo / screenshot: inset inside the card, fading into it on the left.
            character.frame = NSRect(x: cs.width - w - 10, y: 10, width: w, height: cs.height - 26)
            character.imageScaling = .scaleProportionallyUpOrDown
            character.layer?.cornerRadius = 10
            character.layer?.masksToBounds = true
            let fade = CAGradientLayer()
            fade.frame = character.bounds
            fade.colors = [NSColor.clear.cgColor, NSColor.black.cgColor]
            fade.startPoint = CGPoint(x: 0, y: 0.5)
            fade.endPoint = CGPoint(x: 0.35, y: 0.5)
            character.layer?.mask = fade
        }
    }

    @objc func pickCharacter() {
        if storeMedia("character", types: [.image], message: "选一张角色图片（透明背景的 PNG 抠图效果最好）") { loadCharacter() }
    }

    @objc func removeCharacter() {
        if let old = characterFile { try? FileManager.default.removeItem(at: old) }
        loadCharacter()
    }

    @objc func openDashboard() { NSWorkspace.shared.open(base) }

    func isoDate(_ s: String) -> Date? {
        let f = ISO8601DateFormatter()
        if let d = f.date(from: s) { return d }
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.date(from: s)
    }

    /// "本周 已用 22% · 10/14 07:39 重置"; times within a day show the clock only.
    func limitText(_ name: String, _ w: [String: Any]) -> String {
        guard let used = w["used_percent"] as? Double else { return "" }
        var text = String(format: "%@ 已用 %.0f%%", name, used)
        if let iso = w["resets_at"] as? String, let d = isoDate(iso) {
            let f = DateFormatter()
            f.dateFormat = d.timeIntervalSinceNow < 24 * 3600 ? "HH:mm" : "M/d HH:mm"
            text += " · \(f.string(from: d)) 重置"
        }
        // At the recent pace (see project_limit): when it runs out, else where it ends up at the reset.
        if let p = w["projection"] as? [String: Any] {
            if let iso = p["full_at"] as? String, let d = isoDate(iso) {
                let f = DateFormatter()
                f.dateFormat = d.timeIntervalSinceNow < 24 * 3600 ? "HH:mm" : "M/d HH:mm"
                text += " · ⚠︎ 按此速度 \(f.string(from: d)) 用完"
            } else if let r = p["at_reset"] as? Double {
                text += String(format: " · 预计 %.0f%%", r)
            }
        }
        return text
    }

    // MARK: data

    func refresh() {
        URLSession.shared.dataTask(with: base.appendingPathComponent("widget.json")) { [weak self] data, resp, _ in
            DispatchQueue.main.async { self?.handle(data: data, code: (resp as? HTTPURLResponse)?.statusCode) }
        }.resume()
    }

    func handle(data: Data?, code: Int?) {
        guard let code else {  // nothing listening: start the server once
            if !startedServer {
                startedServer = true
                let p = Process()
                p.executableURL = URL(fileURLWithPath: serverBin)
                p.arguments = ["serve", "--no-open", "--port", "\(port)"]
                p.standardOutput = FileHandle.nullDevice
                p.standardError = FileHandle.nullDevice
                do { try p.run(); status.stringValue = "正在启动统计服务…" } catch { status.stringValue = "找不到 claude-usage，请先安装（见 README）" }
            }
            return
        }
        guard code == 200, let data, let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            status.stringValue = code == 503 ? "第一次读取 Codex 记录，稍等…" : "统计服务返回错误 \(code)"
            return
        }
        if let err = obj["error"] as? String { status.stringValue = "读取失败：\(err)"; return }
        let today = obj["today"] as? [String: Double] ?? [:]
        values[0].stringValue = String(format: "$%.2f", today["claude_cost"] ?? 0)
        extras[0].stringValue = compact(today["claude"] ?? 0)
        values[1].stringValue = compact(today["codex"] ?? 0)
        if let lim = obj["codex_limit"] as? [String: Any] {
            limitLines[2].stringValue = limitText("本周", lim)
        }
        if let cl = obj["claude_limit"] as? [String: Any] {
            var stale = ""
            if let iso = cl["saved_at"] as? String, let d = isoDate(iso), Date().timeIntervalSince(d) > 30 * 60 {
                let t = DateFormatter(); t.dateFormat = "HH:mm"
                stale = " · 截至\(t.string(from: d))"  // only refreshed while Claude Code is open
            }
            limitLines[0].stringValue = (cl["five_hour"] as? [String: Any]).map { limitText("5小时", $0) + stale } ?? ""
            limitLines[1].stringValue = (cl["seven_day"] as? [String: Any]).map { limitText("本周", $0) + stale } ?? ""
        } else {
            limitLines[0].stringValue = "额度：重开 Claude Code 后显示"
            limitLines[1].stringValue = ""
        }
        // Power (the user's own agent) runs on the tools above, so it is a share of them.
        let p = obj["power"] as? [String: Double] ?? [:]
        let all = ["claude", "codex", "deepseek"].reduce(0) { $0 + (today[$1] ?? 0) }
        values[3].stringValue = compact(p["tokens"] ?? 0)
        extras[3].stringValue = String(format: "$%.2f · 占 %.0f%%", p["cost"] ?? 0, all > 0 ? (p["tokens"] ?? 0) / all * 100 : 0)
        values[2].stringValue = compact(today["deepseek"] ?? 0)
        week.days = (obj["week"] as? [[String: Any]] ?? []).map { d in
            Day(date: d["d"] as? String ?? "", values: ["claude", "codex", "deepseek"].map { (d[$0] as? Double) ?? 0 }, power: d["power"] as? Double ?? 0)
        }
        let f = DateFormatter(); f.dateFormat = "M月d日 · 今天"
        date.stringValue = f.string(from: Date())
        let t = DateFormatter(); t.dateFormat = "HH:mm"
        status.stringValue = characterFile == nil
            ? "更新于 \(t.string(from: Date())) · 右键选择角色图片"
            : "更新于 \(t.string(from: Date())) · 双击看完整统计"
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)  // lives in the Dock
app.applicationIconImage = appIcon()
// Give the bundle the same icon so it shows in Finder and in the Dock while closed.
if !FileManager.default.fileExists(atPath: Bundle.main.bundlePath + "/Icon\r") {
    NSWorkspace.shared.setIcon(app.applicationIconImage, forFile: Bundle.main.bundlePath)
}
let controller = WidgetController()
app.delegate = controller
controller.buildMainMenu()
app.activate(ignoringOtherApps: true)
app.run()
