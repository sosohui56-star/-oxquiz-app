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
        "filtered_df": None,
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
        "selected_gsheet_name": None,
        "selected_worksheet_name": None,
        "need_rerun": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def rerun_if_needed():
    if st.session_state.get("need_rerun", False):
        st.session_state["need_rerun"] = False
        try:
            st.experimental_rerun()
        except AttributeError:
            try:
                st.session_state["rerun"] = True
                st.experimental_rerun()
            except Exception:
                pass

def connect_to_gspread() -> gspread.Client:
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
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
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Google Sheets 데이터 로드 오류: {e}")
        return pd.DataFrame()

def get_new_question():
    df = st.session_state.filtered_df
    if df is not None and not df.empty:
        st.session_state.question = df.sample(1).iloc[0]
    else:
        st.session_state.question = None

def main_page():
    rerun_if_needed()

    st.title("📘 공인중개사 OX 퀴즈")
    st.sidebar.header("📂 문제집 선택")

    # Show log status if exists
    if st.session_state.sheet_log_status:
        st.info(st.session_state.sheet_log_status)
        st.session_state.sheet_log_status = None

    predefined_sheets = {
        "1차 민법": "1Z9Oz04vuV7f5hbzrZ3iyn71RuB6bg0FEAL9_z10hyvs",
        "1차 학개론": "1LGlF9dUsuRsl3DVwIkHdm3XZzOCHojoYXbC2J_8RXuo",
        "2차 공법": "1L1N6lasmt8rvVDbD3NqTJlvzIz1cRBSCqGI3Bvw6a4Y",
        "2차 공시법": "1DP-AuJ5AaMoMMDiXwMYTy4eVIpAOKnh2PXVVtgS2O_Y",
        "2차 세법": "1prNQuzxdytOPzxpGKZw-aa76ud7RepkemIDlWpWCpMo",
        "2차 중개사법": "1Lkz9_f7040gjryUxTRcbU-4NTNucBXijK9RMlL6y_QY"
    }

    sheets_url = st.sidebar.text_input("Google Sheets URL을 입력하세요", help="Google Sheets의 공유 링크를 입력하세요")
    selected_predefined = st.sidebar.selectbox("또는 미리 정의된 문제집에서 선택", ["선택안함"] + list(predefined_sheets.keys()))

    if sheets_url:
        spreadsheet_source = sheets_url
        sheet_name = "사용자 입력 시트"
    elif selected_predefined != "선택안함":
        spreadsheet_source = predefined_sheets[selected_predefined]
        sheet_name = selected_predefined
    else:
        st.sidebar.warning("Google Sheets URL을 입력하거나 미리 정의된 시트를 선택하세요.")
        st.session_state.filtered_df = pd.DataFrame()
        return

    worksheet_name = st.sidebar.text_input("워크시트 이름 (비워두면 첫 번째 시트 사용)", placeholder="Sheet1")

    if st.sidebar.button("문제집 로드"):
        with st.spinner("문제집을 불러오는 중..."):
            df_source = load_data_from_google_sheet(spreadsheet_source, worksheet_name)
            if not df_source.empty:
                st.session_state.df = df_source
                st.session_state.exam_name = sheet_name
                st.success(f"✅ '{sheet_name}' 문제집이 성공적으로 로드되었습니다!")
                st.write(f"총 {len(df_source)}개의 문제가 있습니다.")
                st.write("문제집 구조:", df_source.columns.tolist())
                with st.expander("첫 번째 문제 예시 보기"):
                    st.write(df_source.head(1))
                st.session_state.filtered_df = df_source.copy()
                st.session_state.question = None
                st.session_state.need_rerun = True
            else:
                st.error("❌ 문제집 데이터가 비어있습니다.")
                st.session_state.filtered_df = pd.DataFrame()
                st.session_state.need_rerun = False

    # 필터링 문제 없으면 안내
    if st.session_state.filtered_df is None or st.session_state.filtered_df.empty:
        st.info("📝 위에서 Google Sheets 문제집을 먼저 로드해주세요.")
        return

    # 단원 필터링
    if "단원명" in st.session_state.df.columns:
        chapters = ["전체 보기"] + sorted(st.session_state.df["단원명"].dropna().unique().tolist())
        selected_chapter = st.selectbox("단원 선택", chapters)
        if selected_chapter != "전체 보기":
            filtered_df = st.session_state.df[st.session_state.df["단원명"] == selected_chapter]
        else:
            filtered_df = st.session_state.df.copy()
    else:
        filtered_df = st.session_state.df.copy()

    st.session_state.filtered_df = filtered_df.reset_index(drop=True)

    if filtered_df.empty:
        st.info("📝 위에서 Google Sheets 문제집을 먼저 로드해주세요.")
        return

    # 문제 뽑기
    if st.session_state.question is None:
        get_new_question()

    question = st.session_state.question
    if question is None:
        st.warning("문제가 없습니다.")
        return

    # 문제 출력
    st.write(f"**단원:** {question.get('단원명', '') if '단원명' in question else ''}")
    try:
        qnum_display = int(question.get("문제번호", ""))
    except Exception:
        qnum_display = question.get("문제번호", "")
    st.write(f"**문제번호:** {qnum_display}")
    st.write(f"**문제:** {question['문제']}")

    # 답변 버튼
    col1, col2, col3 = st.columns(3)
    user_answer = None
    if col1.button("⭕ O", use_container_width=True):
        user_answer = "O"
    elif col2.button("❌ X", use_container_width=True):
        user_answer = "X"
    elif col3.button("⁉️ 모름", use_container_width=True):
        user_answer = "모름"

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
                "해설": question.get("해설", ""),
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
            "explanation": question.get("해설", ""),
        }
        if st.session_state.user_progress_file:
            save_user_progress(st.session_state.user_progress_file, data_to_save)
        st.session_state.last_correct = correct
        st.session_state.last_qnum = str(qnum_display)

    # 이해도 버튼 및 다음 문제 처리
    if st.session_state.answered and st.session_state.last_question is not None:
        last_q = st.session_state.last_question
        if last_q.get("해설"):
            st.info(f"📘 해설: {last_q['해설']}")

        rating_col1, rating_col2, rating_col3 = st.columns(3)

        def set_rerun_flag():
            st.session_state.answered = False
            st.session_state.need_rerun = True

        if rating_col1.button("❌ 다시 보지 않기"):
            if st.session_state.user_progress_file:
                update_question_rating(st.session_state.user_progress_file, st.session_state.last_qnum, "skip")
            log_to_sheet({
                "timestamp": datetime.now().isoformat(),
                "user_name": st.session_state.user_name,
                "question_id": st.session_state.last_qnum,
                "correct": st.session_state.last_correct,
                "rating": "skip",
                "exam_name": st.session_state.exam_name,
            })
            st.session_state.filtered_df = st.session_state.filtered_df[
                st.session_state.filtered_df["문제번호"].astype(str) != st.session_state.last_qnum
            ].reset_index(drop=True)
            get_new_question()
            set_rerun_flag()

        if rating_col2.button("📘 이해 50~90%"):
            if st.session_state.user_progress_file:
                update_question_rating(st.session_state.user_progress_file, st.session_state.last_qnum, "mid")
            log_to_sheet({
                "timestamp": datetime.now().isoformat(),
                "user_name": st.session_state.user_name,
                "question_id": st.session_state.last_qnum,
                "correct": st.session_state.last_correct,
                "rating": "mid",
                "exam_name": st.session_state.exam_name,
            })
            get_new_question()
            set_rerun_flag()

        if rating_col3.button("🔄 이해 50% 미만"):
            if st.session_state.user_progress_file:
                update_question_rating(st.session_state.user_progress_file, st.session_state.last_qnum, "low")
            log_to_sheet({
                "timestamp": datetime.now().isoformat(),
                "user_name": st.session_state.user_name,
                "question_id": st.session_state.last_qnum,
                "correct": st.session_state.last_correct,
                "rating": "low",
                "exam_name": st.session_state.exam_name,
            })
            get_new_question()
            set_rerun_flag()

    # 사이드바 상태 표시
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"👤 사용자: **{st.session_state.user_name}**")
    st.sidebar.markdown(f"✅ 정답 수: {st.session_state.score}")
    st.sidebar.markdown(f"❌ 오답 수: {len(st.session_state.wrong_list)}")
    st.sidebar.markdown(f"📊 총 풀어 수: {st.session_state.total}")
    remaining_count = (
        st.session_state.filtered_df.shape[0] if st.session_state.filtered_df is not None else 0
    )
    st.sidebar.markdown(f"📘 남은 문제: {remaining_count}")

    if st.sidebar.button("📂 오답 엑셀로 저장"):
        save_wrong_answers_to_excel()
    if st.sidebar.button("📈 주간 랭킹 보기"):
        display_weekly_ranking()
    if st.sidebar.button("❔ 오답 목록 보기"):
        show_wrong_list_table()

    st.markdown("### 📋 사용 가이드")
    st.markdown("""
    1. **사이드바**에서 Google Sheets URL을 입력하거나 미리 정의된 문제집을 선택하세요
    2. 워크시트 이름을 입력하세요 (비워두면 첫 번째 시트 사용)
    3. **\"문제집 로드\"** 버튼을 클릭하세요
    4. 문제집이 로드되면 퀴즈를 시작할 수 있습니다
    #### 📝 스프레드시트 형식 요구사항:
    - 필수 컬럼: `문제`, `정답`
    - 선택 컬럼: `단원명`, `문제번호`, `해설`
    - 정답 형식: "O" 또는 "X"
    """)

def run_app() -> None:
    init_session_state()
    rerun_if_needed()

    if not st.session_state.logged_in:
        login_page()
        return
    main_page()

if __name__ == "__main__":
    run_app()
