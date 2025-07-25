import streamlit as st
import pandas as pd
import os
import random
from datetime import datetime

st.set_page_config(page_title="📘 공인중개사 OX 퀴즈", layout="centered")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_name' not in st.session_state:
    st.session_state.user_name = ""
if 'wrong_list' not in st.session_state:
    st.session_state.wrong_list = []
if 'score' not in st.session_state:
    st.session_state.score = 0
if 'total' not in st.session_state:
    st.session_state.total = 0

if not st.session_state.logged_in:
    st.title("🔐 사용자 로그인")
    name = st.text_input("이름을 입력하세요")
    group = st.text_input("소속을 입력하세요")
    password = st.text_input("암호를 입력하세요", type="password")
    if st.button("로그인"):
        if password == "1234":
            st.session_state.logged_in = True
            st.session_state.user_name = f"{name} ({group})"
            st.success(f"🎉 환영합니다, {st.session_state.user_name}님!")
            st.rerun()
        else:
            st.error("❌ 암호가 틀렸습니다.")
    st.stop()

st.title("📘 공인중개사 OX 퀴즈")
st.sidebar.header("📂 문제집 선택")

csv_files = [f for f in os.listdir() if f.endswith(".csv")]
selected_file = st.sidebar.selectbox("사용할 파일을 선택하세요", csv_files)

if selected_file:
    df = pd.read_csv(selected_file)
    df = df.dropna(subset=["문제", "정답"])

    chapters = sorted(df["단원명"].dropna().unique())
    selected_chapter = st.sidebar.selectbox("특정 단원만 푸시겠습니까?", ["전체 보기"] + list(chapters))
    if selected_chapter != "전체 보기":
        df = df[df["단원명"] == selected_chapter]

    if not df.empty:
        question = df.sample(1).iloc[0]
        st.markdown(f"📚 단원명: {question['단원명']} | 문제번호: {int(question['문제번호'])}")
        st.markdown(f"❓ {question['문제']}")
        col1, col2, col3 = st.columns(3)
        if col1.button("⭕ O"):
            user_answer = "O"
        elif col2.button("❌ X"):
            user_answer = "X"
        elif col3.button("⁉️ 모름"):
            user_answer = "모름"
        else:
            user_answer = None

if user_answer:
    st.session_state.total += 1
    if user_answer == question["정답"]:
        st.session_state.score += 1
        st.success("✅ 정답입니다!")
        st.info(f"📘 해설: {question['해설']}")
    else:
        st.session_state.wrong_list.append({
            "이름": st.session_state.user_name,
            "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "문제번호": int(question["문제번호"]),
            "단원명": question["단원명"],
            "문제": question["문제"],
            "정답": question["정답"],
            "선택": user_answer,
            "해설": question["해설"]
        })
        st.error(f"❌ 오답입니다. 정답은 {question['정답']}")
        st.info(f"📘 해설: {question['해설']}")

    if st.button("👉 다음 문제"):
        st.session_state.question = df.sample(1).iloc[0]
        st.session_state.answered = False
        st.experimental_rerun()

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"👤 사용자: **{st.session_state.user_name}**")
    st.sidebar.markdown(f"✅ 정답 수: {st.session_state.score}")
    st.sidebar.markdown(f"❌ 오답 수: {len(st.session_state.wrong_list)}")
    st.sidebar.markdown(f"📊 총 풀이 수: {st.session_state.total}")
    st.sidebar.markdown("Made with ❤️ for 공인중개사 수험생")

    if st.sidebar.button("🗂️ 오답 엑셀로 저장"):
        if st.session_state.wrong_list:
            wrong_df = pd.DataFrame(st.session_state.wrong_list)
            filename = f"{st.session_state.user_name}_오답_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            wrong_df.to_excel(filename, index=False)
            st.sidebar.success(f"📁 {filename} 저장 완료!")
        else:
            st.sidebar.warning("❗ 오답이 없습니다.")
else:
    st.warning("⚠️ CSV 문제 파일을 업로드하세요.")
