import os
from datetime import datetime, timedelta
import csv
import re
import json

import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
import gspread # gspread 라이브러리 추가
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound # 예외 처리 추가

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
        "prev_selected_file": None, # 스프레드시트 이름 (또는 ID + 시트 이름 조합)
        "prev_selected_chapter": None,
        "is_admin": False,
        "last_correct": None,
        "last_qnum": None,
        "sheet_log_status": None,
        "skip_ids": set(),
        "low_ids": set(),
        "user_progress_file": None,
        "exam_name": None,
        # "gsheet_files": [], # Google Drive에서 찾은 스프레드시트 목록 (사용하지 않음)
        "selected_gsheet_name": None, # 사용자가 선택한 스프레드시트 이름
        "selected_worksheet_name": None, # 사용자가 선택한 워크시트 이름
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

def connect_to_gspread() -> 'gspread.Client':
    """gspread 클라이언트 객체를 반환합니다."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive", # Drive API 접근을 위해 추가
    ]
    creds_data = st.secrets.get("GCP_CREDENTIALS", {})
    # GCP_CREDENTIALS가 문자열인 경우 JSON 파싱
    if isinstance(creds_data, str):
        try:
            creds_dict = json.loads(creds_data)
        except json.JSONDecodeError as e:
            st.error(f"GCP_CREDENTIALS 파싱 오류: {e}. secrets.toml 또는 Streamlit Secrets 형식을 확인하세요.")
            st.stop()
    else:
        creds_dict = dict(creds_data)

    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(credentials)
    return client

def log_to_sheet(data: dict):
    row = [
        str(data.get("timestamp") or ""),
        str(data.get("user_name") or ""),
        str(data.get("question_id") or ""),
        str(data.get("correct") or ""),
        str(data.get("rating") or ""),
        str(data.get("exam_name") or ""),
    ]
    try:
        client = connect_to_gspread()
        # oxquiz_progress_log 스프레드시트 이름은 고정
        sheet = client.open("oxquiz_progress_log").worksheet("시트1") # 진행 로그 시트 이름 확인 (여기선 '시트1')
        sheet.append_row(row)
        st.session_state.sheet_log_status = "✅ 구글 시트에 기록 성공!"
    except Exception as e:
        st.session_state.sheet_log_status = f"📛 구글 시트 기록 실패: {e}"
        st.error(f"📛 구글 시트 기록 실패: {e}")

def load_user_progress(username: str, exam_name:str=None):
    safe_name = get_safe_filename(username)
    fname = f"{safe_name}_{exam_name}_progress.csv" if exam_name else f"{safe_name}_progress.csv"
    file_path = os.path.join(USER_DATA_DIR, fname)
    skip_ids, low_ids, df = set(), set(), None
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path)
            if "rating" not in df.columns:
                df["rating"] = ""
            skip_ids = set(df[df["rating"] == "skip"]["question_id"].astype(str))
            low_ids = set(df[df["rating"] == "low"]["question_id"].astype(str))
        except Exception as e:
            st.warning(f"진행 파일을 읽는 중 오류가 발생했습니다: {e}")
    return skip_ids, low_ids, file_path, df

def update_session_progress_from_df(username: str, df):
    if df is None:
        st.session_state.score = 0
        st.session_state.total = 0
        st.session_state.wrong_list = []
        return
    st.session_state.total = len(df)
    st.session_state.score = df[df["correct"] == True].shape[0]
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
            df["question_id"] = df["question_id"].astype(str)
            df["rating"] = df["rating"].astype(str)
            mask = (df["question_id"] == question_id) & (df["rating"] == "")
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
        user_name = f"{name} ({group})" if group else name
        st.session_state.user_name = user_name
        st.session_state.exam_name = None # 로그인 시 시험 이름 초기화
        if password == "admin" or group.lower() in ("admin", "관리자"):
            st.session_state.is_admin = True
            st.session_state.logged_in = True
        elif password == "1234":
            st.session_state.is_admin = False
            st.session_state.logged_in = True
        else:
            st.error("❌ 암호가 틀렸습니다.")
            return
        
        # 로그인 시 기존 진행 상황 초기화 (문제집 선택에 따라 새로 로드됨)
        st.session_state.skip_ids = set()
        st.session_state.low_ids = set()
        st.session_state.user_progress_file = None
        st.session_state.df = None
        st.session_state.question = None
        st.session_state.answered = False
        st.session_state.prev_selected_file = None # 이전 파일 선택 기록 초기화
        st.session_state.prev_selected_chapter = None # 이전 단원 선택 기록 초기화

        st.rerun()

def load_and_filter_data(df_loaded: pd.DataFrame, selected_chapter: str, skip_ids: set, low_ids: set) -> None:
    """로드된 데이터프레임을 필터링하고 세션 상태에 저장합니다."""
    if df_loaded.empty:
        st.session_state.df = pd.DataFrame()
        st.session_state.question = None
        st.session_state.answered = False
        st.session_state.last_question = None
        return

    required_cols = {"문제", "정답"}
    missing = required_cols - set(df_loaded.columns)
    if missing:
        st.error(f"스프레드시트에 필수 열 {missing} 이/가 없습니다. 헤더를 확인하세요.")
        st.session_state.df = pd.DataFrame()
        st.session_state.question = None
        st.session_state.answered = False
        st.session_state.last_question = None
        return
    
    df_loaded = df_loaded.dropna(subset=["문제", "정답"]).copy() # 원본 DataFrame을 수정하지 않도록 copy() 사용
    
    if "문제번호" not in df_loaded.columns:
        df_loaded["문제번호"] = range(1, len(df_loaded) + 1)
    
    df_filtered = df_loaded.copy() # 필터링 시작 전 복사본 생성

    if selected_chapter != "전체 보기" and "단원명" in df_filtered.columns:
        df_filtered = df_filtered[df_filtered["단원명"] == selected_chapter]
    
    # skip_ids와 low_ids는 string 타입으로 다룸
    df_filtered["문제번호_str"] = df_filtered["문제번호"].astype(str)

    if skip_ids:
        df_filtered = df_filtered[~df_filtered["문제번호_str"].isin(skip_ids)]
    
    if low_ids:
        # low_ids는 필터링된 데이터에 다시 추가
        low_df = df_loaded[df_loaded["문제번호_str"].isin(low_ids)]
        if not low_df.empty:
            # 기존 필터링된 df_filtered와 low_df를 합칠 때 중복 제거
            df_filtered = pd.concat([df_filtered, low_df]).drop_duplicates(subset=["문제번호_str"]).reset_index(drop=True)
            
    df_filtered = df_filtered.drop(columns=["문제번호_str"]) # 임시 컬럼 제거

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

def save_wrong_answers_to_excel():
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
    display_weekly_ranking()

def show_wrong_list_table():
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

# @st.cache_data(ttl=3600) # 더 이상 Google Drive 폴더 탐색을 하지 않으므로 캐시 데코레이터 제거
# def get_gsheets_in_drive(folder_name: str = None) -> list:
#     """
#     Google Drive에서 특정 폴더 내의 Google 스프레드시트 목록을 가져옵니다.
#     gspread는 Drive 폴더를 직접 탐색하는 기능을 지원하지 않습니다.
#     이 함수는 더 이상 사용되지 않습니다.
#     """
#     st.error("이 함수는 더 이상 사용되지 않습니다. get_gsheets_in_drive 함수를 호출하지 마세요.")
#     return []


@st.cache_data(ttl=3600) # 1시간 캐시
def get_worksheet_names(spreadsheet_id: str) -> list:
    """특정 스프레드시트의 워크시트 이름을 가져옵니다."""
    try:
        client = connect_to_gspread()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheets = spreadsheet.worksheets()
        return [ws.title for ws in worksheets]
    except SpreadsheetNotFound:
        st.error("지정된 스프레드시트 ID를 찾을 수 없습니다. ID가 올바른지 확인하세요.")
        return []
    except Exception as e:
        st.error(f"워크시트 이름을 가져오는 중 오류가 발생했습니다: {e}")
        return []

@st.cache_data(ttl=3600) # 1시간 캐시
def load_data_from_google_sheet(spreadsheet_id: str, worksheet_name: str) -> pd.DataFrame:
    """특정 Google 스프레드시트의 워크시트에서 데이터를 로드합니다."""
    try:
        client = connect_to_gspread()
        sheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        return df
    except SpreadsheetNotFound:
        st.error(f"Google 스프레드시트 ID '{spreadsheet_id}'를 찾을 수 없습니다. ID를 확인하세요.")
        return pd.DataFrame()
    except WorksheetNotFound:
        st.error(f"워크시트 '{worksheet_name}'를 찾을 수 없습니다. 이름을 확인하세요.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Google 스프레드시트에서 데이터를 읽는 중 오류가 발생했습니다: {e}")
        return pd.DataFrame()

def main_page() -> None:
    st.title("📘 공인중개사 OX 퀴즈")
    st.sidebar.header("📂 문제집 선택")

    if st.session_state.sheet_log_status:
        st.info(st.session_state.sheet_log_status)
        st.session_state.sheet_log_status = None

    # Google Drive에서 스프레드시트 목록 가져오기 로직 제거
    # 대신 사용자가 직접 스프레드시트 이름/ID를 입력하거나, 미리 정의된 목록에서 선택
    
    # 미리 정의된 스프레드시트 목록 또는 ID를 여기서 관리
    # 예시: { "문제집 이름": "스프레드시트_ID_또는_정확한_이름" }
    # 실제 Google Drive의 "퀴즈 문제집" 폴더에 있는 스프레드시트 이름과 ID를 사용하세요.
    # ID가 더 정확합니다. ID는 스프레드시트 URL에서 https://docs.google.com/spreadsheets/d/여기부터가ID/edit#gid=... 형식입니다.
    
    # -------------------------------------------------------------
    # TODO: 여기에 실제 스프레드시트 ID와 이름(선택 사항)을 입력하세요!
    # 이 부분은 수동으로 작성해야 합니다.
    # 예시: "2차 세법" 시트의 ID가 "1a2b3c4d5e6f..." 라면 아래처럼
    
    # your_gsheet_options = {
    #     "1차 민법": "1x-abcdeFGHIJKLMNOPQRSTUVW",
    #     "2차 중개사법": "1y-abcdeFGHIJKLMNOPQRSTUVW",
    #     "2차 세법": "1z-abcdeFGHIJKLMNOPQRSTUVW",
    #     # 더 많은 문제집이 있다면 여기에 추가하세요
    # }
    
    # 스크린샷에서 확인된 스프레드시트들의 ID를 Google Drive에서 직접 복사하여 넣으세요.
    # 각 스프레드시트를 Google Drive에서 열고, URL에서 ID 부분을 복사하시면 됩니다.
    your_gsheet_options = {
        "1차 민법": "12wJkK8K7L0M1N2O3P4Q5R6S7T8U9V0W", # 실제 ID로 변경 필요
        "2차 중개사법": "1x-ABCDEFG_HIJKLMNOPQRSTUV", # 실제 ID로 변경 필요
        "2차 세법": "1y-UVWXYZ_ABCDEFGHIJKLMNO", # 실제 ID로 변경 필요
        "oxquiz_progress_log": "1z-PQRSTUV_WXYZABCDEFGH", # 로그 시트도 필요하다면 추가
    }
    # -------------------------------------------------------------

    if not your_gsheet_options:
        st.error("⚠️ 문제집 스프레드시트 ID를 코드에 설정해야 합니다.")
        st.stop() # 설정이 안되면 앱 중단

    selected_gsheet_name = st.sidebar.selectbox(
        "문제집 스프레드시트를 선택하세요",
        options=["선택하세요"] + list(your_gsheet_options.keys()),
        key="gsheet_select"
    )

    selected_spreadsheet_id = None
    selected_worksheet_name = None
    df_source = pd.DataFrame()
    file_label = None

    if selected_gsheet_name and selected_gsheet_name != "선택하세요":
        selected_spreadsheet_id = your_gsheet_options[selected_gsheet_name]
        st.session_state.selected_gsheet_name = selected_gsheet_name # 세션 상태 저장

        # 선택된 스프레드시트의 워크시트 목록 가져오기
        worksheet_names = get_worksheet_names(selected_spreadsheet_id)
        if not worksheet_names:
            st.warning("선택된 스프레드시트에 워크시트가 없습니다.")
            return
        
        # 워크시트 선택
        selected_worksheet_name = st.sidebar.selectbox(
            "문제 시트를 선택하세요",
            options=["선택하세요"] + worksheet_names,
            key="worksheet_select"
        )
        st.session_state.selected_worksheet_name = selected_worksheet_name # 세션 상태 저장

        if selected_worksheet_name and selected_worksheet_name != "선택하세요":
            df_source = load_data_from_google_sheet(selected_spreadsheet_id, selected_worksheet_name)
            if not df_source.empty:
                file_label = f"{selected_gsheet_name} - {selected_worksheet_name}"
            else:
                st.warning("⚠️ 선택된 Google 스프레드시트 시트에서 데이터를 불러오지 못했습니다. 내용을 확인하세요.")
                return
    
    if not file_label:
        st.warning("⚠️ 문제집 스프레드시트와 시트를 선택하세요.")
        return

    # 파일명(문제집명) 세션 동기화
    st.session_state.exam_name = file_label

    # 문제집(스프레드시트+워크시트)이 바뀔 때마다 진도 복원
    current_file_identifier = f"{selected_gsheet_name}_{selected_worksheet_name}"
    if st.session_state.get("prev_selected_file", None) != current_file_identifier or st.session_state.df is None:
        st.session_state.prev_selected_file = current_file_identifier
        skip_ids, low_ids, user_progress_file, df_progress = load_user_progress(
            st.session_state.user_name, file_label # exam_name으로 file_label 사용
        )
        st.session_state.skip_ids = skip_ids
        st.session_state.low_ids = low_ids
        st.session_state.user_progress_file = user_progress_file
        update_session_progress_from_df(st.session_state.user_name, df_progress)

        # 단원명 목록 가져오기
        df_loaded_temp = df_source.dropna(subset=["문제", "정답"])
        chapters = sorted(df_loaded_temp["단원명"].dropna().unique()) if "단원명" in df_loaded_temp.columns else []
        selected_chapter = st.sidebar.selectbox(
            "특정 단원만 푸시겠습니까?", ["전체 보기"] + chapters, key="chapter_select"
        )
        st.session_state.prev_selected_chapter = selected_chapter
        load_and_filter_data(df_source, selected_chapter, skip_ids, low_ids)
    else:
        # 파일이 바뀌지 않았고, 단원이 바뀌었을 때
        df_loaded_temp = df_source.dropna(subset=["문제", "정답"])
        chapters = sorted(df_loaded_temp["단원명"].dropna().unique()) if "단원명" in df_loaded_temp.columns else []
        selected_chapter = st.sidebar.selectbox(
            "특정 단원만 푸시겠습니까?", ["전체 보기"] + chapters, key="chapter_select"
        )
        if st.session_state.get("prev_selected_chapter", None) != selected_chapter:
            st.session_state.prev_selected_chapter = selected_chapter
            load_and_filter_data(df_source, selected_chapter, st.session_state.skip_ids, st.session_state.low_ids)


    accuracy = (st.session_state.score / st.session_state.total * 100) if st.session_state.total > 0 else 0.0
    st.sidebar.markdown(f"🎯 정답률: {accuracy:.1f}%")
    remaining_local = st.session_state.df.shape[0] if st.session_state.df is not None else 0
    st.sidebar.markdown(f"📝 남은 문제: {remaining_local}개")

    if st.session_state.df is None or st.session_state.df.empty:
        st.warning("선택된 스프레드시트에 문제 데이터가 없거나, 데이터를 불러오지 못했습니다.")
        return
    st.write(f"현재 선택된 문제집: **{st.session_state.exam_name}**")
    st.write("문제집의 열(헤더):", st.session_state.df.columns.tolist()) # 컬럼 목록 보기 좋게 출력

    if "문제" not in st.session_state.df.columns or "정답" not in st.session_state.df.columns:
        st.error("스프레드시트에 '문제' 또는 '정답' 열이 없습니다. 헤더를 확인하세요.")
        st.stop()

    if st.session_state.question is None:
        get_new_question()
    if st.session_state.question is None:
        st.info("선택한 단원에 문제 데이터가 없거나, 이전에 모두 풀었습니다.")
        st.stop()

    question = st.session_state.question
    qnum = question["문제번호"]
    try:
        qnum_display = int(qnum)
    except Exception:
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

    user_progress_file = st.session_state.get("user_progress_file", None)

    if user_answer:
        st.session_state.total += 1
        st.session_state.answered = True
        st.session_state.last_question = question.copy()
        record_user_activity()

        correct = (user_answer == question["정답"])
        if correct:
            st.session_state.score += 1
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
                "해설": question["해설"] if ("해설" in question and pd.notna(question["해설"])) else "",
            })
            st.error(f"❌ 오답입니다. 정답은 {question['정답']}")

        data_to_save = {
            "timestamp": datetime.now().isoformat(),
            "user_name": st.session_state.user_name,
            "question_id": str(qnum_display),
            "correct": correct,
            "rating": "",
            "chapter": question.get("단원명", ""),
            "question": question["문제"],
            "correct_answer": question["정답"],
            "answer": user_answer,
            "explanation": question["해설"] if ("해설" in question and pd.notna(question["해설"])) else "",
        }
        if user_progress_file:
            save_user_progress(user_progress_file, data_to_save)
        st.session_state.last_correct = correct
        st.session_state.last_qnum = str(qnum_display)

    if st.session_state.answered and st.session_state.last_question is not None:
        last_q = st.session_state.last_question
        if "해설" in last_q and pd.notna(last_q["해설"]):
            st.info(f"📘 해설: {last_q['해설']}")
        rating_col1, rating_col2, rating_col3 = st.columns(3)

        if rating_col1.button("❌ 다시 보지 않기"):
            if user_progress_file:
                update_question_rating(user_progress_file, st.session_state.last_qnum, "skip")
            log_to_sheet({
                "timestamp": datetime.now().isoformat(),
                "user_name": st.session_state.user_name,
                "question_id": st.session_state.last_qnum,
                "correct": st.session_state.last_correct,
                "rating": "skip",
                "exam_name": st.session_state.exam_name,
            })
            st.session_state.df = st.session_state.df[
                st.session_state.df["문제번호"].astype(str) != st.session_state.last_qnum
            ]
            get_new_question()
            st.session_state.answered = False
            st.rerun()

        if rating_col2.button("📘 이해 50~90%"):
            if user_progress_file:
                update_question_rating(user_progress_file, st.session_state.last_qnum, "mid")
            log_to_sheet({
                "timestamp": datetime.now().isoformat(),
                "user_name": st.session_state.user_name,
                "question_id": st.session_state.last_qnum,
                "correct": st.session_state.last_correct,
                "rating": "mid",
                "exam_name": st.session_state.exam_name,
            })
            get_new_question()
            st.session_state.answered = False
            st.rerun()

        if rating_col3.button("🔄 이해 50% 미만"):
            if user_progress_file:
                update_question_rating(user_progress_file, st.session_state.last_qnum, "low")
            log_to_sheet({
                "timestamp": datetime.now().isoformat(),
                "user_name": st.session_state.user_name,
                "question_id": st.session_state.last_qnum,
                "correct": st.session_state.last_correct,
                "rating": "low",
                "exam_name": st.session_state.exam_name,
            })
            get_new_question()
            st.session_state.answered = False
            st.rerun()

    st.sidebar.markdown("———")
    st.sidebar.markdown(f"👤 사용자: **{st.session_state.user_name}**")
    st.sidebar.markdown(f"✅ 정답 수: {st.session_state.score}")
    st.sidebar.markdown(f"❌ 오답 수: {len(st.session_state.wrong_list)}")
    st.sidebar.markdown(f"📊 총 풀어 수: {st.session_state.total}")
    remaining_count = st.session_state.df.shape[0] if st.session_state.df is not None else 0
    st.sidebar.markdown(f"📘 남은 문제: {remaining_count}")

    if st.sidebar.button("📂 오답 엑셀로 저장"):
        save_wrong_answers_to_excel()
    if st.sidebar.button("📈 주간 랭킹 보기"):
        show_weekly_ranking()
    if st.sidebar.button("❔ 오답 목록 보기"):
        show_wrong_list_table()

def run_app() -> None:
    init_session_state()
    if not st.session_state.logged_in:
        login_page()
        return
    main_page()

if __name__ == "__main__":
    run_app()
