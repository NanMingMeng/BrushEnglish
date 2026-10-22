// 通用按钮：主色 / 灰色 / 危险红 / 透明四种样子。
// 手感规矩：按下缩到 0.96，150 毫秒，松手弹回；禁用的按钮不缩放。
// 悬停变色只在「有鼠标的设备」上生效，触屏点了不会留在变色状态。
import QtQuick 2.15
import QtQuick.Controls 2.15
import BrushUI 1.0

Button {
    id: root

    property string variant: "neutral"   // primary / neutral / danger / ghost
    property string iconName: ""
    property int iconSize: 18

    focusPolicy: Qt.NoFocus

    readonly property bool _mouseHover: hover.hovered
    readonly property bool _pressed: root.pressed && root.enabled

    // 悬停检测：只认鼠标，不认手指
    HoverHandler {
        id: hover
        acceptedPointerTypes: PointerDevice.Mouse
    }

    scale: _pressed ? Theme.pressScale : 1
    Behavior on scale {
        NumberAnimation {
            duration: Theme.durPress
            easing.type: Easing.OutQuad
        }
    }

    function bgColor() {
        if (!root.enabled) return Theme.col("surfaceAlt");
        if (variant === "primary")
            return (_mouseHover ? Theme.col("primaryHover") : Theme.col("primary"));
        if (variant === "danger")
            return (_mouseHover ? Theme.col("dangerHover") : Theme.col("danger"));
        if (variant === "ghost")
            return (_mouseHover ? Theme.col("neutral") : "transparent");
        return (_mouseHover ? Theme.col("neutralHover") : Theme.col("neutral"));
    }

    function fgColor() {
        if (!root.enabled) return Theme.col("muted");
        if (variant === "primary") return Theme.col("primaryText");
        if (variant === "danger")  return Theme.col("dangerText");
        return Theme.col("neutralText");
    }

    background: Rectangle {
        radius: Theme.rCtrl
        color: root.bgColor()
        border.width: (variant === "ghost") ? 0 : 1
        border.color: Theme.col("border")

        // 只过渡颜色，不写 transition: all
        Behavior on color {
            ColorAnimation { duration: 120 }
        }
    }

    contentItem: Row {
        spacing: 6
        leftPadding: 10
        rightPadding: 10

        SvgIcon {
            name: root.iconName
            color: root.fgColor()
            size: root.iconSize
            anchors.verticalCenter: parent.verticalCenter
        }

        Label {
            text: root.text
            color: root.fgColor()
            font.family: Theme.fontUI
            font.pixelSize: Theme.fsBase
            anchors.verticalCenter: parent.verticalCenter
            visible: text.length > 0
        }
    }

    ToolTip.visible: (root.toolTip || "").length > 0 && hover.hovered
    ToolTip.text: root.toolTip || ""
    ToolTip.delay: 500
}