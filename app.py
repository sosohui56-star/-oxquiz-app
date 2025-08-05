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
        "filtered_df": None,  # 필터된 데이터 저장용
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
        "need_rerun": False,  # 재실행 플래그
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
    client = connect_to_gspread()
    try:
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
        df_week.groupby("user_name").size()
        .reset_index(name="풀이수")
        .sort_values(by="풀이수", ascending=False)
    )
    ranking_df["순위"] = range(1, len(ranking_df) + 1)
    ranking_df = ranking_df[["순위", "user_name", "풀이수"]]
    st.subheader("📈 이번 주 문제풀이 랭킹")
    st.table(ranking_df)
    if st.session_state.user_name in ranking_df["user_name"].values:
        row = ranking_df[ranking_df["user_name"] == st.session_state.user_name].iloc[0]
        st.success(f"{st.session_state.user_name}님의 이번 주 풀이 수: {int(row['풀이수'])}개, 순위: {int(row['순위'])}위")

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

def show_wrong_list_table():
    if not st.session_state.wrong_list:
        st.warning("❗ 오답이 없습니다.")
        return
    wrong_df = pd.DataFrame(st.session_state.wrong_list)
    st.subheader("❗ 오답 목록")
    st.table(
        wrong_df[["날짜", "문제번호", "단원명", "문제", "선택", "정답", "해설"]]
    )

def show_accuracy():
    if st.session_state.total > 0:
        accuracy = (st.session_state.score / st.session_state.total) * 100
        st.sidebar.markdown(f"🎯 문제집별 정답률: {accuracy:.2f}%")
    else:
        st.sidebar.markdown("🎯 문제집별 정답률: 정보 없음")

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
        st.session_state.skip_ids = set()
        st.session_state.low_ids = set()
        st.session_state.user_progress_file = None
        st.session_state.df = None
        st.session_state.filtered_df = None
        st.session_state.question = None
        st.session_state.answered = False
        st.session_state.prev_selected_file = None
        st.session_state.prev_selected_chapter = None
        st.session_state.need_rerun = True

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
        st.error(f"Google 스프레드시트에서 데이터를 읽는 중 오류가 발생했습니다: {e}")
        return pd.DataFrame()

def get_new_question() -> None:
    df = st.session_state.filtered_df
    if df is not None and not df.empty:
        st.session_state.question = df.sample(1).iloc[0]
    else:
        st.session_state.question = None

def main_page() -> None:
    rerun_if_needed()

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
        st.session_state.filtered_df = pd.DataFrame()
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
                st.success(f"✅ '{sheet_name}' 문제집이 성공적으로 로드되었습니다!")
                st.write(f"총 {len(df_source)}개의 문제가 있습니다.")
                st.write("문제집 구조:", df_source.columns.tolist())
                with st.expander("첫 번째 문제 예시 보기"):
                    if len(df_source) > 0:
                        st.write(df_source.head(1))
                    else:
                        st.error("❌ 문제집을 불러올 수 없습니다. URL과 워크시트 이름을 확인하세요.")
                st.session_state.filtered_df = df_source.copy()
                get_new_question()
                return
            else:
                st.error("❌ 문제집 데이터가 비어있습니다.")
                st.session_state.filtered_df = pd.DataFrame()
                return

    if st.session_state.filtered_df is None or st.session_state.filtered_df.empty:
        st.info("📝 위에서 Google Sheets 문제집을 먼저 로드해주세요.")
        return

    # 단원 필터링 UI 및 적용
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

    st.subheader("📚 퀴즈 시작")
    required_cols = {"문제", "정답"}
    if not required_cols.issubset(st.session_state.filtered_df.columns):
        st.error(f"필수 컬럼이 없습니다: {required_cols - set(st.session_state.filtered_df.columns)}")
        st.info("스프레드시트에 '문제'와 '정답' 컬럼이 있는지 확인하세요.")
        return

    if st.session_state.question is None:
        get_new_question()

    question = st.session_state.question
    if question is None:
        st.warning("문제가 없습니다.")
        return

    if "단원명" in question:
        st.write(f"**단원:** {question.get('단원명', '')}")
    qnum_display = question.get("문제번호", "")
    try:
        qnum_display = int(qnum_display)
    except Exception:
        pass
    st.write(f"**문제번호:** {qnum_display}")
    st.write(f"**문제:** {question['문제']}")

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
        if st.session_state.user_progress_file:
            save_user_progress(st.session_state.user_progress_file, data_to_save)
            # log_to_sheet(data_to_save)
        st.session_state.last_correct = correct
        st.session_state.last_qnum = str(qnum_display)

    if st.session_state.answered and st.session_state.last_question is not None:
        last_q = st.session_state.last_question
        if "해설" in last_q and pd.notna(last_q["해설"]):
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
    else:
        st.info("📝 위에서 Google Sheets 문제집을 먼저 로드해주세요.")

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

    if not st.session_state.logged_in:
        login_page()
        return
    main_page()

if __name__ == "__main__":
    run_app()
