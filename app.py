import os
from datetime import datetime, timedelta
import csv
import re
import json

import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO

"""
공인중개사 OX 퀴즈 애플리케이션 (기능 보완 & 안정화 버전)

- 로그인 기능
- 퀴즈 로딩 및 제출
- 오답 저장/엑셀 다운로드
- 구글 시트 기록
- 주간 랭킹 버튼 UI
"""

# 디렉터리 설정
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

def record_user_activity():
    file_path = "progress_log.csv"
    header = ["user_name", "timestamp"]
    try:
        if not os.path.exists(file_path):
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header)
        with open(file_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([st.session_state.user_name, datetime.now().isoformat()])
    except Exception as e:
        st.warning(f"기록 파일에 저장하는 중 오류가 발생했습니다: {e}")

def connect_to_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = json.loads(st.secrets["GCP_CREDENTIALS"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("oxquiz_progress_log").worksheet("시트1")

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

def show_wrong_list_table():
    if st.session_state.wrong_list:
        df = pd.DataFrame(st.session_state.wrong_list)
        st.subheader("❗ 오답 목록")
        st.table(df[["날짜", "문제번호", "단원명", "문제", "선택", "정답", "해설"]])

def save_wrong_list_to_excel():
    if not st.session_state.wrong_list:
        st.warning("저장할 오답이 없습니다.")
        return

    df = pd.DataFrame(st.session_state.wrong_list)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="오답 목록")
    buffer.seek(0)

    st.download_button(
        label="📥 오답 엑셀 다운로드",
        data=buffer,
        file_name="oxquiz_wrong_list.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def evaluate_rating(correct: bool) -> str:
    return "high" if correct else "low"

def process_answer(user_answer: str):
    question = st.session_state.question
    if not question:
        st.warning("문제가 비어 있습니다.")
        return
    correct = question["정답"] == user_answer
    st.session_state.last_correct = correct
    st.session_state.answered = True
    st.session_state.score += int(correct)
    st.session_state.total += 1
    log_to_sheet({
        "timestamp": datetime.now().isoformat(),
        "user_name": st.session_state.user_name,
        "question_id": question["문제번호"],
        "correct": correct,
        "rating": evaluate_rating(correct)
    })
    if not correct:
        st.session_state.wrong_list.append(question)

def display_weekly_ranking():
    st.subheader("📈 주간 랭킹")
    st.info("이 기능은 아직 구현 중입니다.")

# 로그인 UI
init_session_state()

if not st.session_state.logged_in:
    st.title("🔐 이름을 입력하고 시작하세요")
    name = st.text_input("이름 입력")
    if st.button("로그인") and name:
        st.session_state.user_name = name
        st.session_state.logged_in = True
        record_user_activity()
        st.experimental_rerun()
    st.stop()

# 문제 파일 업로드
st.sidebar.header("📁 파일 업로드")
quiz_file = st.sidebar.file_uploader("문제 파일 업로드 (CSV)", type=["csv"])

if quiz_file:
    df = pd.read_csv(quiz_file)
    st.session_state.df = df
    st.success(f"문제 {len(df)}개 불러옴")

    if not st.session_state.answered:
        question = df.sample(1).iloc[0]
        st.session_state.question = question
        st.write(f"### 문제: {question['문제']}")
        choice = st.radio("선택", ["O", "X"])
        if st.button("제출"):
            process_answer(choice)
            st.experimental_rerun()
    else:
        if st.session_state.last_correct:
            st.success("정답입니다!")
        else:
            st.error("오답입니다.")
        if st.button("다음 문제"):
            st.session_state.answered = False
            st.experimental_rerun()

# 사이드바 버튼 UI
if st.sidebar.button("📈 주간 랭킹 보기"):
    display_weekly_ranking()

if st.sidebar.button("❔ 오답 목록 보기"):
    show_wrong_list_table()

if st.sidebar.button("📂 오답 엑셀로 저장"):
    save_wrong_list_to_excel()
