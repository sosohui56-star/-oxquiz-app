import os
from datetime import datetime
import csv
import re
import pandas as pd
import streamlit as st
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO

# 초기 설정
USER_DATA_DIR = "user_data"
os.makedirs(USER_DATA_DIR, exist_ok=True)

def get_safe_filename(name: str) -> str:
    return re.sub(r"[^\w]", "_", name)

def init_session_state():
    defaults = {
        "logged_in": False,
        "user_name": "",
        "wrong_list": [],
        "score": 0,
        "total": 0,
        "answered": False,
        "question": None,
        "last_question": None,
        "df": None,
        "prev_selected_file": None,
        "prev_selected_chapter": None,
        "is_admin": False,
        "last_correct": None,
        "last_qnum": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def show_wrong_list_table():
    if st.session_state.wrong_list:
        wrong_df = pd.DataFrame(st.session_state.wrong_list)
        st.subheader("❗ 오답 목록")
        st.table(
            wrong_df[["날짜", "문제번호", "단원명", "문제", "선택", "정답", "해설"]]
        )

def save_wrong_list_to_excel():
    if not st.session_state.wrong_list:
        st.warning("저장할 오답이 없습니다.")
        return

    df = pd.DataFrame(st.session_state.wrong_list)
    filtered_df = df[["날짜", "문제번호", "단원명", "문제", "선택", "정답", "해설"]]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        filtered_df.to_excel(writer, index=False, sheet_name="오답 목록")
    output.seek(0)

    st.download_button(
        label="📥 오답 엑셀 다운로드",
        data=output,
        file_name="oxquiz_wrong_list.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def connect_to_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = json.loads(st.secrets["GCP_CREDENTIALS"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("oxquiz_progress_log").worksheet("시트1")
    return sheet

def log_to_sheet(data: dict):
    try:
        sheet = connect_to_sheet()
        row = [
            data.get("timestamp"),
            data.get("user_name"),
            data.get("question_id"),
            data.get("correct"),
            data.get("rating"),
        ]
        sheet.append_row(row)
    except Exception as e:
        st.warning(f"📛 구글 시트 기록 실패: {e}")

def evaluate_rating(correct: bool) -> str:
    return "high" if correct else "low"

def process_answer(user_answer: str):
    question = st.session_state.question
    correct = question["정답"] == user_answer
    rating = evaluate_rating(correct)
    st.session_state.last_correct = correct

    log_to_sheet({
        "timestamp": datetime.now().isoformat(),
        "user_name": st.session_state.user_name,
        "question_id": question["문제번호"],
        "correct": correct,
        "rating": rating
    })

# Streamlit 사이드바 버튼 처리
if st.sidebar.button("📈 주간 랭킹 보기"):
    display_weekly_ranking()

if st.sidebar.button("❔ 오답 목록 보기"):
    show_wrong_list_table()

if st.sidebar.button("📂 오답 엑셀로 저장"):
    save_wrong_list_to_excel()
