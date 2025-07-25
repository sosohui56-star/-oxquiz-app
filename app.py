import streamlit as st
import pandas as pd
import os
import random
import datetime

# 기본 설정
st.set_page_config(page_title="공인중개사 OX 퀴즈", layout="centered")
st.title("📘 공인중개사 OX 퀴즈")

# ✅ 사용자 인증 단계
st.sidebar.header("🔐 사용자 인증")
name = st.sidebar.text_input("이름을 입력하세요")
group = st.sidebar.text_input("소속을 입력하세요")
password = st.sidebar.text_input("비밀번호를 입력하세요", type="password")
correct_password = "minbeob123"  # 🔑 너가 정한 비번

authenticated = False
if name and group and password:
    if password == correct_password:
        st.sidebar.success(f"✔️ 인증 성공: {group}의 {name}님")
        authenticated = True
    else:
        st.sidebar.error("❌ 비밀번호가 틀렸습니다.")

# ✅ 인증 성공 시 퀴즈 실행
if authenticated:
    st.sidebar.header("📂 문제집 선택")
    csv_files = [f for f in os.listdir() if f.endswith(".csv")]
    selected_file = st.sidebar.selectbox("사용할 파일을 선택하세요", csv_files)

    # 오답 저장 딕셔너리
    if "wrong_answers" not in st.session_state:
        st.session_state.wrong_answers = []
    if "history" not in st.session_state:
        st.session_state.history = []
    if "score" not in st.session_state:
        st.session_state.score = {"correct": 0, "total": 0}

    if selected_file:
        df = pd.read_csv(selected_file)

        # 단원 선택
        chapters = df["단원명"].dropna().unique().tolist()
        selected_chapter = st.sidebar.selectbox("🔎 단원을 선택하세요 (전체 보기 원하면 선택 안함)", ["전체"] + chapters)

        # 문제 필터링
        if selected_chapter != "전체":
            df = df[df["단원명"] == selected_chapter]

        if not df.empty:
            question = df.sample(1).iloc[0]
            st.markdown(f"📚 단원명: {question['단원명']} | 문제번호: {question['문제번호']}")
            st.markdown(f"❓ {question['문제']}")
            choice = st.radio("정답을 선택하세요", ["O", "X", "모름"], horizontal=True)

            if st.button("제출"):
                st.session_state.score["total"] += 1
                st.session_state.history.append({"문제": question["문제"], "정답": question["정답"]})

                if choice == question["정답"]:
                    st.session_state.score["correct"] += 1
                    st.success("🎉 정답입니다!")
                elif choice == "모름":
                    st.warning("⁉️ 모름을 선택했어요. 다음 문제도 도전해보세요!")
                else:
                    st.error(f"❌ 오답입니다. 정답은 {question['정답']}입니다.")
                    st.info(f"📘 해설: {question['해설']}")
                    st.session_state.wrong_answers.append(question)

        # 통계 표시
        correct = st.session_state.score["correct"]
        total = st.session_state.score["total"]
        st.sidebar.markdown(f"📊 정답률: **{correct} / {total} ({(correct/total*100):.1f}%)**")

        # 🎮 점수 배지
        if total >= 30:
            st.sidebar.success("🥇 당신은 문제풀이 마스터!")
        elif total >= 20:
            st.sidebar.info("🥈 실력자!")
        elif total >= 10:
            st.sidebar.info("🥉 초보탈출!")

        # 🔁 오답 반복 학습
        if st.sidebar.button("🔁 오답 복습 시작") and st.session_state.wrong_answers:
            wrong_df = pd.DataFrame(st.session_state.wrong_answers)
            st.subheader("🔁 오답 복습 모드")
            wq = wrong_df.sample(1).iloc[0]
            st.markdown(f"❌ 틀린 문제 다시풀기: {wq['문제']}")
            retry = st.radio("정답을 선택하세요", ["O", "X", "모름"], key="retry")
            if st.button("다시 제출"):
                if retry == wq["정답"]:
                    st.success("🎉 정답입니다! 복습 성공!")
                    st.session_state.wrong_answers.remove(wq)
                else:
                    st.error(f"❌ 오답입니다. 정답은 {wq['정답']}입니다.")
                    st.info(f"📘 해설: {wq['해설']}")

    st.markdown("---")
    st.markdown("Made with ❤️ for 공인중개사 수험생")
else:
    st.warning("👆 사이드바에 이름/소속/비밀번호를 모두 입력하세요")
