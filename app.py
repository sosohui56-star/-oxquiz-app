import os
from datetime import datetime, timedelta
import csv
import re

import pandas as pd
import streamlit as st

"""공인중개사 OX 퀴즈 애플리케이션 (안정화 버전)

기능:
- 문제를 풀 때마다 progress_log.csv에 기록해 주간 랭킹 계산
- 사용자별 progress 파일을 저장해 다음 로그인 시 이어서 풀이 가능
- 오답 엑셀 파일은 영문 파일명으로 저장하고, 화면에는 한글 이름으로 안내
- 한 번 푼 문제는 세션과 다음 로그인 시에도 다시 나오지 않음
- CSV 파일 읽기 오류, 필수 컬럼 누락 등의 예외를 처리하여 앱 안정성 향상
"""

# 사용자 개별 데이터를 저장할 디렉터리
USER_DATA_DIR = "user_data"
os.makedirs(USER_DATA_DIR, exist_ok=True)


def get_safe_filename(name: str) -> str:
    """파일명으로 사용하기 안전하도록 문자열을 변환합니다."""
    return re.sub(r"[^\w]", "_", name)


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
    """모든 사용자의 풀이 기록을 progress_log.csv에 저장합니다 (주간 랭킹용)."""
    file_path = "progress_log.csv"
    header = ["user_name", "timestamp"]
    try:
        if not os.path.exists(file_path):
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header)
        with open(file_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([st.session_state.user_name, datetime.now().isoformat()])
    except Exception as e:
        st.warning(f"기록 파일에 저장하는 중 오류가 발생했습니다: {e}")


def load_user_progress(username: str):
    """사용자의 기존 풀이 기록을 불러와 세션 상태를 복원하고, 이미 푼 문제는 제외합니다."""
    safe_name = get_safe_filename(username)
    file_path = os.path.join(USER_DATA_DIR, f"{safe_name}_progress.csv")

    answered_ids = set()
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            st.warning(f"사용자 진행 파일을 읽는 중 오류가 발생했습니다: {e}")
            return answered_ids, file_path

        # 총 풀이 수와 점수 복원
        st.session_state.total = len(df)
        st.session_state.score = df[df["correct"] == True].shape[0]

        # 오답 목록 복원
        wrong_df = df[df["correct"] == False]
        st.session_state.wrong_list = []
        for _, row in wrong_df.iterrows():
            st.session_state.wrong_list.append({
                "이름": username,
                "날짜": row.get("timestamp", ""),
                "문제번호": row.get("question_id", ""),
                "단원명": row.get("chapter", ""),
                "문제": row.get("question", ""),
                "정답": row.get("correct_answer", ""),
                "선택": row.get("answer", ""),
                "해설": row.get("explanation", ""),
            })

        answered_ids = set(df["question_id"])

    return answered_ids, file_path


def save_user_progress(file_path: str, data: dict) -> None:
    """사용자의 풀었던 문제를 파일에 저장합니다."""
    df_line = pd.DataFrame([data])
    write_header = not os.path.exists(file_path)
    try:
        df_line.to_csv(file_path, mode="a", header=write_header, index=False)
    except Exception as e:
        st.warning(f"사용자 진행 파일 저장 중 오류가 발생했습니다: {e}")


def display_weekly_ranking() -> None:
    """주간 랭킹을 계산하여 전체 사용자에게 표시합니다."""
    file_path = "progress_log.csv"
    if not os.path.exists(file_path):
        st.info("아직 풀이 기록이 없습니다.")
        return

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        st.warning(f"주간 랭킹 파일을 읽는 중 오류가 발생했습니다: {e}")
        return

    if "timestamp" not in df.columns or "user_name" not in df.columns:
        st.warning("주간 랭킹 파일의 형식이 올바르지 않습니다.")
        return

    try:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    except Exception as e:
        st.warning(f"날짜 형식을 변환하는 중 오류가 발생했습니다: {e}")
        return

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
    name_input = st.text_input("이름을 입력하세요")
    group_input = st.text_input("소속을 입력하세요 (관리자일 경우 '관리자' 또는 'admin')")
    password = st.text_input("암호를 입력하세요", type="password")

    if st.button("로그인"):
        # 입력 값 공백 제거
        name = name_input.strip()
        group = group_input.strip()

        if password == "admin" or group.lower() in ("admin", "관리자"):
            st.session_state.is_admin = True
            st.session_state.logged_in = True
            st.session_state.user_name = f"{name} ({group})" if group else name
            # 로그인 시 기존 데이터 복원
            load_user_progress(st.session_state.user_name)
            st.success(f"🎉 관리자님 환영합니다, {st.session_state.user_name}!")
            st.rerun()
        elif password == "1234":
            st.session_state.is_admin = False
            st.session_state.logged_in = True
            st.session_state.user_name = f"{name} ({group})" if group else name
            # 로그인 시 기존 데이터 복원
            load_user_progress(st.session_state.user_name)
            st.success(f"🎉 환영합니다, {st.session_state.user_name}님!")
            st.rerun()
        else:
            st.error("❌ 암호가 틀렸습니다.")


def load_and_filter_data(selected_file: str, selected_chapter: str, answered_ids: set) -> None:
    """CSV 파일을 읽고 단원별로 필터링한 뒤, 이미 푼 문제는 제외합니다."""
    try:
        df_loaded = pd.read_csv(selected_file)
    except FileNotFoundError:
        st.error(f"{selected_file} 파일을 찾을 수 없습니다.")
        st.session_state.df = pd.DataFrame()
        return
    except Exception as e:
        st.error(f"{selected_file} 파일을 읽는 중 오류가 발생했습니다: {e}")
        st.session_state.df = pd.DataFrame()
        return

    # 필수 컬럼 확인
    required_cols = {"문제", "정답"}
    missing = required_cols - set(df_loaded.columns)
    if missing:
        st.error(f"CSV 파일에 필수 열 {missing} 이/가 없습니다. 헤더를 확인하세요.")
        st.session_state.df = pd.DataFrame()
        return

    df_loaded = df_loaded.dropna(subset=["문제", "정답"])

    # '문제번호' 열이 없다면 생성
    if "문제번호" not in df_loaded.columns:
        # 인덱스 기반으로 번호 생성
        df_loaded["문제번호"] = range(1, len(df_loaded) + 1)

    # 단원 필터링
    if selected_chapter != "전체 보기":
        df_filtered = df_loaded[df_loaded["단원명"] == selected_chapter]
    else:
        df_filtered = df_loaded

    # 이미 푼 문제 제외
    if answered_ids:
        df_filtered = df_filtered[~df_filtered["문제번호"].astype(str).isin(answered_ids)]

    st.session_state.df = df_filtered.reset_index(drop=True)
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

    # 로그인한 사용자의 이전 풀이 문제 목록 로딩
    answered_ids, user_progress_file = load_user_progress(st.session_state.user_name)

    if st.session_state.prev_selected_file != selected_file:
        st.session_state.prev_selected_file = selected_file

    # CSV 파일을 미리 읽어 단원 목록 확보
    try:
        df_loaded = pd.read_csv(selected_file)
    except Exception as e:
        st.error(f"{selected_file} 파일을 읽는 중 오류가 발생했습니다: {e}")
        return

    if "문제" not in df_loaded.columns or "정답" not in df_loaded.columns:
        st.error("CSV 파일에 '문제' 또는 '정답' 열이 없습니다.")
        return

    df_loaded = df_loaded.dropna(subset=["문제", "정답"])
    chapters = sorted(df_loaded["단원명"].dropna().unique()) if "단원명" in df_loaded.columns else []

    selected_chapter = st.sidebar.selectbox(
        "특정 단원만 푸시겠습니까?", ["전체 보기"] + chapters
    )

    if (
        st.session_state.prev_selected_chapter != selected_chapter
        or st.session_state.prev_selected_file != selected_file
        or st.session_state.df is None
    ):
        st.session_state.prev_selected_chapter = selected_chapter
        load_and_filter_data(selected_file, selected_chapter, answered_ids)

    if st.session_state.question is None:
        get_new_question()

    if st.session_state.question is None:
        st.info("선택한 단원에 문제 데이터가 없거나, 이전에 모두 풀었습니다.")
        return

    question = st.session_state.question

    # 문제번호가 숫자가 아닐 수도 있으므로 예외처리
    qnum = question["문제번호"]
    try:
        qnum_display = int(qnum)
    except (ValueError, TypeError):
        qnum_display = qnum

    st.markdown(f"📚 단원명: {question.get('단원명','')} | 문제번호: {qnum_display}")
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

        correct = False
        if user_answer == question["정답"]:
            st.session_state.score += 1
            correct = True
            st.success("✅ 정답입니다!")
        else:
            st.session_state.wrong_list.append({
                "이름": st.session_state.user_name,
                "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "문제번호": qnum_display,
                "단원명": question.get("단원명", ""),
                "문제": question["문제"],
                "정답": question["정답"],
                "선택": user_answer,
                "해설": question["해설"]
                if "해설" in question and pd.notna(question["해설"])
                else "",
            })
            st.error(f"❌ 오답입니다. 정답은 {question['정답']}")

        # 사용자 개별 progress 파일에 기록 저장
        save_user_progress(user_progress_file, {
            "question_id": str(qnum),
            "timestamp": datetime.now().isoformat(),
            "correct": correct,
            "chapter": question.get("단원명",""),
            "question": question["문제"],
            "answer": user_answer,
            "correct_answer": question["정답"],
            "explanation": question["해설"] if "해설" in question and pd.notna(question["해설"]) else "",
        })

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

        # 오답 엑셀 저장: 실제 파일명은 영문, 화면에는 한글로 표시
        if st.sidebar.button("🗂️ 오답 엑셀로 저장"):
            if st.session_state.wrong_list:
                wrong_df = pd.DataFrame(st.session_state.wrong_list)
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = get_safe_filename(st.session_state.user_name)
                filename = f"{safe_name}_wrong_{timestamp_str}.xlsx"
                display_name = f"{st.session_state.user_name}_오답_{timestamp_str}.xlsx"
                try:
                    wrong_df.to_excel(filename, index=False)
                    st.sidebar.success(f"📁 {display_name} 저장 완료!")
                except Exception as e:
                    st.sidebar.error(f"엑셀 파일을 저장하는 데 실패했습니다: {e}")
            else:
                st.sidebar.warning("❗ 오답이 없습니다.")

        # 주간 랭킹 보기
        if st.sidebar.button("📈 주간 랭킹 보기"):
            display_weekly_ranking()

        # 오답 목록 보기(선택사항)
        if st.sidebar.button("❔ 오답 목록 보기"):
            if st.session_state.wrong_list:
                wrong_df = pd.DataFrame(st.session_state.wrong_list)
                st.subheader("❗ 오답 목록")
                st.table(
                    wrong_df[
                        ["날짜", "문제번호", "단원명", "문제", "선택", "정답", "해설"]
                    ]
                )
            else:
                st.info("현재 오답이 없습니다.")


def run_app() -> None:
    """앱 실행 함수."""
    init_session_state()
    if not st.session_state.logged_in:
        login_page()
        return
    main_page()


if __name__ == "__main__":
    run_app()
