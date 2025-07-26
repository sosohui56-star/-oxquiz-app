import os
from datetime import datetime, timedelta
import csv

import pandas as pd
import streamlit as st


"""공인중개사 OX 퀴즈 애플리케이션

CSV 문제집을 읽어 OX 퀴즈를 출제하고,
사용자의 답안을 채점하여 오답 목록을 저장합니다.

**주요 기능**
- 사용자가 문제를 풀 때마다 `progress_log.csv`에 이름과 시간을 기록하여 주간 랭킹을 계산합니다.
- 모든 사용자가 주간 랭킹을 확인할 수 있습니다.
- 소속을 '관리자' 또는 'admin'으로 입력하거나 비밀번호를 'admin'으로 입력하면 `is_admin` 플래그가 True가 됩니다(다른 관리 기능 확장 가능).
- 한 번 풀었던 문제는 세션 내에서 데이터프레임에서 제거하여 다시 나오지 않도록 합니다.
"""

def init_session_state() -> None:
    """세션 상태 초기화."""
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
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def record_user_activity() -> None:
    """문제 풀이 활동을 CSV 파일에 기록합니다."""
    file_path = "progress_log.csv"
    header = ["user_name", "timestamp"]
    if not os.path.exists(file_path):
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
    with open(file_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([st.session_state.user_name, datetime.now().isoformat()])


def display_weekly_ranking() -> None:
    """주간 랭킹을 계산하여 전체 사용자에게 표시합니다."""
    file_path = "progress_log.csv"
    if not os.path.exists(file_path):
        st.info("아직 풀이 기록이 없습니다.")
        return

    df = pd.read_csv(file_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    now = datetime.now()
    start_of_week = now - timedelta(days=now.weekday())
    end_of_week = start_of_week + timedelta(days=7)

    df_week = df[(df["timestamp"] >= start_of_week) & (df["timestamp"] < end_of_week)]
    if df_week.empty:
        st.info("이번 주에는 아직 풀이 기록이 없습니다.")
        return

    ranking_df = (
        df_week.groupby("user_name").size().reset_index(name="풀이수")
        .sort_values(by="풀이수", ascending=False)
    )
    ranking_df["순위"] = range(1, len(ranking_df) + 1)
    ranking_df = ranking_df[["순위", "user_name", "풀이수"]]

    st.subheader("📈 이번 주 문제풀이 랭킹")
    st.table(ranking_df)

    if st.session_state.user_name in ranking_df["user_name"].values:
        row = ranking_df[
            ranking_df["user_name"] == st.session_state.user_name
        ].iloc[0]
        st.success(
            f"{st.session_state.user_name}님의 이번 주 풀이 수: {int(row['풀이수'])}개, 순위: {int(row['순위'])}위"
        )


def login_page() -> None:
    """로그인 페이지를 표시합니다."""
    st.title("🔐 사용자 로그인")
    name = st.text_input("이름을 입력하세요")
    group = st.text_input("소속을 입력하세요 (관리자일 경우 '관리자' 또는 'admin')")
    password = st.text_input("암호를 입력하세요", type="password")

    if st.button("로그인"):
        if password == "admin" or group.lower() in ("admin", "관리자"):
            st.session_state.is_admin = True
            st.session_state.logged_in = True
            st.session_state.user_name = f"{name} ({group})" if group else name
            st.success(f"🎉 관리자님 환영합니다, {st.session_state.user_name}!")
            st.rerun()
        elif password == "1234":
            st.session_state.is_admin = False
            st.session_state.logged_in = True
            st.session_state.user_name = f"{name} ({group})" if group else name
            st.success(f"🎉 환영합니다, {st.session_state.user_name}님!")
            st.rerun()
        else:
            st.error("❌ 암호가 틀렸습니다.")


def load_and_filter_data(selected_file: str, selected_chapter: str) -> None:
    """CSV 파일을 읽고 단원별로 필터링하여 세션 상태에 저장합니다."""
    df_loaded = pd.read_csv(selected_file)
    df_loaded = df_loaded.dropna(subset=["문제", "정답"])

    if selected_chapter != "전체 보기":
        df_filtered = df_loaded[df_loaded["단원명"] == selected_chapter]
    else:
        df_filtered = df_loaded

    st.session_state.df = df_filtered
    st.session_state.question = None
    st.session_state.answered = False
    st.session_state.last_question = None


def get_new_question() -> None:
    """세션 상태의 데이터프레임에서 무작위로 문제를 선택합니다."""
    df = st.session_state.df
    if df is not None and not df.empty:
        st.session_state.question = df.sample(1).iloc[0]
    else:
        st.session_state.question = None


def main_page() -> None:
    """메인 퀴즈 페이지를 구성합니다."""
    st.title("📘 공인중개사 OX 퀴즈")
    st.sidebar.header("📂 문제집 선택")

    csv_files = [f for f in os.listdir() if f.endswith(".csv")]
    selected_file = st.sidebar.selectbox("사용할 파일을 선택하세요", csv_files)

    if not selected_file:
        st.warning("⚠️ CSV 문제 파일을 업로드하세요.")
        return

    if st.session_state.prev_selected_file != selected_file:
        st.session_state.prev_selected_file = selected_file

    df_loaded = pd.read_csv(selected_file)
    df_loaded = df_loaded.dropna(subset=["문제", "정답"])
    chapters = sorted(df_loaded["단원명"].dropna().unique())

    selected_chapter = st.sidebar.selectbox(
        "특정 단원만 푸시겠습니까?", ["전체 보기"] + chapters
    )

    if (
        st.session_state.prev_selected_chapter != selected_chapter
        or st.session_state.prev_selected_file != selected_file
        or st.session_state.df is None
    ):
        st.session_state.prev_selected_chapter = selected_chapter
        load_and_filter_data(selected_file, selected_chapter)

    if st.session_state.question is None:
        get_new_question()

    if st.session_state.question is None:
        st.info("선택한 단원에 문제 데이터가 없습니다.")
        return

    question = st.session_state.question

    st.markdown(
        f"📚 단원명: {question['단원명']} | 문제번호: {int(question['문제번호'])}"
    )
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
        st.session_state.answered = True
        st.session_state.last_question = question.copy()

        # 주간 랭킹용 기록 저장
        record_user_activity()

        if user_answer == question["정답"]:
            st.session_state.score += 1
            st.success("✅ 정답입니다!")
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
                if "해설" in question and pd.notna(question["해설"])
                else "",
            })
            st.error(f"❌ 오답입니다. 정답은 {question['정답']}")

        # === 중복 문제 방지: 현재 문제를 df에서 제거 ===
        st.session_state.df = st.session_state.df[
            st.session_state.df["문제번호"] != question["문제번호"]
        ]

    if st.session_state.answered and st.session_state.last_question is not None:
        last_q = st.session_state.last_question
        if "해설" in last_q and pd.notna(last_q["해설"]):
            st.info(f"📘 해설: {last_q['해설']}")

        if st.button("👉 다음 문제"):
            get_new_question()
            st.session_state.answered = False
            st.rerun()

        # 사이드바 통계 및 오답 저장
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"👤 사용자: **{st.session_state.user_name}**")
        st.sidebar.markdown(f"✅ 정답 수: {st.session_state.score}")
        st.sidebar.markdown(f"❌ 오답 수: {len(st.session_state.wrong_list)}")
        st.sidebar.markdown(f"📊 총 풀이 수: {st.session_state.total}")
        st.sidebar.markdown("Made with ❤️ for 공인중개사 수험생")

        if st.sidebar.button("🗂️ 오답 엑셀로 저장"):
            if st.session_state.wrong_list:
                wrong_df = pd.DataFrame(st.session_state.wrong_list)
                filename = (
                    f"{st.session_state.user_name}_오답_"
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                )
                wrong_df.to_excel(filename, index=False)
                st.sidebar.success(f"📁 {filename} 저장 완료!")
            else:
                st.sidebar.warning("❗ 오답이 없습니다.")

        # 주간 랭킹 보기 버튼 (모든 사용자에게 표시)
        if st.sidebar.button("📈 주간 랭킹 보기"):
            display_weekly_ranking()


def run_app() -> None:
    """앱 실행 함수."""
    init_session_state()
    if not st.session_state.logged_in:
        login_page()
        return
    main_page()


if __name__ == "__main__":
    run_app()
