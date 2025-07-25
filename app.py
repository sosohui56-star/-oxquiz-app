import streamlit as st
import pandas as pd
import os
import random

# 앱 설정
st.set_page_config(page_title="공인중개사 OX 퀴즈", layout="centered")
st.title("📘 공인중개사 OX 퀴즈")

# 세션 상태 초기화
if "history" not in st.session_state:
    st.session_state.history = []
if "wrong_list" not in st.session_state:
    st.session_state.wrong_list = []
if "stats" not in st.session_state:
    st.session_state.stats = {}

# 사이드바: 파일 선택 및 기능 선택
st.sidebar.header("📂 문제집 선택")
csv_files = [f for f in os.listdir() if f.endswith(".csv")]
selected_file = st.sidebar.selectbox("사용할 파일을 선택하세요", csv_files)

# 기능 선택
repeat_wrong = st.sidebar.checkbox("🔁 오답 반복 학습 모드")
show_stats = st.sidebar.checkbox("📅 진도 통계 보기")

# 진도 현황 표시
if show_stats and st.session_state.stats:
    st.sidebar.subheader("📊 단원별 정답/오답")
    stats_df = pd.DataFrame(st.session_state.stats).T.fillna(0).astype(int)
    stats_df.columns = ["정답 수", "오답 수"]
    st.sidebar.dataframe(stats_df)

# 퀴즈 실행
if selected_file:
    df = pd.read_csv(selected_file)

    # 반복 모드일 경우 오답 리스트만
    if repeat_wrong and st.session_state.wrong_list:
        df = df[df['문제번호'].isin(st.session_state.wrong_list)]

    if len(df) == 0:
        st.warning("출제할 문제가 없습니다.")
    else:
        question = df.sample(1).iloc[0]
        st.markdown(f"📚 단원명: {question['단원명']} | 문제번호: {question['문제번호']}")
        st.markdown(f"❓ {question['문제']}")

        choice = st.radio("정답을 선택하세요", ["O", "X", "모름"], horizontal=True)

        if st.button("제출"):
            unit = question['단원명']
            qnum = question['문제번호']
            answer = question['정답']
            expl = question['해설']

            # 진도 집계
            if unit not in st.session_state.stats:
                st.session_state.stats[unit] = [0, 0]

            if choice == answer:
                st.success("🎉 정답입니다!")
                st.session_state.stats[unit][0] += 1
                if qnum in st.session_state.wrong_list:
                    st.session_state.wrong_list.remove(qnum)
            elif choice == "모름":
                st.warning("⁉️ 모름을 선택했어요. 다음 문제도 도전해보세요!")
            else:
                st.error(f"❌ 오답입니다. 정답: {answer}\n👉 해설: {expl}")
                st.session_state.stats[unit][1] += 1
                if qnum not in st.session_state.wrong_list:
                    st.session_state.wrong_list.append(qnum)

            st.session_state.history.append(qnum)

# 푼 문제 수에 따른 배지 표시
total_answered = len(st.session_state.history)
if total_answered >= 50:
    st.sidebar.success("🥇 50문제 달성! 고수 인정")
elif total_answered >= 30:
    st.sidebar.success("🥈 30문제 돌파! 중수 등극")
elif total_answered >= 10:
    st.sidebar.success("🥉 10문제 완료! 초심자 탈출")

# 앱 하단
st.markdown("---")
st.markdown("Made with ❤️ for 공인중개사 수험생")
