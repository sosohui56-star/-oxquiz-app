import os
from datetime import datetime, timedelta
import csv
import re

import pandas as pd
import streamlit as st
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials

"""
공인중개사 OX 퀴즈 애플리케이션 (기능 보완 & 안정화 버전)

본 모듈은 Streamlit을 이용해 공인중개사 수험생을 위한 OX 퀴즈 프로그램을 제공합니다.
사용자 진행 상황을 로컬 CSV로 저장하고, 선택적으로 구글 스프레드시트에 기록합니다.
해당 버전은 기존 코드의 오류를 수정하고 함수 중복을 제거했습니다.
또한 문제 이해도(다시 보지 않기/50~90%/50% 미만) 평가 시점에 점수를 구글 시트에 기록하도록 수정했습니다.
"""

# 디렉터리 초기화
USER_DATA_DIR = "user_data"
os.makedirs(USER_DATA_DIR, exist_ok=True)

def get_safe_filename(name: str) -> str:
    """파일명에 사용할 수 없는 문자를 '_'로 치환합니다."""
    return re.sub(r"[^\w]", "_", name)

def init_session_state() -> None:
    """Streamlit 세션 상태를 초기화합니다."""
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
        # 최근 답변 정보 저장용
        "last_correct": None,
        "last_qnum": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def record_user_activity() -> None:
    """사용자의 풀이 활동을 간단히 로컬 CSV 파일로 기록합니다."""
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

def connect_to_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = json.loads(st.secrets["GCP_CREDENTIALS"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    # ⬇ 시트 탭 이름이 '시트1'이라면 worksheet("시트1")로 지정
    sheet = client.open("oxquiz_progress_log").worksheet("시트1")
    return sheet

def log_to_sheet(data: dict):
    """
    풀이 데이터를 구글 스프레드시트에 기록합니다.

    data 예시:
        {
            "timestamp": "2025-01-01T12:00:00",
            "user_name": "홍길동",
            "question_id": "42",
            "correct": True,
            "rating": "mid"
        }
    """
    try:
        sheet = connect_to_sheet()
        row = [
            data.get("timestamp"),
            data.get("user_name"),
            data.get("question_id"),
            data.get("correct"),
            data.get("rating"),
        ]
        sheet.append_row(row)
    except Exception as e:
        # 구글 시트 기록 실패 시 사용자에게 경고
        st.warning(f"📛 구글 시트 기록 실패: {e}")

def load_user_progress(username: str):
    """
    사용자 진행 정보를 로컬 CSV 파일에서 읽어와 skip/low 문제 ID 집합과 파일 경로를 반환합니다.
    """
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

        # 등급별로 문제번호를 분류
        skip_ids = set(df[df["rating"] == "skip"]["question_id"].astype(str))
        low_ids = set(df[df["rating"] == "low"]["question_id"].astype(str))

    return skip_ids, low_ids, file_path

def save_user_progress(file_path: str, data: dict) -> None:
    """사용자 풀이 결과를 로컬 CSV에 저장합니다."""
    df_line = pd.DataFrame([data])
    write_header = not os.path.exists(file_path)
    try:
        df_line.to_csv(file_path, mode="a", header=write_header, index=False)
    except Exception as e:
        st.warning(f"사용자 진행 파일 저장 중 오류가 발생했습니다: {e}")

def update_question_rating(file_path: str, question_id: str, rating: str) -> None:
    """
    특정 문제의 이해도(등급)를 업데이트합니다.
    rating은 'skip', 'mid', 'low' 중 하나입니다.
    """
    try:
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            if "rating" not in df.columns:
                df["rating"] = ""
            mask = (
                (df["question_id"] == question_id) &
                (df["rating"].isna() | (df["rating"] == ""))
            )
            if mask.any():
                df.loc[mask, "rating"] = rating
                df.to_csv(file_path, index=False)
    except Exception as e:
        st.warning(f"문제 이해도 저장 중 오류가 발생했습니다: {e}")

def display_weekly_ranking() -> None:
    """
    최근 한 주간의 풀이 수를 기준으로 랭킹을 산출하여 화면에 표시합니다.
    """
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

    # 날짜 형식 변환
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
    """로그인 페이지를 표시하고 로그인 상태를 관리합니다."""
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
    문제집 데이터프레임을 로딩하고 단원 필터링 및 skip/low 문제 제외/복제 처리를 수행합니다.

    selected_source는 CSV 파일 경로나 pd.DataFrame 일 수 있습니다.
    selected_chapter가 '전체 보기'가 아닌 경우 해당 단원만 필터링합니다.
    'skip' 등급 문제는 제거하고, 'low' 등급 문제는 한 번 더 복제하여 출제 확률을 높입니다.
    결과는 st.session_state.df에 저장됩니다.
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

    # 3. 결측값 제거
    df_loaded = df_loaded.dropna(subset=["문제", "정답"])

    # 4. 문제번호 부여
    if "문제번호" not in df_loaded.columns:
        df_loaded["문제번호"] = range(1, len(df_loaded) + 1)

    # 5. 단원 필터링
    if selected_chapter != "전체 보기":
        df_filtered = df_loaded[df_loaded["단원명"] == selected_chapter]
    else:
        df_filtered = df_loaded

    # 6. 'skip' 등급 문제 제외
    if skip_ids:
        df_filtered = df_filtered[~df_filtered["문제번호"].astype(str).isin(skip_ids)]

    # 7. 'low' 등급 문제를 복제하여 확률 증가
    if low_ids:
        low_df = df_filtered[df_filtered["문제번호"].astype(str).isin(low_ids)]
        if not low_df.empty:
            df_filtered = pd.concat([df_filtered, low_df], ignore_index=True)

    # 8. 세션 상태에 저장 및 초기화
    st.session_state.df = df_filtered.reset_index(drop=True)
    st.session_state.question = None
    st.session_state.answered = False
    st.session_state.last_question = None

def get_new_question() -> None:
    """현재 필터링된 데이터프레임에서 랜덤으로 문제를 선택하여 세션 상태에 저장합니다."""
    df = st.session_state.df
    if df is not None and not df.empty:
        st.session_state.question = df.sample(1).iloc[0]
    else:
        st.session_state.question = None

def main_page() -> None:
    """퀴즈의 메인 페이지를 표시하고 문제풀이 로직을 처리합니다."""
    st.title("📘 공인중개사 OX 퀴즈")
    st.sidebar.header("📂 문제집 선택")

    # 1. CSV 업로드 기능
    uploaded_file = st.sidebar.file_uploader("문제집 업로드(CSV)", type=["csv"])

    # 현재 작업 디렉터리 내 CSV 파일 목록
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

    # 업로드 또는 선택된 파일이 없으면 경고 메시지
    if not uploaded_file and not selected_file:
        st.warning("⚠️ CSV 문제 파일을 업로드하거나 선택하세요.")
        return

    # 3. 사용자 진행 정보 로딩 (skip/low 문제번호 등)
    skip_ids, low_ids, user_progress_file = load_user_progress(st.session_state.user_name)

    # 4. 업로드 or 선택된 파일을 불러오는 부분
    if uploaded_file:
        try:
            df_source = pd.read_csv(uploaded_file)
            file_label = uploaded_file.name
            st.success("업로드된 문제집 파일을 불러왔습니다!")
        except Exception as e:
            st.error(f"CSV 파일을 읽는 중 오류: {e}")
            return
    elif selected_file:
        try:
            df_source = pd.read_csv(selected_file)
            file_label = selected_file
            st.success(f"{selected_file} 파일을 불러왔습니다!")
        except Exception as e:
            st.error(f"로컬 파일 읽기 오류: {e}")
            return
    else:
        st.warning("문제집 파일을 업로드하거나 선택하세요.")
        return

    # 실제 열(헤더) 이름이 뭔지 출력!
    st.write("문제집의 열(헤더):", df_source.columns)

    # 5. 이전 선택과 현재 선택이 다르면 데이터 다시 로딩
    if st.session_state.prev_selected_file != file_label:
        st.session_state.prev_selected_file = file_label

 # 6. 단원 목록 확보
    try:
        if isinstance(df_source, pd.DataFrame):
            df_loaded_temp = df_source.copy()
        else:
            df_loaded_temp = pd.read_csv(df_source)
    except Exception as e:
        st.error(f"{file_label} 파일을 읽는 중 오류가 발생했습니다: {e}")
        return

  # 필수 컬럼 확인
    if "문제" not in df_loaded_temp.columns or "정답" not in df_loaded_temp.columns:
        st.error("CSV 파일에 '문제' 또는 '정답' 열이 없습니다.")
        return

    df_loaded_temp = df_loaded_temp.dropna(subset=["문제", "정답"])
    chapters = sorted(df_loaded_temp["단원명"].dropna().unique()) if "단원명" in df_loaded_temp.columns else []

    selected_chapter = st.sidebar.selectbox(
        "특정 단원만 푸시겠습니까?", ["전체 보기"] + chapters
    )

    # 7. 단원 또는 파일이 변경되었거나 데이터프레임이 비어 있으면 데이터 로딩 수행
    if (
        st.session_state.prev_selected_chapter != selected_chapter
        or st.session_state.prev_selected_file != file_label
        or st.session_state.df is None
    ):
        st.session_state.prev_selected_chapter = selected_chapter
        load_and_filter_data(df_source, selected_chapter, skip_ids, low_ids)

    # 8. 현재 문제 없으면 새 문제 선택
    if st.session_state.question is None:
        get_new_question()

    # 문제가 없으면 종료
    if st.session_state.question is None:
        st.info("선택한 단원에 문제 데이터가 없거나, 이전에 모두 풀었습니다.")
        return

    # 문제 표시
    question = st.session_state.question
    qnum = question["문제번호"]
    try:
        qnum_display = int(qnum)
    except (ValueError, TypeError):
        qnum_display = qnum

    st.markdown(f"📚 단원명: {question.get('단원명','')} | 문제번호: {qnum_display}")
    st.markdown(f"❓ {question['문제']}")

    # 사용자의 선택 처리
    user_answer = None
    col1, col2, col3 = st.columns(3)
    if col1.button("⭕ O"):
        user_answer = "O"
    elif col2.button("❌ X"):
        user_answer = "X"
    elif col3.button("⁉️ 모름"):
        user_answer = "모름"

    if user_answer:
        # 총 풀이수 증가
        st.session_state.total += 1
        st.session_state.answered = True
        st.session_state.last_question = question.copy()

        record_user_activity()

        # 정답 여부 판별
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

        # 나중에 평점 버튼 클릭 시 사용할 값 저장
        st.session_state.last_correct = correct
        st.session_state.last_qnum = str(qnum_display)

       # 정답/오답 후 해설과 평점 버튼 표시
    if st.session_state.answered and st.session_state.last_question is not None:
        last_q = st.session_state.last_question

        # 해설이 있으면 표시
        if "해설" in last_q and pd.notna(last_q["해설"]):
            st.info(f"📘 해설: {last_q['해설']}")

        # 평점 버튼
        rating_col1, rating_col2, rating_col3 = st.columns(3)

        if rating_col1.button("❌ 다시 보지 않기"):
            update_question_rating(user_progress_file, st.session_state.last_qnum, "skip")
            log_to_sheet({
                "timestamp": datetime.now().isoformat(),
                "user_name": st.session_state.user_name,
                "question_id": st.session_state.last_qnum,
                "correct": st.session_state.last_correct,
                "rating": "skip",
            })
            st.session_state.df = st.session_state.df[
                st.session_state.df["문제번호"] != question["문제번호"]
            ]
            get_new_question()
            st.session_state.answered = False
            st.rerun()

        if rating_col2.button("📘 이해 50~90%"):
            update_question_rating(user_progress_file, st.session_state.last_qnum, "mid")
            log_to_sheet({
                "timestamp": datetime.now().isoformat(),
                "user_name": st.session_state.user_name,
                "question_id": st.session_state.last_qnum,
                "correct": st.session_state.last_correct,
                "rating": "mid",
            })
            get_new_question()
            st.session_state.answered = False
            st.rerun()

        if rating_col3.button("🔄 이해 50% 미만"):
            update_question_rating(user_progress_file, st.session_state.last_qnum, "low")
            log_to_sheet({
                "timestamp": datetime.now().isoformat(),
                "user_name": st.session_state.user_name,
                "question_id": st.session_state.last_qnum,
                "correct": st.session_state.last_correct,
                "rating": "low",
            })
            get_new_question()
            st.session_state.answered = False
            st.rerun()

  
# 사이드바 요약 및 기타 기능 표시
st.sidebar.markdown("———")
st.sidebar.markdown(f"👤 사용자: **{st.session_state.user_name}**")
st.sidebar.markdown(f"✅ 정답 수: {st.session_state.score}")
st.sidebar.markdown(f"❌ 오답 수: {len(st.session_state.wrong_list)}")
st.sidebar.markdown(f"📊 총 풀어 수: {st.session_state.total}")
remaining = st.session_state.df.shape[0] if st.session_state.df is not None else 0
st.sidebar.markdown(f"📘 남은 문제: {remaining}")

st.sidebar.markdown("Made with ❤️ )


def save_wrong_answers_to_excel():
    """
    오답 리스트를 엑셀로 저장하는 기능을 수행합니다.
    저장 후 성공/실패 메시지를 사이드바에 출력합니다.
    """
    if not st.session_state.wrong_list:
        st.sidebar.warning("❗ 오답이 없습니다.")
        return

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


def show_weekly_ranking():
    """
    주간 랭킹을 출력하는 기능을 수행합니다.
    """
    display_weekly_ranking()


def show_wrong_list_table():
    """
    오답 리스트를 테이블로 출력하는 기능을 수행합니다.
    """
    if not st.session_state.wrong_list:
        st.warning("❗ 오답이 없습니다.")
        return

    wrong_df = pd.DataFrame(st.session_state.wrong_list)
    st.subheader("❗ 오답 목록")
    st.table(
        wrong_df[
            ["날짜", "문제번호", "단원명", "문제", "선택", "정답", "해설"]
        ]
    )


# 버튼 처리
if st.sidebar.button("📂 오답 엑셀로 저장"):
    save_wrong_answers_to_excel()

if st.sidebar.button("📈 주간 랭킹 보기"):
    show_weekly_ranking()

if st.sidebar.button("❔ 오답 목록 보기"):
    show_wrong_list_table()

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
    """애플리케이션 실행 진입점입니다."""
    init_session_state()
    if not st.session_state.logged_in:
        login_page()
        return
    main_page()

# Streamlit 앱을 실행할 때는 __name__ == "__main__" 조건으로 run_app 호출
if __name__ == "__main__":
    run_app()
