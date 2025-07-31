import os
from datetime import datetime, timedelta
import csv
import re

import pandas as pd
import streamlit as st

"""
공인중개사 OX 퀴즈 애플리케이션 (기능 보완 & 안정화 버전)

추가된 기능:
- 📁 CSV 파일 업로드: 사이드바에서 문제집을 업로드하여 즉시 사용 가능
- 🎯 진행 요약: 정답률과 남은 문제 수를 사이드바에 표시
- 🛡️ 예외 처리 강화: 파일 읽기 오류에 대한 처리 및 경고 메시지 보완
- 🛑 문제 제거 조건 수정: '다시 보지 않기'를 선택해야만 문제가 제거되고, 이해도 50% 미만 문제는 두 배 빈도로 출제
"""

USER_DATA_DIR = "user_data"
os.makedirs(USER_DATA_DIR, exist_ok=True)

def get_safe_filename(name: str) -> str:
    return re.sub(r"[^\w]", "_", name)

def init_session_state() -> None:
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
    safe_name = get_safe_filename(username)
    file_path = os.path.join(USER_DATA_DIR, f"{safe_name}_progress.csv")

    skip_ids = set()
    low_ids = set()
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            st.warning(f"사용자 진행 파일을 읽는 중 오류가 발생했습니다: {e}")
            return skip_ids, low_ids, file_path

        if "rating" not in df.columns:
            df["rating"] = ""

        st.session_state.total = len(df)
        st.session_state.score = df[df["correct"] == True].shape[0]

        wrong_df = df[(df["correct"] == False)]
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

        skip_ids = set(df[df["rating"] == "skip"]["question_id"].astype(str))
        low_ids = set(df[df["rating"] == "low"]["question_id"].astype(str))

    return skip_ids, low_ids, file_path

def save_user_progress(file_path: str, data: dict) -> None:
    df_line = pd.DataFrame([data])
    write_header = not os.path.exists(file_path)
    try:
        df_line.to_csv(file_path, mode="a", header=write_header, index=False)
    except Exception as e:
        st.warning(f"사용자 진행 파일 저장 중 오류가 발생했습니다: {e}")

def update_question_rating(file_path: str, question_id: str, rating: str) -> None:
    try:
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            if "rating" not in df.columns:
                df["rating"] = ""
            mask = (df["question_id"] == question_id) & (df["rating"].isna() | (df["rating"] == ""))
            if mask.any():
                df.loc[mask, "rating"] = rating
                df.to_csv(file_path, index=False)
    except Exception as e:
        st.warning(f"문제 이해도 저장 중 오류가 발생했습니다: {e}")

def display_weekly_ranking() -> None:
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
    st.title("🔐 사용자 로그인")
    name_input = st.text_input("이름을 입력하세요")
    group_input = st.text_input("소속을 입력하세요 (관리자일 경우 '관리자' 또는 'admin')")
    password = st.text_input("암호를 입력하세요", type="password")

    if st.button("로그인"):
        name = name_input.strip()
        group = group_input.strip()

        if password == "admin" or group.lower() in ("admin", "관리자"):
            st.session_state.is_admin = True
            st.session_state.logged_in = True
            st.session_state.user_name = f"{name} ({group})" if group else name
            load_user_progress(st.session_state.user_name)
            st.success(f"🎉 관리자님 환영합니다, {st.session_state.user_name}!")
            st.rerun()
        elif password == "1234":
            st.session_state.is_admin = False
            st.session_state.logged_in = True
            st.session_state.user_name = f"{name} ({group})" if group else name
            load_user_progress(st.session_state.user_name)
            st.success(f"🎉 환영합니다, {st.session_state.user_name}님!")
            st.rerun()
        else:
            st.error("❌ 암호가 틀렸습니다.")

def load_and_filter_data(selected_source, selected_chapter: str, skip_ids: set, low_ids: set) -> None:
    """
    selected_source는 CSV 파일 경로나 pd.DataFrame 일 수 있습니다.
    '다시 보지 않기' 등급 문제는 제외하고, low 등급 문제는 두 배로 복제합니다.
    """
    # 1. 데이터프레임 로딩
    if isinstance(selected_source, pd.DataFrame):
        df_loaded = selected_source.copy()
    else:
        # selected_source가 파일 경로라고 가정
        try:
            df_loaded = pd.read_csv(selected_source)
        except FileNotFoundError:
            st.error(f"{selected_source} 파일을 찾을 수 없습니다.")
            st.session_state.df = pd.DataFrame()
            return
        except Exception as e:
            st.error(f"{selected_source} 파일을 읽는 중 오류가 발생했습니다: {e}")
            st.session_state.df = pd.DataFrame()
            return

    # 2. 필수 컬럼 확인
    required_cols = {"문제", "정답"}
    missing = required_cols - set(df_loaded.columns)
    if missing:
        st.error(f"CSV 파일에 필수 열 {missing} 이/가 없습니다. 헤더를 확인하세요.")
        st.session_state.df = pd.DataFrame()
        return

    df_loaded = df_loaded.dropna(subset=["문제", "정답"])

    if "문제번호" not in df_loaded.columns:
        df_loaded["문제번호"] = range(1, len(df_loaded) + 1)

    # 3. 단원 필터링
    if selected_chapter != "전체 보기":
        df_filtered = df_loaded[df_loaded["단원명"] == selected_chapter]
    else:
        df_filtered = df_loaded

    # 4. 'skip' 등급 문제 제외
    if skip_ids:
        df_filtered = df_filtered[~df_filtered["문제번호"].astype(str).isin(skip_ids)]

    # 5. 'low' 등급 문제를 복제하여 확률 증가
    if low_ids:
        low_df = df_filtered[df_filtered["문제번호"].astype(str).isin(low_ids)]
        if not low_df.empty:
            df_filtered = pd.concat([df_filtered, low_df], ignore_index=True)

    st.session_state.df = df_filtered.reset_index(drop=True)
    st.session_state.question = None
    st.session_state.answered = False
    st.session_state.last_question = None

def get_new_question() -> None:
    df = st.session_state.df
    if df is not None and not df.empty:
        st.session_state.question = df.sample(1).iloc[0]
    else:
        st.session_state.question = None

def main_page() -> None:
    st.title("📘 공인중개사 OX 퀴즈")
    st.sidebar.header("📂 문제집 선택")

    # 1. CSV 업로드 기능
    uploaded_file = st.sidebar.file_uploader("문제집 업로드(CSV)", type=["csv"])

    csv_files = [f for f in os.listdir() if f.endswith(".csv")]
    selected_file = st.sidebar.selectbox("로컬 CSV 선택", csv_files)

    # 2. 학습 진행 정보 표시 (정답률, 남은 문제)
    if st.session_state.total > 0:
        accuracy = (st.session_state.score / st.session_state.total) * 100
    else:
        accuracy = 0.0
    st.sidebar.markdown(f"🎯 정답률: {accuracy:.1f}%")
    remaining = st.session_state.df.shape[0] if st.session_state.df is not None else 0
    st.sidebar.markdown(f"📝 남은 문제: {remaining}개")

    if not uploaded_file and not selected_file:
        st.warning("⚠️ CSV 문제 파일을 업로드하거나 선택하세요.")
        return

    # 3. 사용자 진행 정보 로딩
    skip_ids, low_ids, user_progress_file = load_user_progress(st.session_state.user_name)

    # 4. 데이터 원본 결정
    if uploaded_file:
        try:
            df_source = pd.read_csv(uploaded_file)
            file_label = uploaded_file.name
        except Exception as e:
            st.error(f"업로드된 파일을 읽는 중 오류가 발생했습니다: {e}")
            return
    else:
        df_source = selected_file
        file_label = selected_file

    if st.session_state.prev_selected_file != file_label:
        st.session_state.prev_selected_file = file_label

    # 5. 단원 목록 확보
    try:
        if isinstance(df_source, pd.DataFrame):
            df_loaded_temp = df_source.copy()
        else:
            df_loaded_temp = pd.read_csv(df_source)
    except Exception as e:
        st.error(f"{file_label} 파일을 읽는 중 오류가 발생했습니다: {e}")
        return

    if "문제" not in df_loaded_temp.columns or "정답" not in df_loaded_temp.columns:
        st.error("CSV 파일에 '문제' 또는 '정답' 열이 없습니다.")
        return

    df_loaded_temp = df_loaded_temp.dropna(subset=["문제", "정답"])
    chapters = sorted(df_loaded_temp["단원명"].dropna().unique()) if "단원명" in df_loaded_temp.columns else []

    selected_chapter = st.sidebar.selectbox(
        "특정 단원만 푸시겠습니까?", ["전체 보기"] + chapters
    )

    if (
        st.session_state.prev_selected_chapter != selected_chapter
        or st.session_state.prev_selected_file != file_label
        or st.session_state.df is None
    ):
        st.session_state.prev_selected_chapter = selected_chapter
        # selected_source는 DataFrame 또는 파일 경로
        load_and_filter_data(df_source, selected_chapter, skip_ids, low_ids)

    if st.session_state.question is None:
        get_new_question()

    if st.session_state.question is None:
        st.info("선택한 단원에 문제 데이터가 없거나, 이전에 모두 풀었습니다.")
        return

    question = st.session_state.question

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
log_to_sheet({
    "timestamp": datetime.now().isoformat(),
    "user_name": st.session_state.user_name,
    "question_id": str(qnum),
    "correct": correct,
    "rating": "skip" if skip else "low" if low else "mid"
})

if st.session_state.answered and st.session_state.last_question is not None:
    ...
        last_q = st.session_state.last_question
        if "해설" in last_q and pd.notna(last_q["해설"]):
            st.info(f"📘 해설: {last_q['해설']}")

        rating_col1, rating_col2, rating_col3 = st.columns(3)
        if rating_col1.button("❌ 다시 보지 않기"):
            update_question_rating(user_progress_file, str(qnum), "skip")
            st.session_state.df = st.session_state.df[
                st.session_state.df["문제번호"] != question["문제번호"]
            ]
            get_new_question()
            st.session_state.answered = False
            st.rerun()

        if rating_col2.button("📘 이해 50~90%"):
            update_question_rating(user_progress_file, str(qnum), "mid")
            get_new_question()
            st.session_state.answered = False
            st.rerun()

        if rating_col3.button("🔄 이해 50% 미만"):
            update_question_rating(user_progress_file, str(qnum), "low")
            get_new_question()
            st.session_state.answered = False
            st.rerun()

        st.sidebar.markdown("---")
        st.sidebar.markdown(f"👤 사용자: **{st.session_state.user_name}**")
        st.sidebar.markdown(f"✅ 정답 수: {st.session_state.score}")
        st.sidebar.markdown(f"❌ 오답 수: {len(st.session_state.wrong_list)}")
        st.sidebar.markdown(f"📊 총 풀이 수: {st.session_state.total}")
        st.sidebar.markdown(f"🎯 정답률: {accuracy:.1f}%")
        st.sidebar.markdown(f"📝 남은 문제: {remaining}개")
        st.sidebar.markdown("Made with ❤️ for 공인중개사 수험생")

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

        if st.sidebar.button("📈 주간 랭킹 보기"):
            display_weekly_ranking()

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
    init_session_state()
    if not st.session_state.logged_in:
        login_page()
        return
    main_page()

if __name__ == "__main__":
    run_app()
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials

def connect_to_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = json.loads(st.secrets["GCP_CREDENTIALS"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("oxquiz_progress_log").sheet1
    return sheet

def log_to_sheet(data: dict):
    try:
        sheet = connect_to_sheet()
        row = [
            data["timestamp"],
            data["user_name"],
            data["question_id"],
            data["correct"],
            data["rating"]
        ]
        sheet.append_row(row)
    except Exception as e:
        st.warning(f"📛 구글 시트 기록 실패: {e}")
