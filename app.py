
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

def connect_to_gspread() -> gspread.Client:
    """gspread 클라이언트 객체를 반환합니다."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    try:
        # Streamlit secrets에서 GCP 인증정보 가져오기
        creds_data = st.secrets.get("GCP_CREDENTIALS", {})
        if isinstance(creds_data, str):
            creds_dict = json.loads(creds_data)
        else:
            creds_dict = dict(creds_data)

        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.error(f"Google Sheets 연결 오류: {e}")
        st.stop()

@st.cache_data(ttl=3600)
def load_data_from_google_sheet(spreadsheet_url_or_id: str, worksheet_name: str = None) -> pd.DataFrame:
    """Google 스프레드시트에서 데이터를 로드합니다."""
    try:
        client = connect_to_gspread()

        # URL에서 스프레드시트 ID 추출 또는 직접 ID 사용
        if "docs.google.com" in spreadsheet_url_or_id:
            # URL에서 ID 추출
            import re
            match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', spreadsheet_url_or_id)
            if match:
                spreadsheet_id = match.group(1)
            else:
                st.error("올바른 Google Sheets URL이 아닙니다.")
                return pd.DataFrame()
        else:
            spreadsheet_id = spreadsheet_url_or_id

        # 스프레드시트 열기
        spreadsheet = client.open_by_key(spreadsheet_id)

        # 워크시트 선택
        if worksheet_name:
            worksheet = spreadsheet.worksheet(worksheet_name)
        else:
            worksheet = spreadsheet.sheet1

        # 데이터 가져오기
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)

        return df

    except SpreadsheetNotFound:
        st.error(f"스프레드시트를 찾을 수 없습니다: {spreadsheet_url_or_id}")
        return pd.DataFrame()
    except WorksheetNotFound:
        st.error(f"워크시트를 찾을 수 없습니다: {worksheet_name}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Google 스프레드시트에서 데이터를 읽는 중 오류가 발생했습니다: {e}")
        return pd.DataFrame()

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

        # 로그인 시 기존 진행 상황 초기화
        st.session_state.skip_ids = set()
        st.session_state.low_ids = set()
        st.session_state.user_progress_file = None
        st.session_state.df = None
        st.session_state.question = None
        st.session_state.answered = False
        st.session_state.prev_selected_file = None
        st.session_state.prev_selected_chapter = None

        st.rerun()

def main_page() -> None:
    st.title("📘 공인중개사 OX 퀴즈")
    st.sidebar.header("📂 문제집 선택")

    # Google Sheets URL 입력 방식
    st.sidebar.subheader("Google Sheets 연결")

    # 옵션 1: URL 직접 입력
    sheets_url = st.sidebar.text_input(
        "Google Sheets URL을 입력하세요",
        placeholder="https://docs.google.com/spreadsheets/d/your-sheet-id/edit#gid=0",
        help="Google Sheets의 공유 링크를 입력하세요"
    )

    # 옵션 2: 미리 정의된 목록에서 선택 (필요시 사용)
    predefined_sheets = {
        "1차 민법": "your-actual-sheet-id-1",
        "2차 중개사법": "your-actual-sheet-id-2", 
        "2차 세법": "your-actual-sheet-id-3"
    }

    selected_predefined = st.sidebar.selectbox(
        "또는 미리 정의된 문제집에서 선택",
        ["선택안함"] + list(predefined_sheets.keys())
    )

    # 사용할 스프레드시트 결정
    if sheets_url:
        spreadsheet_source = sheets_url
        sheet_name = "사용자 입력 시트"
    elif selected_predefined != "선택안함":
        spreadsheet_source = predefined_sheets[selected_predefined]
        sheet_name = selected_predefined
    else:
        st.sidebar.warning("Google Sheets URL을 입력하거나 미리 정의된 시트를 선택하세요.")
        return

    # 워크시트 이름 입력
    worksheet_name = st.sidebar.text_input(
        "워크시트 이름 (비워두면 첫 번째 시트 사용)",
        placeholder="Sheet1"
    )

    if st.sidebar.button("문제집 로드"):
        with st.spinner("문제집을 불러오는 중..."):
            df_source = load_data_from_google_sheet(spreadsheet_source, worksheet_name)

            if not df_source.empty:
                st.session_state.df = df_source
                st.session_state.exam_name = sheet_name
                st.success(f"✅ '{sheet_name}' 문제집이 성공적으로 로드되었습니다!")
                st.write(f"총 {len(df_source)}개의 문제가 있습니다.")

                # 컬럼 정보 표시
                st.write("문제집 구조:", df_source.columns.tolist())

                # 샘플 데이터 표시 
                if len(df_source) > 0:
                    st.write("첫 번째 문제 예시:")
                    st.write(df_source.head(1))
            else:
                st.error("❌ 문제집을 불러올 수 없습니다. URL과 워크시트 이름을 확인하세요.")

    # 문제집이 로드된 경우에만 퀴즈 진행
    if st.session_state.df is not None and not st.session_state.df.empty:
        st.subheader("📚 퀴즈 시작")

        # 필수 컬럼 확인
        required_cols = {"문제", "정답"}
        if not required_cols.issubset(st.session_state.df.columns):
            st.error(f"필수 컬럼이 없습니다: {required_cols - set(st.session_state.df.columns)}")
            return

        # 단원 선택 (있는 경우)
        if "단원명" in st.session_state.df.columns:
            chapters = ["전체 보기"] + sorted(st.session_state.df["단원명"].dropna().unique().tolist())
            selected_chapter = st.selectbox("단원 선택", chapters)

            if selected_chapter != "전체 보기":
                filtered_df = st.session_state.df[st.session_state.df["단원명"] == selected_chapter]
            else:
                filtered_df = st.session_state.df
        else:
            filtered_df = st.session_state.df

        if len(filtered_df) == 0:
            st.warning("선택한 조건에 맞는 문제가 없습니다.")
            return

        # 랜덤 문제 선택
        if st.session_state.question is None:
            st.session_state.question = filtered_df.sample(1).iloc[0]

        question = st.session_state.question

        # 문제 표시
        st.write("---")
        if "단원명" in question:
            st.write(f"**단원:** {question.get('단원명', '')}")

        if "문제번호" in question:
            try:
                qnum_display = int(question["문제번호"])
            except:
                qnum_display = question["문제번호"]
            st.write(f"**문제번호:** {qnum_display}")

        st.write(f"**문제:** {question['문제']}")

        # 답안 선택
        col1, col2, col3 = st.columns(3)
        user_answer = None

        if col1.button("⭕ O", use_container_width=True):
            user_answer = "O"
        elif col2.button("❌ X", use_container_width=True):
            user_answer = "X"
        elif col3.button("⁉️ 모름", use_container_width=True):
            user_answer = "모름"

        # 답안 처리
        if user_answer:
            correct = (user_answer == question["정답"])

            if correct:
                st.success("✅ 정답입니다!")
            else:
                st.error(f"❌ 오답입니다. 정답은 '{question['정답']}'입니다.")

            # 해설 표시 (있는 경우)
            if "해설" in question and pd.notna(question["해설"]) and question["해설"].strip():
                st.info(f"💡 **해설:** {question['해설']}")

            # 다음 문제 버튼
            if st.button("다음 문제", use_container_width=True):
                st.session_state.question = filtered_df.sample(1).iloc[0]
                st.rerun()

    else:
        st.info("📝 위에서 Google Sheets 문제집을 먼저 로드해주세요.")

def run_app() -> None:
    init_session_state()

    if not st.session_state.logged_in:
        login_page()
        return

    main_page()

if __name__ == "__main__":
    run_app()
