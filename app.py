import streamlit as st
import pandas as pd
import os
import random

st.set_page_config(page_title="공인중개사 OX 퀴즈", layout="centered")
st.title("📘 공인중개사 OX 퀴즈")
st.sidebar.header("📂 문제집 선택")

# 파일 선택
csv_files = [f for f in os.listdir() if f.endswith(".csv")]
selected_file = st.sidebar.selectbox("사용할 파일을 선택하세요", csv_files)

if selected_file:
    df = pd.read_csv(selected_file)
    question = df.sample(1).iloc[0]
    st.markdown(f"📚 단원명: {question['단원명']} | 문제번호: {question['문제번호']}")
    st.markdown(f"❓ {question['문제']}")

    # 버튼 세 개로 선택지 제공
    col1, col2, col3 = st.columns(3)
    user_choice = None
    with col1:
        if st.button("⭕ O"):
            user_choice = "O"
    with col2:
        if st.button("❌ X"):
            user_choice = "X"
    with col3:
        if st.button("⁉️ 모름"):
            user_choice = "모름"

    if user_choice:
        st.write("---")
        if user_choice == question["정답"]:
            st.success("🎉 정답입니다!")
        elif user_choice == "모름":
            st.warning("⁉️ 모름을 선택했어요. 다음 문제도 도전해보세요!")
        else:
            st.error(f"❌ 오답입니다. \n\n👉 해설: {question['해설']}")
