import os
from datetime import datetime, timedelta
import csv
import re
from io import BytesIO
import json

import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials

"""
공인중개사 OX 퀴즈 애플리케이션 (기능 보완 & 안정화 버전)
- 로그인 기능
- 퀴즈 로딩 및 제출
- 오답 저장/엑셀 다운로드
- 구글 시트 기록
- 주간 랭킹 버튼 UI
- 저장소 내 문제 자동 탐색 추가
"""

USER_DATA_DIR = "user_data"
os.makedirs(USER_DATA_DIR, exist_ok=True)

REPO_CSV_FILES = [f for f in os.listdir('.') if f.endswith(".csv") and os.path.isfile(f)]

def get_safe_filename(name: str) -> str:
    return re.sub(r"[^\w]", "_", name)

def get_user_id() -> str:
    return get_safe_filename(st.session_state.user_name)

def init_session_state():
    defaults = {
        "logged_in": False,
        "user_name": "",
        "wrong_list": [],
        "score": 0,
        "total": 0,
        "answered": False,
        "question": None,
        "df": None,
        "last_correct": None,
        "last_qnum": None,
        "repeat_question": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def connect_to_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = json.loads(st.secrets["GCP_CREDENTIALS"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("oxquiz_progress_log")

def log_to_sheet(timestamp, user_name, question_id, correct, rating):
    try:
        sheet_doc = connect_to_sheet()
        sheet_title = get_safe_filename(user_name)
        try:
            worksheet = sheet_doc.worksheet(sheet_title)
        except gspread.WorksheetNotFound:
            worksheet = sheet_doc.add_worksheet(title=sheet_title, rows="1000", cols="10")
            worksheet.append_row(["날짜", "사용자", "문제번호", "정오답", "이해도"])
        worksheet.append_row([timestamp, user_name, question_id, str(correct), rating])
    except Exception as e:
        st.warning(f"[Google Sheets 기록 실패] {e}")

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
    user_id = get_user_id()
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="오답 목록")
    buffer.seek(0)
    st.download_button(
        label="📥 오답 엑셀 다운로드",
        data=buffer,
        file_name=f"oxquiz_wrong_list_{user_id}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    df.to_csv(os.path.join(USER_DATA_DIR, f"wrong_list_{user_id}.csv"), index=False)

def display_weekly_ranking():
    st.subheader("📈 주간 랭킹")
    st.info("이 기능은 아직 구현 중입니다.")

init_session_state()

if not st.session_state.logged_in:
    st.title("🔐 이름을 입력하고 시작하세요")
    name = st.text_input("이름 입력")
    if st.button("로그인") and name:
        st.session_state.user_name = name
        st.session_state.logged_in = True
        st.rerun()
    st.stop()

st.sidebar.header("📁 메뉴")
st.sidebar.write("👤 ", st.session_state.user_name)
if st.sidebar.button("📈 주간 랭킹 보기"):
    display_weekly_ranking()
if st.sidebar.button("❔ 오답 목록 보기"):
    show_wrong_list_table()
if st.sidebar.button("📂 오답 엑셀로 저장"):
    save_wrong_list_to_excel()

st.sidebar.markdown("---")
quiz_file = st.sidebar.file_uploader("문제 파일 업로드 (CSV)", type=["csv"])
selected_repo_file = st.sidebar.selectbox("또는 저장소 문제 선택", ["(선택안함)"] + REPO_CSV_FILES)

try:
    if quiz_file:
        df = pd.read_csv(quiz_file)
        source = "업로드한 파일"
    elif selected_repo_file != "(선택안함)":
        df = pd.read_csv(selected_repo_file)
        source = f"{selected_repo_file} (저장소)"
    else:
        st.warning("문제를 업로드하거나 저장소에서 선택하세요.")
        st.stop()

    df.columns = df.columns.str.strip()
    required_cols = {"문제번호", "문제", "정답"}
    if not required_cols.issubset(set(df.columns)):
        st.error(f"필수 컬럼 누락: {required_cols - set(df.columns)}")
        st.stop()

    st.session_state.df = df
    st.success(f"{source}에서 문제 {len(df)}개 불러옴")

except Exception as e:
    st.error(f"CSV 불러오기 실패: {e}")
    st.stop()

chapters = sorted(df['단원명'].dropna().unique())
selected_chapter = st.sidebar.selectbox("🔍 단원 선택", ["전체"] + chapters)
if selected_chapter != "전체":
    df = df[df['단원명'] == selected_chapter]
if df.empty:
    st.warning("선택한 단원의 문제가 없습니다.")
    st.stop()

if st.sidebar.button("📊 단원별 정답률 보기"):
    full_df = st.session_state.df
    if full_df is not None:
        summary_df = pd.DataFrame(st.session_state.wrong_list)
        summary_df['맞춤여부'] = False
        correct_ids = list(set(full_df['문제번호']) - set(summary_df['문제번호']))
        correct_df = full_df[full_df['문제번호'].isin(correct_ids)].copy()
        correct_df['맞춤여부'] = True
        correct_df = correct_df[['문제번호', '단원명', '맞춤여부']]
        summary_df = summary_df[['문제번호', '단원명', '맞춤여부']].copy()
        summary_all = pd.concat([summary_df, correct_df], ignore_index=True)
        result = summary_all.groupby('단원명')['맞춤여부'].agg(["count", "sum"])
        result.columns = ["총문제수", "정답수"]
        result["정답률"] = (result["정답수"] / result["총문제수"] * 100).round(1)
        st.subheader("📊 단원별 정답률 요약")
        st.dataframe(result.reset_index())

if not st.session_state.answered:
    # 반복 출제할 문제 우선 사용
    if st.session_state.repeat_question:
        question = st.session_state.repeat_question
        st.session_state.repeat_question = None
    else:
        if "question" not in st.session_state or st.session_state.answered:
            question = df.sample(1).iloc[0]
            st.session_state.question = question
        else:
            question = st.session_state.question

    if question is None or not isinstance(question, pd.Series):
        st.error("문제를 불러오지 못했습니다. CSV 형식이 올바른지 확인하세요.")
        st.stop()

    st.session_state.last_qnum = question.get('문제번호', '알수없음')
    st.write(f"### 문제 {question.get('문제번호', '?')}: {question.get('문제', '질문 없음')}")
    user_choice = st.radio("정답을 선택하세요", ["O", "X"])

    if st.button("제출"):
        correct = (user_choice == question.get('정답', ''))
        st.session_state.answered = True
        st.session_state.last_correct = correct
        st.session_state.score += int(correct)
        st.session_state.total += 1

        if not correct:
            wrong_entry = question.to_dict()
            wrong_entry["날짜"] = datetime.now().strftime("%Y-%m-%d")
            wrong_entry["선택"] = user_choice
            st.session_state.wrong_list.append(wrong_entry)

        st.rerun()
