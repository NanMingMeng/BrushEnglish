// SVG 图标：24x24 网格上的简笔路径，颜色跟着主题走（不用表情符号当图标）。
// 图标的线条粗细跟着旁边文字的粗细走：正文用 1.75，粗体标题用 2.2。
import QtQuick 2.15
import QtQuick.Shapes 1.15

Item {
    id: root

    property string name: ""
    property color color: Theme.col("fg")
    property int size: 18
    property real strokeWidth: 1.75

    width: size
    height: size

    readonly property var icons: {
        "play":    { "p": "M8 5.5 19 12 8 18.5Z", "f": true },
        "pause":   { "p": "M9 5v14M15 5v14", "f": false },
        "stop":    { "p": "M6.5 6.5h11v11h-11Z", "f": true },
        "broom":   { "p": "M12 3.5v7M8 10.5h8l-1.5 9h-5ZM8 10.5 4.5 16M16 10.5l3.5 5.5", "f": false },
        "sliders": { "p": "M4 7h6M14 7h6M4 12h10M18 12h2M4 17h3M11 17h9", "f": false },
        "book":    { "p": "M4.5 5.5A2 2 0 0 1 6.5 3.5H19v17H6.5a2 2 0 0 1-2-2Z", "f": false },
        "folder":  { "p": "M3 7.5A2 2 0 0 1 5 5.5h3.2l1.8 2H19a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z", "f": false },
        "save":    { "p": "M5 3.5h11L19.5 7v13.5H5ZM9 3.5v6h7v-6", "f": false },
        "refresh": { "p": "M20 12a8 8 0 1 1-2.3-5.6M20 4.5V10h-5.5", "f": false },
        "sun":     { "p": "M12 7.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9ZM12 2v2M12 20v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2 12h2M20 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4", "f": false },
        "moon":    { "p": "M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z", "f": false },
        "undo":    { "p": "M9.5 14.5 4.5 9.5l5-5M4.5 9.5h10a5 5 0 0 1 0 10h-4", "f": false },
        "gauge":   { "p": "M12 20a8 8 0 1 1 8-8M12 12l4.5-3", "f": false },
        "list":    { "p": "M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01", "f": false },
        "file":    { "p": "M14 3.5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5ZM14 3.5v5h5", "f": false },
        "rows":    { "p": "M3 5.5h18v13H3ZM3 10.5h18", "f": false },
        "columns": { "p": "M3 5.5h18v13H3ZM9.5 5.5v13", "f": false },
        "pin":     { "p": "M12 20V4.5M6.5 10 12 4.5 17.5 10", "f": false },
        "eye":     { "p": "M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z", "f": false },
        "clock":   { "p": "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17ZM12 7.5V12l3 2", "f": false },
        "sound":   { "p": "M4 9.5h3.5L12 6v12l-4.5-3.5H4ZM15.5 9a4.5 4.5 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11", "f": false },
        "search":  { "p": "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14ZM16.5 16.5 21 21", "f": false }
    }

    readonly property var def: icons[name] || null

    Shape {
        anchors.fill: parent
        visible: root.def !== null
        vendorExtensionsEnabled: false

        ShapePath {
            strokeColor: root.color
            strokeWidth: root.strokeWidth
            fillColor: (root.def && root.def.f) ? root.color : "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin

            PathSvg {
                path: (root.def && root.def.p) ? root.def.p : ""
            }
        }
    }
}