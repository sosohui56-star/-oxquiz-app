import os
import re
import json
import csv
from datetime import datetime

import pandas as pd
import streamlit as st

from google.oauth2.service_account import Credentials
import gspread
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound

# 사용자 데이터 저장 폴더
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
    # 로컬 CSV 파일에 사용자 활동 로그 기록 (필요 시)
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
        st.warning(f"기록 파일에 저장하는 중 오류 발생: {e}")


def connect_to_gspread() -> gspread.Client:
    # Streamlit secrets 에 GCP 서비스 계정 JSON을 "GCP_CREDENTIALS" 키로 저장 필요
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    try:
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


def connect_to_sheet() -> gspread.Worksheet:
    try:
        client = connect_to_gspread()
        sheet = client.open("oxquiz_progress_log").worksheet("시트1")
        return sheet
    except Exception as e:
        st.error(f"진행 로그 시트를 열 수 없습니다: {e}")
        st.stop()


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
        sheet = connect_to_sheet()
        sheet.append_row(row)
        st.session_state.sheet_log_status = "✅ 구글 시트에 기록 성공!"
        st.info("✅ 구글 시트에 기록 성공!")
    except Exception as e:
        st.session_state.sheet_log_status = f"📛 구글 시트 기록 실패: {e}"
        st.error(f"📛 구글 시트 기록 실패: {e}")


def load_user_progress(username: str, exam_name: str = None):
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
            st.warning(f"진행 파일을 읽는 중 오류 발생: {e}")
    return skip_ids, low_ids, file_path, df


def save_user_progress(file_path: str, data: dict) -> None:
    df_line = pd.DataFrame([data])
    write_header = not os.path.exists(file_path)
    try:
        df_line.to_csv(file_path, mode="a", header=write_header, index=False)
    except Exception as e:
        st.warning(f"사용자 진행 파일 저장 중 오류 발생: {e}")


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
        st.warning(f"문제 이해도 저장 중 오류 발생: {e}")


def load_data_from_google_sheet(spreadsheet_url_or_id: str, worksheet_name: str = None) -> pd.DataFrame:
    try:
        client = connect_to_gspread()
        if "docs.google.com" in spreadsheet_url_or_id:
            match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', spreadsheet_url_or_id)
            if not match:
                st.error("올바른 Google Sheets URL이 아닙니다.")
                return pd.DataFrame()
            spreadsheet_id = match.group(1)
        else:
            spreadsheet_id = spreadsheet_url_or_id
        spreadsheet = client.open_by_key(spreadsheet_id)
        if worksheet_name:
            worksheet = spreadsheet.worksheet(worksheet_name)
        else:
            worksheet = spreadsheet.sheet1
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
        st.error(f"Google 스프레드시트에서 데이터를 읽는 중 오류 발생: {e}")
        return pd.DataFrame()


def get_new_question(filtered_df=None) -> None:
    df = filtered_df if filtered_df is not None else st.session_state.df
    if df is not None and not df.empty:
        st.session_state.question = df.sample(1).iloc[0]
    else:
        st.session_state.question = None


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

        # 로그인 인증 예시
        if password == "admin" or group.lower() in ("관리자", "admin"):
            st.session_state.is_admin = True
            st.session_state.logged_in = True
        elif password == "1234":
            st.session_state.is_admin = False
            st.session_state.logged_in = True
        else:
            st.error("❌ 암호가 틀렸습니다.")
            return

        # 초기화
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

    sheets_url = st.sidebar.text_input(
        "Google Sheets URL을 입력하세요",
        placeholder="https://docs.google.com/spreadsheets/d/your-sheet-id/edit#gid=0",
        help="Google Sheets의 공유 링크를 입력하세요"
    )

    selected_predefined = st.sidebar.selectbox(
        "또는 미리 정의된 문제집에서 선택",
        ["선택안함"] + list(predefined_sheets.keys())
    )

    if sheets_url:
        spreadsheet_source = sheets_url
        sheet_name = "사용자 입력 시트"
    elif selected_predefined != "선택안함":
        spreadsheet_source = predefined_sheets[selected_predefined]
        sheet_name = selected_predefined
    else:
        st.sidebar.warning("Google Sheets URL을 입력하거나 미리 정의된 시트를 선택하세요.")
        return

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
                st.session_state.user_progress_file = os.path.join(
                    USER_DATA_DIR,
                    f"{get_safe_filename(st.session_state.user_name)}_{get_safe_filename(sheet_name)}_progress.csv"
                )
                # 로드 시 모든 상태 초기화
                st.session_state.question = None
                st.session_state.answered = False
                st.session_state.score = 0
                st.session_state.total = 0
                st.session_state.wrong_list = []
                st.success(f"✅ '{sheet_name}' 문제집을 성공적으로 로드했습니다!")
                st.rerun() # 상태 초기화 후 깔끔하게 새로 시작

    if st.session_state.df is not None and not st.session_state.df.empty:
        st.subheader("📚 퀴즈 시작")

        required_cols = {"문제", "정답"}
        if not required_cols.issubset(st.session_state.df.columns):
            st.error(f"필수 컬럼이 누락되었습니다: {required_cols - set(st.session_state.df.columns)}")
            st.info("Google Sheets에 '문제'와 '정답' 컬럼이 있어야 합니다.")
            return

        if "단원명" in st.session_state.df.columns:
            chapters = ["전체 보기"] + sorted(st.session_state.df["단원명"].dropna().unique().tolist())
            selected_chapter = st.selectbox("단원 선택", chapters)
            if selected_chapter != "전체 보기":
                filtered_df = st.session_state.df[st.session_state.df["단원명"] == selected_chapter]
            else:
                filtered_df = st.session_state.df
        else:
            filtered_df = st.session_state.df

        if filtered_df.empty:
            st.warning("선택한 단원에 해당하는 문제가 없습니다.")
            return

        # <--- 로직 수정의 핵심 부분 시작 --->
        
        # 1. 아직 풀 문제가 없으면 새로 가져오기 (최초 실행 시)
        if st.session_state.question is None:
            get_new_question(filtered_df)

        # 2. 현재 문제 표시
        question = st.session_state.question
        if question is None:
             st.warning("더 이상 풀 문제가 없습니다. 다른 단원을 선택해주세요.")
             return

        st.write("---")
        if "단원명" in question:
            st.write(f"**단원:** {question.get('단원명', '')}")
        qnum_display = question.get("문제번호", "N/A")
        st.write(f"**문제번호:** {qnum_display}")
        st.write(f"**문제:** {question['문제']}")
        
        # 3. 해설/평가 표시 (답변이 제출된 상태일 때)
        if st.session_state.answered:
            last_q = st.session_state.last_question
            
            # 정답/오답 결과 표시
            if st.session_state.last_correct:
                st.success("✅ 정답입니다!")
            else:
                st.error(f"❌ 오답입니다. 정답은 {last_q['정답']}")
            
            # 해설 표시
            if "해설" in last_q and pd.notna(last_q["해설"]):
                st.info(f"📘 해설: {last_q['해설']}")

            # 이해도 체크 버튼
            rating_col1, rating_col2, rating_col3 = st.columns(3)
            rating_buttons = {
                "skip": rating_col1.button("❌ 다시 보지 않기"),
                "mid": rating_col2.button("📘 이해 50~90%"),
                "low": rating_col3.button("🔄 이해 50% 미만"),
            }

            for rating, is_clicked in rating_buttons.items():
                if is_clicked:
                    if st.session_state.user_progress_file:
                        update_question_rating(st.session_state.user_progress_file, st.session_state.last_qnum, rating)
                    log_to_sheet({
                        "timestamp": datetime.now().isoformat(),
                        "user_name": st.session_state.user_name,
                        "question_id": st.session_state.last_qnum,
                        "correct": st.session_state.last_correct,
                        "rating": rating,
                        "exam_name": st.session_state.exam_name,
                    })
                    if rating == "skip":
                         st.session_state.df = st.session_state.df[st.session_state.df["문제번호"].astype(str) != st.session_state.last_qnum]
                    
                    st.session_state.answered = False
                    get_new_question(filtered_df) # 다음 문제 가져오기
                    st.rerun()

        # 4. 문제 풀이 버튼 표시 (아직 답변하지 않았을 때)
        else:
            col1, col2, col3 = st.columns(3)
            answer_buttons = {
                "O": col1.button("⭕ O", use_container_width=True),
                "X": col2.button("❌ X", use_container_width=True),
                "모름": col3.button("⁉️ 모름", use_container_width=True),
            }

            for user_answer, is_clicked in answer_buttons.items():
                if is_clicked:
                    st.session_state.total += 1
                    st.session_state.answered = True
                    st.session_state.last_question = question.copy() # 현재 문제를 last_question에 저장
                    record_user_activity()

                    correct = (user_answer == question["정답"])
                    st.session_state.last_correct = correct # 정답 여부 저장

                    if correct:
                        st.session_state.score += 1
                    else:
                        st.session_state.wrong_list.append({
                            "이름": st.session_state.user_name,
                            "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"), "문제번호": qnum_display,
                            "단원명": question.get("단원명", ""), "문제": question["문제"],
                            "정답": question["정답"], "선택": user_answer,
                            "해설": question.get("해설", "") if pd.notna(question.get("해설", "")) else "",
                        })
                    
                    st.session_state.last_qnum = str(qnum_display)
                    st.rerun() # 해설을 보여주기 위해 페이지 새로고침

        # <--- 로직 수정의 핵심 부분 끝 --->

        # 우측 사이드바 - 사용자 정보 & 기능
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"👤 사용자: **{st.session_state.user_name}**")
        st.sidebar.markdown(f"✅ 정답 수: {st.session_state.score}")
        st.sidebar.markdown(f"❌ 오답 수: {len(st.session_state.wrong_list)}")
        st.sidebar.markdown(f"📊 총 풀어 수: {st.session_state.total}")

        remaining_count = filtered_df.shape[0] if filtered_df is not None else 0
        st.sidebar.markdown(f"📘 남은 문제: {remaining_count}")

        if st.session_state.total > 0:
            accuracy = (st.session_state.score / st.session_state.total) * 100
            st.sidebar.markdown(f"🎯 정답률: {accuracy:.1f}%")
        else:
            st.sidebar.markdown("🎯 정답률: 0%")

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
