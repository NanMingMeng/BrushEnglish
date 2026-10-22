// 设计令牌：颜色、字号、圆角、间距、动效时长全部集中在这里。
// 以后想换风格，只改这一个文件就够，其他界面文件不用动。
//
// 几条定死的规矩（改的时候别破坏）：
// 1. 外圆角 = 内圆角 + 内边距。卡片里套按钮时，卡片圆角必须比按钮大。
// 2. 阴影负责「层次」，边框负责「结构」。卡片用阴影，分隔线/输入框用边框。
// 3. 高频操作（切标签、打日志）一律不加动画，加了只会让人觉得慢。
pragma Singleton
import QtQuick 2.15
import QtQuick.Controls 2.15

QtObject {
    id: th

    // ---------- 主题切换 ----------
    // false = 珍珠白（浅色）  true = 云墨黑（深色）
    property bool dark: false

    // ---------- 字体 ----------
    readonly property string fontUI: "Microsoft YaHei UI"   // 界面正文（黑体风格）
    readonly property string fontLog: "Microsoft YaHei UI"  // 日志：黑体、清晰
    readonly property string fontMono: "Consolas"           // 需要对齐时用的等宽字体

    // ---------- 字号 ----------
    readonly property int fsBase:  13   // 正文
    readonly property int fsSmall: 12   // 次要说明
    readonly property int fsNav:   13   // 导航
    readonly property int fsBig:   26   // 状态大数字
    readonly property int fsLog:   13   // 运行日志（比原版大一档）

    // ---------- 圆角 ----------
    readonly property int rCtrl: 8    // 按钮 / 输入框
    readonly property int rCard: 14   // 卡片（= 8 + 内边距 6）
    readonly property int rTag:  5    // 小标签

    // ---------- 间距 ----------
    readonly property int spTight: 6
    readonly property int sp:      12
    readonly property int spCard:  16

    // ---------- 动效 ----------
    readonly property int  durPress:  150   // 按下的反馈时长
    readonly property real pressScale: 0.96 // 按下缩到 0.96
    readonly property int  durEnter:  300   // 首次入场
    readonly property int  stagger:   100   // 入场错开间隔

    // ---------- 配色表 ----------
    readonly property var paletteLight: ({
        "bg":        "#F7F7F5",
        "surface":   "#FFFFFF",
        "surfaceAlt":"#F1F1EE",
        "border":    "#E2E2DE",
        "divider":   "#EDEDE9",
        "fg":        "#1B1B19",
        "muted":     "#6E6E68",
        "primary":   "#2E7D74",
        "primaryHover": "#256862",
        "primaryText":  "#FFFFFF",
        "neutral":   "#EEEEEA",
        "neutralHover": "#E3E3DE",
        "neutralText":   "#1B1B19",
        "danger":    "#C9483A",
        "dangerHover":"#AE3E31",
        "dangerText": "#FFFFFF",
        "accent":    "#C97C2B",
        "ok":        "#2E7D74",
        "warn":      "#C97C2B",
        "err":       "#C9483A",
        "logBg":     "#FFFFFF",
        "logFg":     "#000000",   // 日志正文：纯黑，不再发灰
        "logTimeFg": "#6E6E68",
        "shadow":    "#14000000"
    })

    readonly property var paletteDark: ({
        "bg":        "#2A2A2C",
        "surface":   "#323236",
        "surfaceAlt":"#3A3A3F",
        "border":    "#4A4A50",
        "divider":   "#43434A",
        "fg":        "#F0F0EE",
        "muted":     "#A8A8A6",
        "primary":   "#4DBFB0",
        "primaryHover": "#6ECDC0",
        "primaryText":  "#0A2420",
        "neutral":   "#3C3C42",
        "neutralHover": "#46464D",
        "neutralText":   "#F0F0EE",
        "danger":    "#F0796C",
        "dangerHover":"#F59A8F",
        "dangerText": "#2A0E0A",
        "accent":    "#E0A855",
        "ok":        "#4DBFB0",
        "warn":      "#E0A855",
        "err":       "#F0796C",
        "logBg":     "#2A2A2C",
        "logFg":     "#E8E8E6",   // 深色底下正文改成浅色，不然看不见
        "logTimeFg": "#A8A8A6",
        "shadow":    "#40000000"
    })

    // 取一个颜色。界面里统一写 Theme.col("bg")，主题一换全都跟着变。
    function col(name) {
        var p = th.dark ? th.paletteDark : th.paletteLight;
        return (p[name] !== undefined) ? p[name] : "#000000";
    }

    // 日志级别 → 文字颜色
    function levelColor(level) {
        switch (level) {
        case "ERROR":   return th.col("err");
        case "WARNING": return th.col("warn");
        case "SUCCESS": return th.col("ok");
        case "DEBUG":   return th.col("muted");
        default:        return th.col("logFg");
        }
    }

    // 日志级别 → 中文名
    function levelLabel(level) {
        switch (level) {
        case "ERROR":   return "错误";
        case "WARNING": return "警告";
        case "SUCCESS": return "成功";
        case "DEBUG":   return "调试";
        default:        return "信息";
        }
    }
}