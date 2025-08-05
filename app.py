import os
import json
import re
from datetime import datetime
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
import gspread

USER_DATA_DIR = "user_data"
os.makedirs(USER_DATA_DIR, exist_ok=True)

def init_session_state():
    defaults = {
        "logged_in": False,
        "user_name": "",
        "is_admin": False,
        "df": None,
        "filtered_df": None,
        "question_index": 0,
        "score": 0,
        "total_answered": 0,
        "wrong_list": [],
        "exam_name": "",
        "current_answer": None,
        "show_result": False
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def connect_to_gspread():
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_dict = st.secrets["GCP_CREDENTIALS"]
        if isinstance(creds_dict, str):
            creds_dict = json.loads(creds_dict)
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(credentials)
    except Exception as e:
        st.error(f"Google Sheets 연결 실패: {e}")
        st.stop()

def load_google_sheet(sheet_id, worksheet_name=None):
    try:
        client = connect_to_gspread()
        if "docs.google.com" in sheet_id:
            m = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sheet_id)
            if m:
                sheet_id = m.group(1)
            else:
                st.error("올바른 Google Sheets URL이 아닙니다.")
                return pd.DataFrame()
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(worksheet_name) if worksheet_name else spreadsheet.sheet1
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return pd.DataFrame()

def get_current_question():
    df = st.session_state.filtered_df
    idx = st.session_state.question_index
    if df is None or df.empty or idx >= len(df) or idx < 0:
        return None
    return df.iloc[idx]

def save_wrong_answer(question, user_answer):
    wrong_item = {
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "문제번호": question.get("문제번호", ""),
        "단원명": question.get("단원명", ""),
        "문제": question.get("문제", ""),
        "정답": question.get("정답", ""),
        "선택": user_answer,
        "해설": question.get("해설", "")
    }
    st.session_state.wrong_list.append(wrong_item)

def login_page():
    st.title("🔐 로그인")
    with st.form("login_form"):
        name = st.text_input("이름", placeholder="이름을 입력하세요")
        group = st.text_input("소속", placeholder="소속을 입력하세요")
        password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
        submitted = st.form_submit_button("로그인")
        if submitted:
            if not name.strip():
                st.error("이름을 입력해주세요.")
                return
            if password == "admin" or group.lower() in ("admin", "관리자"):
                st.session_state.is_admin = True
                st.session_state.logged_in = True
            elif password == "1234":
                st.session_state.is_admin = False
                st.session_state.logged_in = True
            else:
                st.error("비밀번호가 틀렸습니다.")
                return
            st.session_state.user_name = f"{name} ({group})" if group else name
            st.experimental_rerun()

def quiz_page():
    st.title("📘 공인중개사 OX 퀴즈")

    with st.sidebar:
        st.header("📂 문제집 선택")
        predefined_sheets = {
            "1차 민법": "1Z9Oz04vuV7f5hbzrZ3iyn71RuB6bg0FEAL9_z10hyvs",
            "1차 학개론": "1LGlF9dUsuRsl3DVwIkHdm3XZzOCHojoYXbC2J_8RXuo",
            "2차 공법": "1L1N6lasmt8rvVDbD3NqTJlvzIz1cRBSCqGI3Bvw6a4Y",
            "2차 공시법": "1DP-AuJ5AaMoMMDiXwMYTy4eVIpAOKnh2PXVVtgS2O_Y",
            "2차 세법": "1prNQuzxdytOPzxpGKZw-aa76ud7RepkemIDlWpWCpMo",
            "2차 중개사법": "1Lkz9_f7040gjryUxTRcbU-4NTNucBXijK9RMlL6y_QY"
        }
        selected_sheet = st.selectbox("문제집 선택", ["선택하세요"] + list(predefined_sheets.keys()))

        if selected_sheet != "선택하세요":
            if st.button("📥 문제집 로드"):
                with st.spinner("문제집 로드 중..."):
                    df = load_google_sheet(predefined_sheets[selected_sheet])
                    if df.empty:
                        st.error("문제집 데이터가 없습니다.")
                    else:
                        st.session_state.df = df
                        st.session_state.filtered_df = df.reset_index(drop=True)
                        st.session_state.exam_name = selected_sheet
                        st.session_state.question_index = 0
                        st.session_state.score = 0
                        st.session_state.total_answered = 0
                        st.session_state.wrong_list = []
                        st.session_state.show_result = False
                        st.session_state.current_answer = None
                        st.success(f"✅ {selected_sheet} 문제집 로드 완료!")
                        st.experimental_rerun()

        if st.session_state.filtered_df is not None:
            st.markdown("---")
            st.write(f"👤 사용자: {st.session_state.user_name}")
            st.write(f"✅ 정답 수: {st.session_state.score}")
            st.write(f"❌ 오답 수: {len(st.session_state.wrong_list)}")
            st.write(f"📊 문제 {st.session_state.question_index + 1} / {len(st.session_state.filtered_df)}")

        if st.button("🚪 로그아웃"):
            for key in st.session_state.keys():
                del st.session_state[key]
            st.experimental_rerun()

    if st.session_state.filtered_df is None or st.session_state.filtered_df.empty:
        st.info("👈 사이드바에서 문제집을 선택하고 로드하세요.")
        return

    # 단원 필터링
    df = st.session_state.df
    chapters = ["전체"] + sorted(df["단원명"].dropna().unique())
    selected_chapter = st.selectbox("단원 선택", chapters, key="chapter_filter")
    if selected_chapter == "전체":
        filtered_df = df
    else:
        filtered_df = df[df["단원명"] == selected_chapter]
    if not filtered_df.equals(st.session_state.filtered_df):
        st.session_state.filtered_df = filtered_df.reset_index(drop=True)
        st.session_state.question_index = 0
        st.session_state.show_result = False
        st.session_state.current_answer = None
        st.experimental_rerun()

    question = get_current_question()
    if question is None:
        st.warning("문제가 존재하지 않습니다.")
        return

    st.markdown(f"### 단원: {question.get('단원명', '')}")
    st.markdown(f"#### 문제번호: {question.get('문제번호', '')}")
    st.markdown(f"**{question.get('문제', '문제 내용 없음')}**")

    col1, col2, col3 = st.columns(3)
    if not st.session_state.show_result:
        if col1.button("⭕ O"):
            st.session_state.current_answer = "O"
            st.session_state.show_result = True
            st.experimental_rerun()
        if col2.button("❌ X"):
            st.session_state.current_answer = "X"
            st.session_state.show_result = True
            st.experimental_rerun()
        if col3.button("❓ 모름"):
            st.session_state.current_answer = "모름"
            st.session_state.show_result = True
            st.experimental_rerun()
    else:
        user_answer = st.session_state.current_answer
        correct_answer = question.get("정답", "")
        if user_answer == correct_answer:
            st.success(f"🎉 정답입니다! 답: {correct_answer}")
            if st.session_state.total_answered == 0 or st.session_state.last_question_index != st.session_state.question_index:
                st.session_state.score += 1
        else:
            st.error(f"❌ 틀렸습니다. 정답: {correct_answer} | 선택: {user_answer}")
            save_wrong_answer(question, user_answer)
        st.session_state.total_answered += 1
        st.session_state.last_question_index = st.session_state.question_index

        if question.get("해설"):
            with st.expander("📖 해설 보기"):
                st.write(question["해설"])

    st.markdown("---")
    col_prev, col_next = st.columns([1,1])
    if col_prev.button("⬅️ 이전 문제"):
        if st.session_state.question_index > 0:
            st.session_state.question_index -= 1
            st.session_state.show_result = False
            st.session_state.current_answer = None
            st.experimental_rerun()
    if col_next.button("다음 문제 ➡️"):
        if st.session_state.question_index < len(st.session_state.filtered_df) - 1:
            st.session_state.question_index += 1
            st.session_state.show_result = False
            st.session_state.current_answer = None
            st.experimental_rerun()
        else:
            st.balloons()
            st.success("🎉 모든 문제를 완료했습니다!")

def main():
    st.set_page_config(page_title="공인중개사 OX 퀴즈", page_icon="📘", layout="wide")

    init_session_state()

    if not st.session_state.logged_in:
        login_page()
    else:
        quiz_page()

if __name__ == "__main__":
    main()
