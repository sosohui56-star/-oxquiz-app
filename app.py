# app.py

import os
from datetime import datetime, timedelta
import csv
import re
import json

import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials

USER_DATA_DIR = "user_data"
os.makedirs(USER_DATA_DIR, exist_ok=True)

def get_safe_filename(name: str) -> str:
    return re.sub(r"[^\w]", "_", name)

def validate_session_keys(keys):
    for key in keys:
        if key not in st.session_state:
            if key == "wrong_list":
                st.session_state[key] = []
            elif key in ("score", "total"):
                st.session_state[key] = 0
            else:
                st.session_state[key] = None

def update_question_rating(file_path: str, question_id: str, rating: str) -> None:
    try:
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            if "rating" not in df.columns:
                df["rating"] = ""
            mask = (
                (df["question_id"] == question_id) &
                (df["rating"].isna() | (df["rating"] == ""))
            )
            if mask.any():
                df.loc[mask, "rating"] = rating
                df.to_csv(file_path, index=False)
    except Exception as e:
        st.warning(f"문제 이해도 저장 중 오류가 발생했습니다: {e}")

def get_new_question() -> None:
    df = st.session_state.df
    if df is not None and not df.empty:
        st.session_state.question = df.sample(1).iloc[0]
    else:
        st.session_state.question = None

def connect_to_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = st.secrets["GCP_CREDENTIALS"]
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

def display_weekly_ranking():
    file_path = "progress_log.csv"
    if not os.path.exists(file_path):
        st.info("아직 풀이 기록이 없습니다.")
        return
    try:
        df = pd.read_csv(file_path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    except Exception as e:
        st.warning(f"오류 발생: {e}")
        return

    now = datetime.now()
    start, end = now - timedelta(days=now.weekday()), now + timedelta(days=1)
    df_week = df[(df["timestamp"] >= start) & (df["timestamp"] < end)]

    if df_week.empty:
        st.info("이번 주에는 풀이 기록이 없습니다.")
        return

    ranking_df = (
        df_week.groupby("user_name").size().reset_index(name="풀이수")
        .sort_values(by="풀이수", ascending=False)
    )
    ranking_df["순위"] = range(1, len(ranking_df) + 1)
    st.subheader("📈 이번 주 문제풀이 랭킹")
    st.table(ranking_df[["순위", "user_name", "풀이수"]])

    user = st.session_state.user_name
    if user in ranking_df["user_name"].values:
        row = ranking_df[ranking_df["user_name"] == user].iloc[0]
        st.success(f"{user}님의 이번 주 풀이 수: {row['풀이수']}개, 순위: {row['순위']}위")

def handle_rating(rating: str, file: str, q: dict):
    update_question_rating(file, st.session_state.last_qnum, rating)
    log_to_sheet({
        "timestamp": datetime.now().isoformat(),
        "user_name": st.session_state.user_name,
        "question_id": st.session_state.last_qnum,
        "correct": st.session_state.last_correct,
        "rating": rating,
    })
    st.session_state.df = st.session_state.df[
        st.session_state.df["문제번호"] != q["문제번호"]
    ]
    get_new_question()
    st.session_state.answered = False
    st.rerun()

def main_page():
    st.sidebar.title("📁 문제 파일 업로드")
    uploaded_file = st.sidebar.file_uploader("CSV 파일 선택", type="csv")
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            st.session_state.df = df.copy()
            st.success("✅ 문제 로드 완료!")
        except Exception as e:
            st.error(f"❗ CSV 로드 실패: {e}")

    question = st.session_state.get("question")
    if question is None:
        get_new_question()
        question = st.session_state.get("question")

    if question is None:
        st.info("문제가 없습니다. 문제 파일을 확인해주세요.")
        return

    st.markdown(f"📚 단원명: {question.get('단원명','')} | 문제번호: {question.get('문제번호')}")
    st.markdown(f"❓ {question['문제']}")

    user_answer = None
    col1, col2, col3 = st.columns(3)
    if col1.button("⭕ O"):
        user_answer = "O"
    elif col2.button("❌ X"):
        user_answer = "X"
    elif col3.button("⁉️ 모름"):
        user_answer = "모름"

    if user_answer:
        st.session_state.total += 1
        correct = user_answer == question["정답"]
        st.session_state.last_question = question.copy()
        st.session_state.last_qnum = str(question.get("문제번호"))
        st.session_state.last_correct = correct
        st.session_state.answered = True

        if correct:
            st.session_state.score += 1
            st.success("✅ 정답입니다!")
        else:
            st.error(f"❌ 오답입니다. 정답은 {question['정답']}")
            st.session_state.wrong_list.append({
                "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "문제번호": question.get("문제번호"),
                "단원명": question.get("단원명", ""),
                "문제": question["문제"],
                "정답": question["정답"],
                "선택": user_answer,
                "해설": question.get("해설", "")
            })

def run_app():
    validate_session_keys(["user_name", "score", "total", "wrong_list", "df"])
    accuracy = (st.session_state.score / st.session_state.total * 100) if st.session_state.total else 0
    remaining = st.session_state.df.shape[0] if st.session_state.df is not None else 0

    main_page()

    if st.session_state.get("answered") and st.session_state.get("last_question"):
        q = st.session_state.last_question
        if "해설" in q and pd.notna(q["해설"]):
            st.info(f"📘 해설: {q['해설']}")

        c1, c2, c3 = st.columns(3)
        if c1.button("❌ 다시 보지 않기"):
            handle_rating("skip", st.session_state.get("user_progress_file", "progress.csv"), q)
        if c2.button("📘 이해 50~90%"):
            handle_rating("mid", st.session_state.get("user_progress_file", "progress.csv"), q)
        if c3.button("🔄 이해 50% 미만"):
            handle_rating("low", st.session_state.get("user_progress_file", "progress.csv"), q)

    st.sidebar.markdown("———")
    st.sidebar.markdown(f"👤 사용자: **{st.session_state.user_name}**")
    st.sidebar.markdown(f"✅ 정답 수: {st.session_state.score}")
    st.sidebar.markdown(f"❌ 오답 수: {len(st.session_state.wrong_list)}")
    st.sidebar.markdown(f"📊 총 풀어 수: {st.session_state.total}")
    st.sidebar.markdown(f"📈 정답률: {accuracy:.1f}%")
    st.sidebar.markdown(f"📘 남은 문제: {remaining}")
    st.sidebar.markdown("Made with ❤️ for 흥민's 공부")

    if st.sidebar.button("📂 오답 엑셀로 저장"):
        if st.session_state.wrong_list:
            wrong_df = pd.DataFrame(st.session_state.wrong_list)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = get_safe_filename(st.session_state.user_name)
            filename = f"{safe_name}_wrong_{ts}.xlsx"
            try:
                wrong_df.to_excel(filename, index=False)
                st.sidebar.success(f"📁 {filename} 저장 완료!")
            except Exception as e:
                st.sidebar.error(f"❗저장 중 오류 발생: {e}")
        else:
            st.sidebar.warning("❗ 오답이 없습니다.")

    if st.sidebar.button("📈 주간 랭킹 보기"):
        display_weekly_ranking()

    if st.sidebar.button("❔ 오답 목록 보기"):
        if st.session_state.wrong_list:
            df = pd.DataFrame(st.session_state.wrong_list)
            st.subheader("❗ 오답 목록")
            st.table(df[["날짜", "문제번호", "단원명", "문제", "선택", "정답", "해설"]])
        else:
            st.info("현재 오답이 없습니다.")

if __name__ == "__main__":
    run_app()
