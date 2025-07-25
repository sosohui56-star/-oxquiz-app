import os
from datetime import datetime

import pandas as pd
import streamlit as st


"""공인중개사 OX 퀴즈 애플리케이션

이 애플리케이션은 CSV 문제집을 읽어 무작위로 OX 퀴즈를 출제하고,
사용자의 답안을 채점하여 오답 목록을 저장하는 도구입니다.

주요 개선사항:
  * 단원 필터링 결과를 항상 `st.session_state.df`에 저장하여
    데이터프레임이 세션 간 일관되게 유지되도록 하였습니다.
  * 새로운 문제를 고를 때는 `st.session_state.question`이
    비어 있을 때만 선택하며, 다음 문제 버튼을 클릭할 때 직접
    새 문제를 할당합니다. 이렇게 하면 이전 문제와 해설이
    엇갈리는 현상을 방지할 수 있습니다.
  * 사용자가 다른 파일이나 단원을 선택하면 현재 문제를 초기화하여
    혼동을 막습니다.
"""


def init_session_state() -> None:
    """세션 상태 초기화.

    Streamlit은 앱이 매번 다시 실행되기 때문에 사용자의 진행 상황을
    세션 상태에 저장해야 합니다. 이 함수는 최초 실행 시 필요한
    기본값을 설정합니다.
    """

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
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def login_page() -> None:
    """로그인 페이지를 표시합니다.

    암호가 맞으면 `logged_in` 상태를 True로 설정하고 재실행합니다.
    """

    st.title("🔐 사용자 로그인")
    name = st.text_input("이름을 입력하세요")
    group = st.text_input("소속을 입력하세요")
    password = st.text_input("암호를 입력하세요", type="password")

    if st.button("로그인"):
        if password == "1234":
            st.session_state.logged_in = True
            # 소속을 입력하지 않은 경우 괄호를 표시하지 않음
            st.session_state.user_name = (
                f"{name} ({group})" if group else name
            )
            st.success(f"🎉 환영합니다, {st.session_state.user_name}님!")
            # 상태가 변경되었으므로 앱을 재실행하여 메인 화면으로 이동
            st.rerun()
        else:
            st.error("❌ 암호가 틀렸습니다.")


def load_and_filter_data(selected_file: str, selected_chapter: str) -> None:
    """CSV 파일을 읽고 단원별로 필터링하여 세션 상태에 저장합니다.

    Parameters
    ----------
    selected_file: str
        사용자가 선택한 CSV 파일 이름.
    selected_chapter: str
        사용자가 선택한 단원명(또는 "전체 보기").
    """

    # CSV 파일 로드
    df_loaded = pd.read_csv(selected_file)
    # 문제와 정답이 비어있는 행 제거
    df_loaded = df_loaded.dropna(subset=["문제", "정답"])

    # 단원 필터링
    if selected_chapter != "전체 보기":
        df_filtered = df_loaded[df_loaded["단원명"] == selected_chapter]
    else:
        df_filtered = df_loaded

    st.session_state.df = df_filtered

    # 단원이나 파일이 변경된 경우 현재 질문을 초기화
    st.session_state.question = None
    st.session_state.answered = False
    st.session_state.last_question = None


def get_new_question() -> None:
    """세션 상태의 데이터프레임에서 무작위로 문제를 선택합니다.

    `st.session_state.question`이 None일 때 호출하여 새 문제를 채웁니다.
    데이터프레임이 비어있는 경우 question은 None으로 유지됩니다.
    """

    df = st.session_state.df
    if df is not None and not df.empty:
        st.session_state.question = df.sample(1).iloc[0]
    else:
        st.session_state.question = None


def main_page() -> None:
    """메인 퀴즈 페이지를 구성합니다."""

    st.title("📘 공인중개사 OX 퀴즈")
    st.sidebar.header("📂 문제집 선택")

    # 사용 가능한 CSV 파일 나열
    csv_files = [f for f in os.listdir() if f.endswith(".csv")]
    selected_file = st.sidebar.selectbox("사용할 파일을 선택하세요", csv_files)

    if not selected_file:
        st.warning("⚠️ CSV 문제 파일을 업로드하세요.")
        return

    # 파일을 처음 선택하거나 변경했는지 확인
    if st.session_state.prev_selected_file != selected_file:
        st.session_state.prev_selected_file = selected_file
        # 초기화는 단원 선택 로직에서 처리

    # 파일을 미리 읽어 단원 목록을 가져옴
    df_loaded = pd.read_csv(selected_file)
    df_loaded = df_loaded.dropna(subset=["문제", "정답"])
    chapters = sorted(df_loaded["단원명"].dropna().unique())

    # 단원 선택
    selected_chapter = st.sidebar.selectbox(
        "특정 단원만 푸시겠습니까?", ["전체 보기"] + chapters
    )

    # 단원이 변경되면 데이터프레임을 다시 로드/필터링
    if (st.session_state.prev_selected_chapter != selected_chapter or
        st.session_state.prev_selected_file != selected_file or
        st.session_state.df is None):
        st.session_state.prev_selected_chapter = selected_chapter
        load_and_filter_data(selected_file, selected_chapter)

    # question이 비어 있으면 새 문제 선택
    if st.session_state.question is None:
        get_new_question()

    # 문제를 불러왔는지 확인
    if st.session_state.question is None:
        st.info("선택한 단원에 문제 데이터가 없습니다.")
        return

    question = st.session_state.question

    # 문제 출력
    st.markdown(
        f"📚 단원명: {question['단원명']} | 문제번호: {int(question['문제번호'])}"
    )
    st.markdown(f"❓ {question['문제']}")

    # 답변 버튼
    user_answer = None
    col1, col2, col3 = st.columns(3)
    if col1.button("⭕ O"):
        user_answer = "O"
    elif col2.button("❌ X"):
        user_answer = "X"
    elif col3.button("⁉️ 모름"):
        user_answer = "모름"

    # 답변 처리
    if user_answer:
        st.session_state.total += 1
        st.session_state.answered = True
        st.session_state.last_question = question.copy()

        if user_answer == question["정답"]:
            st.session_state.score += 1
            st.success("✅ 정답입니다!")
        else:
            st.session_state.wrong_list.append({
                "이름": st.session_state.user_name,
                "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "문제번호": int(question["문제번호"]),
                "단원명": question["단원명"],
                "문제": question["문제"],
                "정답": question["정답"],
                "선택": user_answer,
                "해설": question["해설"]
                if "해설" in question and pd.notna(question["해설"])
                else "",
            })
            st.error(f"❌ 오답입니다. 정답은 {question['정답']}")

    # 답변 후 해설과 다음 문제 버튼 표시
    if st.session_state.answered and st.session_state.last_question is not None:
        last_q = st.session_state.last_question
        if "해설" in last_q and pd.notna(last_q["해설"]):
            st.info(f"📘 해설: {last_q['해설']}")

        # 다음 문제 버튼
        if st.button("👉 다음 문제"):
            # 새 문제를 선택하고 답변 상태를 초기화
            get_new_question()
            st.session_state.answered = False
            st.rerun()

        # 사이드바 통계 및 오답 저장 버튼
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"👤 사용자: **{st.session_state.user_name}**")
        st.sidebar.markdown(f"✅ 정답 수: {st.session_state.score}")
        st.sidebar.markdown(f"❌ 오답 수: {len(st.session_state.wrong_list)}")
        st.sidebar.markdown(f"📊 총 풀이 수: {st.session_state.total}")
        st.sidebar.markdown("Made with ❤️ for 공인중개사 수험생")

        if st.sidebar.button("🗂️ 오답 엑셀로 저장"):
            if st.session_state.wrong_list:
                wrong_df = pd.DataFrame(st.session_state.wrong_list)
                filename = (
                    f"{st.session_state.user_name}_오답_"
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                )
                wrong_df.to_excel(filename, index=False)
                st.sidebar.success(f"📁 {filename} 저장 완료!")
            else:
                st.sidebar.warning("❗ 오답이 없습니다.")


def run_app() -> None:
    """앱 실행 함수."""

    init_session_state()

    # 로그인 여부 확인
    if not st.session_state.logged_in:
        login_page()
        return

    # 메인 페이지 표시
    main_page()


if __name__ == "__main__":
    run_app()
