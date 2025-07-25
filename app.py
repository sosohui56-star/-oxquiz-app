import streamlit as st
import pandas as pd
import os
import random

st.set_page_config(page_title="민법 OX 퀴즈", layout="centered")
st.title("📘 공인중개사 OX 퀴즈")
st.sidebar.header("📂 문제집 선택")

# ✅ 현재 폴더 내 CSV 파일 자동 탐색
csv_files = [f for f in os.listdir() if f.endswith(".csv")]
selected_file = st.sidebar.selectbox("사용할 파일을 선택하세요", csv_files)

if selected_file:
    df = pd.read_csv(selected_file)

    # ✅ 무작위 문제 1개 선택
    question = df.sample(1).iloc[0]

    st.markdown(f"📚 단원명: {question['단원명']} | 문제번호: {int(question['문제번호'])}")
    st.markdown(f"❓ {question['문제']}")

    choice = st.radio("정답을 선택하세요", ["O", "X", "모름"], horizontal=True)

    if st.button("제출"):
        if choice == question["정답"]:
            st.success("🎉 정답입니다!")
        elif choice == "모름":
            st.warning("⁉️ 모름을 선택했어요. 다음 문제도 도전해보세요!")
        else:
            st.error(f"❌ 오답입니다. \n\n👉 해설: {question['해설']}")
