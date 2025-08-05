import os
from datetime import datetime
import csv
import re
import json
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
import gspread
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound

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
        "question_index": 0,  # 현재 문제 인덱스
        "df": None,
        "filtered_df": None,
        "is_admin": False,
        "user_progress_file": None,
        "exam_name": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def connect_to_gspread() -> gspread.Client:
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    try:
        creds_dict = st.secrets["GCP_CREDENTIALS"]
        if isinstance(creds_dict, str):
            creds_dict = json.loads(creds_dict)
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.error(f"Google Sheets 연결 오류: {e}")
        st.stop()

def load_data_from_google_sheet(spreadsheet_url_or_id: str, worksheet_name: str = None) -> pd.DataFrame:
    try:
        client = connect_to_gspread()
        if "docs.google.com" in spreadsheet_url_or_id:
            import re
            m = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', spreadsheet_url_or_id)
            if not m:
                st.error("올바른 Google Sheets URL이 아닙니다.")
                return pd.DataFrame()
            sheet_id = m.group(1)
        else:
            sheet_id = spreadsheet_url_or_id
        spreadsheet = client.open_by_key(sheet_id)
        if worksheet_name:
            worksheet = spreadsheet.worksheet(worksheet_name)
        else:
            worksheet = spreadsheet.sheet1
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        st.error(f"Google 스프레드시트에서 데이터를 읽는 중 오류가 발생했습니다: {e}")
        return pd.DataFrame()

def get_question_by_index(index: int):
    df = st.session_state.filtered_df
    if df is None or df.empty or index < 0 or index >= len(df):
        return None
    return df.iloc[index]

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
        st.session_state.exam_name = None
        if password == "admin" or group.lower() in ("admin", "관리자"):
            st.session_state.is_admin = True
            st.session_state.logged_in = True
        elif password == "1234":
            st.session_state.is_admin = False
            st.session_state.logged_in = True
        else:
            st.error("❌ 암호가 틀렸습니다.")
            return
        st.session_state.filtered_df = None
        st.session_state.question_index = 0

def record_user_activity():
    # 간략하게 기록 예시(진행 구현에 맞게 확장 가능)
    try:
        with open("progress_log.csv", "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([st.session_state.user_name, datetime.now().isoformat()])
    except Exception:
        pass

def main_page():
    st.title("📘 공인중개사 OX 퀴즈")
    st.sidebar.header("📂 문제집 선택")

    predefined_sheets = {
        "1차 민법": "1Z9Oz04vuV7f5hbzrZ3iyn71RuB6bg0FEAL9_z10hyvs",
        "1차 학개론": "1LGlF9dUsuRsl3DVwIkHdm3XZzOCHojoYXbC2J_8RXuo",
        "2차 공법": "1L1N6lasmt8rvVDbD3NqTJlvzIz1cRBSCqGI3Bvw6a4Y",
        "2차 공시법": "1DP-AuJ5AaMoMMDiXwMYTy4eVIpAOKnh2PXVVtgS2O_Y",
        "2차 세법": "1prNQuzxdytOPzxpGKZw-aa76ud7RepkemIDlWpWCpMo",
        "2차 중개사법": "1Lkz9_f7040gjryUxTRcbU-4NTNucBXijK9RMlL6y_QY"
    }

    sheets_url = st.sidebar.text_input("Google Sheets URL을 입력하세요")
    selected_predefined = st.sidebar.selectbox("또는 미리 정의된 문제집에서 선택", ["선택안함"] + list(predefined_sheets.keys()))

    if sheets_url:
        spreadsheet_source = sheets_url
        sheet_name = "사용자 입력 시트"
    elif selected_predefined != "선택안함":
        spreadsheet_source = predefined_sheets[selected_predefined]
        sheet_name = selected_predefined
    else:
        st.sidebar.warning("Google Sheets URL을 입력하거나 미리 정의된 시트를 선택하세요.")
        st.session_state.filtered_df = None
        return

    worksheet_name = st.sidebar.text_input("워크시트 이름 (빈칸이면 첫 번째 시트)", placeholder="Sheet1")

    if st.sidebar.button("문제집 로드"):
        with st.spinner("문제집을 불러오는 중..."):
            df = load_data_from_google_sheet(spreadsheet_source, worksheet_name)
            if df.empty:
                st.error("데이터가 없습니다.")
                st.session_state.filtered_df = None
                return
            st.session_state.df = df
            st.session_state.exam_name = sheet_name
            st.session_state.filtered_df = df
            st.session_state.question_index = 0

    if st.session_state.filtered_df is None:
        st.info("문제집을 먼저 로드해주세요.")
        return

    # 단원 필터링
    if "단원명" in st.session_state.df.columns:
        chapters = ["전체 보기"] + sorted(st.session_state.df["단원명"].dropna().unique())
        selected_chapter = st.selectbox("단원 선택", chapters)
        if selected_chapter != "전체 보기":
            filtered = st.session_state.df[st.session_state.df["단원명"] == selected_chapter]
            st.session_state.filtered_df = filtered.reset_index(drop=True)
            st.session_state.question_index = 0
        else:
            st.session_state.filtered_df = st.session_state.df.reset_index(drop=True)
            st.session_state.question_index = 0
    else:
        if st.session_state.filtered_df is None:
            st.session_state.filtered_df = st.session_state.df.reset_index(drop=True)
            st.session_state.question_index = 0

    df_filtered = st.session_state.filtered_df
    qidx = st.session_state.question_index

    if len(df_filtered) == 0:
        st.warning("조건에 맞는 문제가 없습니다.")
        return

    question = get_question_by_index(qidx)
    if question is None:
        st.warning("문제를 불러올 수 없습니다.")
        return

    st.write(f"**단원:** {question.get('단원명', '')}")
    st.write(f"**문제번호:** {question.get('문제번호', '')}")
    st.write(f"**문제:** {question.get('문제', '')}")

    col1, col2, col3 = st.columns(3)
    answer = None
    if col1.button("⭕ O", key="O"):
        answer = "O"
    if col2.button("❌ X", key="X"):
        answer = "X"
    if col3.button("⁉️ 모름", key="Unknown"):
        answer = "모름"

    if answer is not None:
        st.session_state.total += 1
        correct = (answer == question.get('정답', ''))
        if correct:
            st.session_state.score += 1
            st.success("✅ 정답입니다!")
        else:
            st.error(f"❌ 오답입니다. 정답은 {question.get('정답', '')}입니다.")
            st.session_state.wrong_list.append({
                "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "문제번호": question.get("문제번호", ""),
                "단원명": question.get("단원명", ""),
                "문제": question.get("문제", ""),
                "정답": question.get("정답", ""),
                "선택": answer,
                "해설": question.get("해설", "")
            })
        record_user_activity()

    # 이전/다음 버튼 배치
    col_prev, col_next = st.columns(2)
    if col_prev.button("⬅ 이전 문제"):
        if st.session_state.question_index > 0:
            st.session_state.question_index -= 1
            st.experimental_rerun()
    if col_next.button("다음 문제 ➡"):
        if st.session_state.question_index < len(df_filtered) - 1:
            st.session_state.question_index += 1
            st.experimental_rerun()

    # 사이드바 상태 출력
    st.sidebar.write(f"👤 사용자: {st.session_state.user_name}")
    st.sidebar.write(f"✅ 정답 수: {st.session_state.score}")
    st.sidebar.write(f"❌ 오답 수: {len(st.session_state.wrong_list)}")
    st.sidebar.write(f"📊 총 풀 문제: {len(df_filtered)}")
    st.sidebar.write(f"현재 문제: {st.session_state.question_index + 1} / {len(df_filtered)}")

    if st.sidebar.button("오답 다운로드 (엑셀)"):
        if st.session_state.wrong_list:
            df_wrong = pd.DataFrame(st.session_state.wrong_list)
            filename = f"{get_safe_filename(st.session_state.user_name)}_wrong.xlsx"
            df_wrong.to_excel(filename, index=False)
            with open(filename, "rb") as f:
                btn = st.sidebar.download_button(
                    label="오답파일 다운로드",
                    data=f,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.sidebar.info("오답이 없습니다.")

def run_app() -> None:
    init_session_state()
    rerun_if_needed()

    if not st.session_state.logged_in:
        login_page()
        return
    main_page()

if __name__=="__main__":
    run_app()
