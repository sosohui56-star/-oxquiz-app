import os
from datetime import datetime, timedelta
import csv
import re
import json

import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
import gspread
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound

# Google Drive API 접근을 위한 추가 라이브러리
from googleapiclient.discovery import build # <--- 이 줄 추가
from google.auth.transport.requests import Request # <--- 이 줄 추가
import google.auth.httplib2 # <--- 이 줄 추가 (이거 없으면 에러 날 수 있음)

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
        "last_correct": None,
        "last_qnum": None,
        "sheet_log_status": None,
        "skip_ids": set(),
        "low_ids": set(),
        "user_progress_file": None,
        "exam_name": None,
        "gsheet_files": [], # 다시 사용!
        "selected_gsheet_name": None,
        "selected_worksheet_name": None,
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
        "https://www.googleapis.com/auth/drive.readonly", # Drive API 목록 조회용 (필요시)
    ]
    creds_data = st.secrets.get("GCP_CREDENTIALS", {})
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

# 새롭게 Drive API를 사용하는 함수
@st.cache_data(ttl=3600) # 1시간 캐시
def get_gsheets_in_drive_with_drive_api(folder_name: str = None) -> list:
    """
    Google Drive API를 직접 사용하여 특정 폴더 내의 Google 스프레드시트 목록을 가져옵니다.
    """
    try:
        creds_data = st.secrets.get("GCP_CREDENTIALS", {})
        if isinstance(creds_data, str):
            creds_dict = json.loads(creds_data)
        else:
            creds_dict = dict(creds_data)

        # Drive API에 필요한 스코프
        # Drive API v3는 "https://www.googleapis.com/auth/drive" 또는 "https://www.googleapis.com/auth/drive.readonly" 스코프 필요
        # 스프레드시트 파일 목록만 가져올 것이므로 readonly로 충분함
        credentials = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/drive.readonly"] # Drive API용 ReadOnly 권한
        )

        # HTTP 클라이언트 빌드
        http = google.auth.httplib2.AuthorizedHttp(credentials)
        
        # Drive API 서비스 빌드
        drive_service = build("drive", "v3", http=http) # <--- Drive API v3 사용

        files_list = []
        if folder_name:
            # 폴더 ID를 먼저 검색
            # q 매개변수: mimeType='application/vnd.google-apps.folder' (폴더), name='폴더이름', trashed=false (휴지통 X)
            folder_query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
            folder_results = drive_service.files().list(
                q=folder_query,
                spaces='drive',
                fields='nextPageToken, files(id, name)'
            ).execute().get('files', [])

            if not folder_results:
                st.warning(f"Google Drive에서 폴더 '{folder_name}'를 찾을 수 없습니다. 모든 스프레드시트를 검색합니다.")
                # 폴더를 찾지 못했으면 폴더 필터 없이 모든 스프레드시트 검색 (이전과 동일)
                spreadsheet_query = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
                results = drive_service.files().list(
                    q=spreadsheet_query,
                    spaces='drive',
                    fields='nextPageToken, files(id, name)',
                    orderBy="name"
                ).execute()
                files_list = results.get('files', [])
            else:
                folder_id = folder_results[0]['id']
                # 폴더 ID를 사용하여 해당 폴더 내의 스프레드시트만 검색
                spreadsheet_query = f"mimeType='application/vnd.google-apps.spreadsheet' and '{folder_id}' in parents and trashed=false"
                results = drive_service.files().list(
                    q=spreadsheet_query,
                    spaces='drive',
                    fields='nextPageToken, files(id, name)',
                    orderBy="name"
                ).execute()
                files_list = results.get('files', [])
        else:
            # 폴더 이름이 없으면 모든 스프레드시트 검색
            spreadsheet_query = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
            results = drive_service.files().list(
                q=spreadsheet_query,
                spaces='drive',
                fields='nextPageToken, files(id, name)',
                orderBy="name"
            ).execute()
            files_list = results.get('files', [])

        return [{'id': f['id'], 'name': f['name']} for f in files_list]
    except Exception as e:
        st.error(f"Google Drive에서 스프레드시트 목록을 가져오는 중 오류가 발생했습니다: {e}")
        st.warning("Google Drive API 권한 및 서비스 계정 설정이 올바른지 확인해주세요.")
        return []

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
        # 주의: 이 시트도 서비스 계정에 공유되어야 합니다.
        sheet = client.open("oxquiz_progress_log").worksheet("시트1")
        sheet.append_row(row)
        st.session_state.sheet_log_status = "✅ 구글 시트에 기록 성공!"
    except Exception as e:
        st.session_state.sheet_log_status = f"📛 구글 시트 기록 실패: {e}"
        st.error(f"📛 구글 시트 기록 실패: {e}")

# ... (나머지 함수들은 이전과 동일) ...

def main_page() -> None:
    st.title("📘 공인중개사 OX 퀴즈")
    st.sidebar.header("📂 문제집 선택")

    if st.session_state.sheet_log_status:
        st.info(st.session_state.sheet_log_status)
        st.session_state.sheet_log_status = None

    # Google Drive 폴더 이름 설정
    quiz_folder_name = "퀴즈 문제집"

    # get_gsheets_in_drive_with_drive_api 함수를 사용하여 목록 가져오기
    if not st.session_state.gsheet_files: # st.session_state.gsheet_files가 비어있을 때만 새로 가져옴
        st.session_state.gsheet_files = get_gsheets_in_drive_with_drive_api(quiz_folder_name)
    
    if not st.session_state.gsheet_files:
        st.warning("Google Drive에서 문제집 스프레드시트를 찾을 수 없습니다. 폴더 이름('퀴즈 문제집')을 확인하거나, 서비스 계정에 해당 폴더/파일에 대한 접근 권한이 있는지 확인하세요.")
        st.warning(f"팁: '{quiz_folder_name}' 폴더를 생성하고 서비스 계정 이메일 주소({st.secrets.get('GCP_CREDENTIALS', {}).get('client_email', '클라이언트 이메일 없음')})와 공유해주세요.")
        return # 더 이상 진행하지 않음

    gsheet_options = {f['name']: f['id'] for f in st.session_state.gsheet_files}
    
    selected_gsheet_name = st.sidebar.selectbox(
        "문제집 스프레드시트를 선택하세요",
        options=["선택하세요"] + sorted(list(gsheet_options.keys())), # 이름으로 정렬하여 표시
        key="gsheet_select"
    )

    selected_spreadsheet_id = None
    selected_worksheet_name = None
    df_source = pd.DataFrame()
    file_label = None

    if selected_gsheet_name and selected_gsheet_name != "선택하세요":
        selected_spreadsheet_id = gsheet_options[selected_gsheet_name]
        st.session_state.selected_gsheet_name = selected_gsheet_name

        worksheet_names = get_worksheet_names(selected_spreadsheet_id)
        if not worksheet_names:
            st.warning("선택된 스프레드시트에 워크시트가 없습니다.")
            return
        
        selected_worksheet_name = st.sidebar.selectbox(
            "문제 시트를 선택하세요",
            options=["선택하세요"] + worksheet_names,
            key="worksheet_select"
        )
        st.session_state.selected_worksheet_name = selected_worksheet_name

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

    # ... (나머지 main_page 함수 내용은 동일) ...

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
