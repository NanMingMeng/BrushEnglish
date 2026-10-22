// 外壳：顶部标签栏（切换页面）+ 操作栏 + 页面内容 + 运行日志。
// 按你的要求做了三处调整：
//   1. 删掉了左侧竖排导航和「检查更新」，只留顶部标签栏这一套界面。
//   2. 原来挤在左下角的按钮，上移成独立一行操作栏，不再跟日志抢地方。
//   3. 日志挪到最下面、横向铺满，配合自动换行，不用再左右滑。
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import BrushUI 1.0
import "components"
import "pages"

ApplicationWindow {
    id: win

    visible: true
    width: 1180
    height: 760
    minimumWidth: 620        // 最窄 620，再窄按钮会挤在一起
    minimumHeight: 520
    title: "刷单词助手"

    // 主题：false = 珍珠白（浅色）  true = 云墨黑（深色）
    property bool dark: false

    // 窗口置顶：开着的话，窗口会一直浮在其他窗口上面
    property bool topMost: true

    // 随机休息 / 听音识别开关（启动时从配置恢复）
    property bool restEnabled: true
    property bool asrEnabled: true

    // 认字引擎状态
    property bool ocrOk: false
    property string ocrText: "认字引擎启动中"

    // 脚本问答：脚本调用 input() 时，这里会亮起来等用户回答
    property bool inputVisible: false
    property string inputPrompt: ""

    // 运行状态（放在顶部标签栏显示）
    property string runState: "未启动"
    property bool runActive: false
    property bool runPaused: false
    property string runRound: "—"
    property string runProgress: "—"
    property string runRuntime: "—"
    property var asrDevices: []

    // 置顶是靠给窗口加一个「始终在最前」的标记实现的
    flags: topMost ? (Qt.Window | Qt.WindowStaysOnTopHint) : Qt.Window

    // 当前页码：0=运行 1=坐标校准 2=题库
    property int pageIndex: 0

    background: Rectangle {
        color: Theme.col("bg")
    }

    // 把界面这边的主题状态同步给 Theme
    onDarkChanged: Theme.dark = dark

    Component.onCompleted: {
        // 启动时把上次存下来的偏好全部恢复：主题、置顶、认字引擎
        var s = backend.uiSettings();
        if (s) {
            dark = (s.theme === "dark");
            topMost = (s.top !== false);
        }
        // onDarkChanged 会自动把 Theme.dark 跟上

        // 按上次记住的位置和大小摆放窗口。
        // 控制层已经做过「防跑偏」校正：万一上次的位置在屏幕外
        // （比如换过显示器、拔过外接屏），会自动拉回可见范围。
        var eng2 = backend.ocrEngine();
        if (eng2 === "paddle") ocrCombo.currentIndex = 1;
        else if (eng2 === "umi") ocrCombo.currentIndex = 2;
        else ocrCombo.currentIndex = 0;

        win.asrEnabled = (backend.spellingSource() !== "wordlist");
        win.restEnabled = backend.randomBreakEnabled();

        var g = backend.windowGeometry();
        if (g && g.w > 0 && g.h > 0) {
            x = g.x;
            y = g.y;
            width = g.w;
            height = g.h;
        }

    }

    // 关窗口时记住这次的位置和大小，下次打开照着摆
    // 生成界面预览图（从 QML 内部抓图，离屏也能用，不会弹窗）
    function grabPreview(path) {
        var res = contentItem.grabToImage();
        res.ready.connect(function() {
            res.saveToFile(path);
            if (backend) backend.toast("预览图已生成");
        });
    }

    onClosing: {
        backend.saveWindowGeometry(x, y, width, height);
        backend.shutdown();
    }

    // 不透明背景层：截图和渲染都靠它铺底色
    Rectangle {
        anchors.fill: parent
        color: Theme.col("bg")

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ================= 一、顶部标签栏 =================
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            color: Theme.col("surface")

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.col("border")
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 6
                spacing: 3

                Label {
                    visible: win.width > 1000
                    text: "刷单词助手"
                    font.family: Theme.fontUI
                    font.pixelSize: Theme.fsNav
                    font.bold: true
                    color: Theme.col("fg")
                    Layout.rightMargin: 10
                }

                Repeater {
                    model: [
                        { "t": "运行", "i": "broom" },
                        { "t": win.width > 1000 ? "坐标校准" : "坐标", "i": "sliders" },
                        { "t": "题库", "i": "book" }
                    ]

                    delegate: Button {
                        id: tabBtn
                        property bool active: win.pageIndex === index
                        text: modelData.t
                        focusPolicy: Qt.NoFocus
                        checkable: false

                        onClicked: win.pageIndex = index

                        background: Rectangle {
                            color: tabBtn.active ? Theme.col("surfaceAlt") : "transparent"
                            radius: Theme.rCtrl
                        }

                        contentItem: Row {
                            spacing: 6
                            leftPadding: 8
                            rightPadding: 8
                            SvgIcon {
                                name: modelData.i
                                size: 18
                                color: tabBtn.active ? Theme.col("primary") : Theme.col("muted")
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Label {
                                text: tabBtn.text
                                font.family: Theme.fontUI
                                font.pixelSize: Theme.fsNav
                                color: tabBtn.active ? Theme.col("primary") : Theme.col("muted")
                                font.bold: tabBtn.active
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }
                }

                // 运行状态（从运行页卡片移到顶部）
                Rectangle {
                    Layout.preferredWidth: 96
                    Layout.preferredHeight: 28
                    Layout.leftMargin: 10
                    radius: Theme.rTag
                    color: Theme.col("surfaceAlt")

                    Row {
                        anchors.centerIn: parent
                        spacing: 6
                        Rectangle {
                            width: 7
                            height: 7
                            radius: 3.5
                            anchors.verticalCenter: parent.verticalCenter
                            color: {
                                if (win.runState === "运行中") return Theme.col("ok");
                                if (win.runState === "已暂停") return Theme.col("warn");
                                if (win.runState === "已停止") return Theme.col("err");
                                return Theme.col("muted");
                            }
                        }
                        Label {
                            text: win.runState
                            font.family: Theme.fontUI
                            font.pixelSize: Theme.fsSmall
                            color: Theme.col("fg")
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }

                // 运行数据：组号 / 进度 / 时长（紧凑显示）
                Label {
                    visible: win.width > 1000
                    text: "组 " + win.runRound
                    font.family: Theme.fontUI
                    font.pixelSize: Theme.fsSmall
                    color: Theme.col("muted")
                    Layout.leftMargin: 12
                }
                Label {
                    visible: win.width > 1000
                    text: win.runProgress
                    font.family: Theme.fontUI
                    font.pixelSize: Theme.fsSmall
                    color: Theme.col("fg")
                    Layout.leftMargin: 10
                }
                Label {
                    visible: win.width > 1000
                    text: win.runRuntime
                    font.family: Theme.fontMono
                    font.pixelSize: Theme.fsSmall
                    color: Theme.col("muted")
                    Layout.leftMargin: 10
                }

                Item { Layout.fillWidth: true }

                // 认字引擎
                ComboBox {
                    id: ocrCombo
                    Layout.preferredWidth: 84
                    Layout.preferredHeight: 28
                    font.family: Theme.fontUI
                    font.pixelSize: Theme.fsSmall
                    model: ["Rapid", "Paddle", "Umi"]
                    currentIndex: 0
                    onActivated: {
                        var keys = ["rapid", "paddle", "umi"];
                        backend.setOcrEngine(keys[index]);
                    }
                }
            }
        }

        // ================= 二、操作栏（上移后独立一行） =================
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            color: Theme.col("surface")

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.col("divider")
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                spacing: 8

                // 一个按钮管运行/暂停/继续，随状态自动变
                ActionButton {
                    id: mainRunBtn
                    text: win.runActive ? (win.runPaused ? "继续" : "暂停") : (win.width > 1000 ? "开始运行" : "开始")
                    iconName: win.runPaused ? "play" : (win.runActive ? "pause" : "play")
                    // 运行中显示“暂停”时标红，暂停后显示“继续”恢复灰色
                    variant: win.runActive ? (win.runPaused ? "neutral" : "danger") : "primary"
                    onClicked: {
                        if (win.runActive) {
                            backend.pause();
                        } else {
                            var err = backend.start();
                            if (err) backend.toast("启动失败：" + err);
                        }
                    }
                }

                // 随机休息开关：关掉后不再中途休息
                ActionButton {
                    id: restBtn
                    text: win.width > 1000 ? ("休息" + (checked ? "开" : "关")) : "休息"
                    variant: checked ? "neutral" : "danger"
                    checkable: true
                    checked: win.restEnabled
                    onClicked: {
                        win.restEnabled = checked;
                        backend.setRandomBreak(checked);
                    }
                }

                // 听音识别开关：关掉后拼写题只用词表顺序
                ActionButton {
                    id: asrBtn
                    text: win.width > 1000 ? ("听音" + (checked ? "开" : "关")) : "听音"
                    variant: checked ? "neutral" : "danger"
                    checkable: true
                    checked: win.asrEnabled
                    onClicked: {
                        win.asrEnabled = checked;
                        backend.setSpellingSource(checked ? "asr" : "wordlist");
                    }
                }



                Item { Layout.fillWidth: true }

                // 强制结束卡死的认字引擎并重新启动
                ActionButton {
                    text: win.width > 1150 ? "重启引擎" : "重启"
                    variant: "ghost"
                    onClicked: backend.restartOcrEngine()
                }

                // 试录识别
                ActionButton {
                    text: "试录"
                    variant: "ghost"
                    onClicked: {
                        win.asrDevices = backend.asrDevices();
                        asrResult.text = "还没录过";
                        asrDialog.open();
                    }
                }

                // 深色 / 置顶等工具按钮：统一放在下方操作栏右侧
                ActionButton {
                    text: (dark ? "浅色" : "深色")
                    variant: "ghost"
                    onClicked: {
                        dark = !dark;
                        backend.savePreference("theme", dark ? "dark" : "light");
                    }
                }

                ActionButton {
                    text: "置顶"
                    variant: "ghost"
                    checkable: true
                    checked: topMost
                    onClicked: {
                        topMost = checked;
                        backend.setTopMost(checked);
                    }
                }




            }
        }

        // ================= 三、页面内容 =================
        Item {
            Layout.fillWidth: true
            // 运行页（pageIndex=0）不需要内容区，把空间全给日志；
            // 坐标页/题库页仍然占满剩余空间。
            Layout.fillHeight: win.pageIndex !== 0
            Layout.preferredHeight: win.pageIndex === 0 ? 0 : -1
            Layout.topMargin: win.pageIndex === 0 ? 0 : 12
            Layout.leftMargin: 12
            Layout.rightMargin: 12

            StackLayout {
                anchors.fill: parent
                currentIndex: win.pageIndex

                RunPage { id: runPage }
                CoordPage { id: coordPage }
                BankPage { id: bankPage }
            }
        }

        // ================= 脚本问答条（脚本等回答时才出现） =================
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: win.inputVisible ? 52 : 0
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            Layout.topMargin: win.inputVisible ? 12 : 0
            visible: win.inputVisible
            radius: Theme.rCard
            color: Theme.col("surfaceAlt")
            border.width: 1
            border.color: Theme.col("primary")

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8

                Label {
                    text: win.inputPrompt ? ("脚本在等你回答：" + win.inputPrompt)
                                           : "脚本在等你回答（直接回车 = 用默认值）"
                    font.family: Theme.fontUI
                    font.pixelSize: Theme.fsSmall
                    color: Theme.col("fg")
                    Layout.maximumWidth: 420
                    elide: Text.ElideRight
                }

                TextField {
                    id: inputField
                    Layout.fillWidth: true
                    Layout.preferredHeight: 32
                    placeholderText: "在这里输入后按回车；直接回车 = 用默认值"
                    font.family: Theme.fontUI
                    font.pixelSize: Theme.fsSmall
                    onAccepted: backend.answerInput(text)
                }

                ActionButton {
                    text: "发送"
                    iconName: "play"
                    variant: "primary"
                    onClicked: backend.answerInput(inputField.text)
                }
            }
        }

        // ================= 四、运行日志（只在「运行」页显示） =================
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: win.pageIndex === 0
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            Layout.bottomMargin: 12

            LogView {
                id: logView
                anchors.fill: parent
                onCopyRequested: backend.copyText(text)
                onClearRequested: backend.clearLog()
            }
        }
        }
    }

    // 试录识别弹窗
    Dialog {
        id: asrDialog
        title: "音频设备选择 + 试录识别"
        modal: true
        anchors.centerIn: parent
        width: 480
        standardButtons: Dialog.Close

        ColumnLayout {
            anchors.fill: parent
            spacing: 10

            Label {
                text: "挑一个名字带「扬声器」、标着「能录系统声音」的设备，才能录到 App 读单词的声音。点「开始试录」后会录 3 秒。"
                wrapMode: Text.Wrap
                font.family: Theme.fontUI
                font.pixelSize: Theme.fsSmall
                color: Theme.col("muted")
                Layout.fillWidth: true
            }

            ComboBox {
                id: asrCombo
                Layout.fillWidth: true
                Layout.preferredHeight: 34
                font.family: Theme.fontUI
                font.pixelSize: Theme.fsSmall
                model: {
                    var out = [];
                    for (var i = 0; i < win.asrDevices.length; i++) {
                        var d = win.asrDevices[i];
                        out.push((d.loopback ? "【能录系统声音】" : "【麦克风】") + d.name);
                    }
                    return out.length ? out : ["（没检测到录音设备）"];
                }
            }

            ActionButton {
                text: "开始试录（录 3 秒）"
                iconName: "play"
                variant: "primary"
                Layout.fillWidth: true
                onClicked: {
                    var d = win.asrDevices[asrCombo.currentIndex];
                    asrResult.text = "正在录 3 秒……请让 App 读单词";
                    backend.asrTest(d ? d.name : "");
                }
            }

            Label {
                id: asrResult
                text: "还没录过"
                wrapMode: Text.Wrap
                font.family: Theme.fontUI
                font.pixelSize: Theme.fsBase
                color: Theme.col("fg")
                Layout.fillWidth: true
            }
        }
    }

    // 把控制层发来的日志转给日志视图
    Connections {
        target: backend
        function onLogLines(batch) { logView.appendBatch(batch) }
        function onLogCleared() { logView.clearAll() }
        function onGrabPreviewRequested(path) { win.grabPreview(path) }
        function onOcrStatusChanged(ok, src) {
            win.ocrOk = ok;
            win.ocrText = ok ? ("已连接 · " + src) : (src || "启动中");
        }
        function onInputRequested(prompt) {
            win.inputPrompt = prompt;
            win.inputVisible = true;
            inputField.text = "";
            inputField.forceActiveFocus();
        }
        function onInputFinished() {
            win.inputVisible = false;
            inputField.text = "";
        }
        function onStatsChanged(p) {
            win.runState = (p && p.state) ? p.state : "—";
            // 每秒用真实运行状态校正按钮，避免状态信号漏掉时按钮还显示“暂停”
            win.runActive = (p && p.running) ? true : false;
            win.runPaused = (p && p.paused) ? true : false;
            win.runRound = (p && p.round) ? String(p.round) : "—";
            win.runProgress = (p && p.progress) ? p.progress : "—";
            win.runRuntime = (p && p.runtime) ? p.runtime : "—";
        }
        function onAsrTestResult(text) {
            asrResult.text = text ? ("听到：" + text)
                                  : "什么都没听到（可能设备选错、音量太小，或模型还没下完）";
        }
        function onStateChanged(st) {
            win.runActive = (st === "starting" || st === "running" || st === "paused" || st === "cancelling");
            win.runPaused = (st === "paused");
        }
    }
}