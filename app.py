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

# 디렉터리 초기화
USER_DATA_DIR = "user_data"
os.makedirs(USER_DATA_DIR, exist_ok=True)

def get_safe_filename(name: str) -> str:
    return re.sub(r"[^\w]", "_", name)

def validate_session_keys(keys):
    for key in keys:
        if key not in st.session_state:
            if key in ("wrong_list",):
                st.session_state[key] = []
            elif key in ("score", "total"):
                st.session_state[key] = 0
            else:
                st.session_state[key] = None

def handle_rating(rating: str, user_progress_file: str, question: dict) -> None:
    update_question_rating(user_progress_file, st.session_state.last_qnum, rating)
    log_to_sheet({
        "timestamp": datetime.now().isoformat(),
        "user_name": st.session_state.user_name,
        "question_id": st.session_state.last_qnum,
        "correct": st.session_state.last_correct,
        "rating": rating,
    })
    st.session_state.df = st.session_state.df[
        st.session_state.df["문제번호"] != question["문제번호"]
    ]
    get_new_question()
    st.session_state.answered = False
    st.rerun()

# 해설 및 평점 버튼 처리
if st.session_state.get("answered") and st.session_state.get("last_question"):
    last_q = st.session_state.last_question
    if "해설" in last_q and pd.notna(last_q["해설"]):
        st.info(f"📘 해설: {last_q['해설']}")

    col1, col2, col3 = st.columns(3)
    if col1.button("❌ 다시 보지 않기"):
        handle_rating("skip", user_progress_file, last_q)
    if col2.button("📘 이해 50~90%"):
        handle_rating("mid", user_progress_file, last_q)
    if col3.button("🔄 이해 50% 미만"):
        handle_rating("low", user_progress_file, last_q)

# 사이드바 요약 표시 (정확한 변수명 사용)
validate_session_keys(["user_name", "score", "total", "wrong_list", "df"])
accuracy = (st.session_state.score / st.session_state.total * 100) if st.session_state.total > 0 else 0
remaining = st.session_state.df.shape[0] if st.session_state.df is not None else 0

st.sidebar.markdown("———")
st.sidebar.markdown(f"👤 사용자: **{st.session_state.user_name}**")
st.sidebar.markdown(f"✅ 정답 수: {st.session_state.score}")
st.sidebar.markdown(f"❌ 오답 수: {len(st.session_state.wrong_list)}")
st.sidebar.markdown(f"📊 총 풀어 수: {st.session_state.total}")
st.sidebar.markdown(f"📈 정답률: {accuracy:.1f}%")
st.sidebar.markdown(f"📘 남은 문제: {remaining}")
st.sidebar.markdown("Made with ❤️ for 흥민's 공부")

# 오답 저장 버튼
if st.sidebar.button("📂 오답 엑셀로 저장"):
    if st.session_state.wrong_list:
        wrong_df = pd.DataFrame(st.session_state.wrong_list)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = get_safe_filename(st.session_state.user_name)
        filename = f"{safe_name}_wrong_{timestamp_str}.xlsx"
        display_name = f"{st.session_state.user_name}_오답_{timestamp_str}.xlsx"
        try:
            wrong_df.to_excel(filename, index=False)
            st.sidebar.success(f"📁 {display_name} 파일로 저장 완료!")
        except Exception as e:
            st.sidebar.error(f"❗엑셀 파일을 저장하는 중 오류 발생: {e}")
    else:
        st.sidebar.warning("❗ 오답이 없습니다.")

# 주간 랭킹 / 오답 리스트 버튼
if st.sidebar.button("📈 주간 랭킹 보기"):
    display_weekly_ranking()

if st.sidebar.button("❔ 오답 목록 보기"):
    if st.session_state.wrong_list:
        wrong_df = pd.DataFrame(st.session_state.wrong_list)
        st.subheader("❗ 오답 목록")
        st.table(wrong_df[["날짜", "문제번호", "단원명", "문제", "선택", "정답", "해설"]])
    else:
        st.info("현재 오답이 없습니다.")
