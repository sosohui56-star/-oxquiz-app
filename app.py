# app.py

import streamlit as st
import pandas as pd
import random

# 사이드바에서 CSV 파일 업로드
uploaded_file = st.sidebar.file_uploader("CSV 파일을 업로드하세요", type="csv")

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    df = df.dropna(subset=['문제', '정답'])

    # 문제 하나 무작위로 선택
    question = df.sample(1).iloc[0]
    
    st.markdown(f"### 📚 단원명: {question['단원명']} | 문제번호: {question['문제번호']}")
    st.markdown(f"### ❓ {question['문제']}")

    # 버튼 3개: O / X / 모름
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("✅ O"):
            user_answer = "O"
    with col2:
        if st.button("❌ X"):
            user_answer = "X"
    with col3:
        if st.button("⁉️ 모름"):
            user_answer = "모름"

    # 정답 비교 후 출력
    if 'user_answer' in locals():
        if user_answer.upper() == question['정답'].strip().upper():
            st.success("🎉 정답입니다!")
        else:
            st.error(f"❌ 오답입니다. 정답: {question['정답']}")
        st.markdown(f"📘 해설: {question['해설']}")
else:
    st.info("왼쪽에서 CSV 파일을 업로드해주세요.")
