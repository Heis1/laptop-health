from __future__ import annotations

BG_MAIN = "#0b1220"
BG_SIDEBAR = "#0f1a2b"
BG_CARD = "#101b2c"
BORDER = "#1a2a41"

TEXT = "#e8f0ff"
TEXT_MID = "#cfe0ff"
TEXT_MUTED = "#9fb0c6"

ACCENT = {
    "green":  "#34d399",
    "blue":   "#60a5fa",
    "orange": "#fb923c",
    "red":    "#f87171",
    "purple": "#a78bfa",
}

def qss() -> str:
    return f"""
    QMainWindow {{
        background: {BG_MAIN};
    }}

    #Sidebar {{
        background: {BG_SIDEBAR};
        border: 1px solid #1c2a3f;
        border-radius: 18px;
    }}
    #AppTitle {{
        color: {TEXT};
        font-size: 18px;
        font-weight: 800;
    }}
    #NavBtn, #NavBtnSecondary {{
        background: #12223a;
        color: #d7e3f4;
        border: 1px solid #1c2f4a;
        border-radius: 14px;
        padding: 10px 12px;
        text-align: left;
        font-size: 13px;
    }}
    #NavBtn:hover, #NavBtnSecondary:hover {{
        background: #162b46;
    }}
    #NavBtn[active="1"] {{
        background: #1a3354;
        border: 1px solid #2a4a77;
    }}

    #PageTitle {{
        color: {TEXT};
        font-size: 22px;
        font-weight: 850;
    }}
    #TopBtn, #TopBtnIcon {{
        background: #12223a;
        color: #d7e3f4;
        border: 1px solid #1c2f4a;
        border-radius: 14px;
        padding: 10px 12px;
        font-size: 13px;
    }}
    #TopBtn:hover, #TopBtnIcon:hover {{
        background: #162b46;
    }}

    #Card {{
        background: {BG_CARD};
        border: 1px solid {BORDER};
        border-radius: 18px;
    }}
    #Card[accent="green"]  {{ border-left: 5px solid {ACCENT["green"]}; }}
    #Card[accent="blue"]   {{ border-left: 5px solid {ACCENT["blue"]}; }}
    #Card[accent="orange"] {{ border-left: 5px solid {ACCENT["orange"]}; }}
    #Card[accent="red"]    {{ border-left: 5px solid {ACCENT["red"]}; }}
    #Card[accent="purple"] {{ border-left: 5px solid {ACCENT["purple"]}; }}

    #CardTitle {{
        color: {TEXT_MID};
        font-size: 14px;
        font-weight: 700;
    }}
    #CardBig {{
        color: #ffffff;
        font-size: 34px;
        font-weight: 900;
        margin-top: 2px;
    }}
    #CardSub {{
        color: {TEXT_MUTED};
        font-size: 13px;
    }}

    #Badge {{
        background: rgba(248, 113, 113, 0.18);
        border: 1px solid rgba(248, 113, 113, 0.35);
        color: #ffd2d2;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 800;
    }}

    #RowLabel {{
        color: {TEXT_MUTED};
        font-size: 13px;
    }}
    #RowValue {{
        color: {TEXT};
        font-size: 13px;
        font-weight: 700;
    }}

    #InspectorToggle {{
        color: #d7e3f4;
        font-size: 13px;
        font-weight: 750;
        padding: 6px;
    }}
    #InspectorDots {{
        color: #89a1c2;
        font-size: 14px;
    }}
    """
