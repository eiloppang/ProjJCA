"""
누락된 KRI 데이터 채우기
- 한국현대문학 CSV에서 kri_num, gender, birth가 누락된 행 찾기
- KCI에서 article-id로 저자 정보 및 CRT ID 추출
- KRI에서 연구자 정보 (생년, 성별) 수집
- 영문학 데이터도 처리
"""

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, 
    TimeoutException,
    UnexpectedAlertPresentException
)
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
from random import uniform
from tqdm import tqdm
import re
import os

# ===== 로그인 정보 설정 =====
KCI_LOGIN_INFO = {
    "loginBean.membId": "eiloppang",
    "loginBean.secrNo": "0102414k^~^",
}

KRI_LOGIN_INFO = {
    "uid": "eiloppang",
    "upw": "0102414k^~^",
}

# Chrome 설정
def setup_driver():
    """Chrome 드라이버 설정"""
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('window-size=1920x1080')
    chrome_options.add_argument('--start-maximized')
    chrome_options.add_argument("disable-gpu")
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    return driver


def get_kri_id_from_author_profile(driver, cret_id, arti_id):
    """
    KCI 저자 프로필 페이지에서 KRI 연구자번호 추출
    저자정보 부분의 hidden input에서 value 값 추출
    <input type="hidden" id="citationBean.kriCretId" name="citationBean.kriCretId" value="10032099">
    """
    profile_url = f'https://www.kci.go.kr/kciportal/po/citationindex/poCretDetail.kci?citationBean.cretId={cret_id}&citationBean.artiId={arti_id}'
    
    try:
        driver.get(profile_url)
        time.sleep(uniform(1.5, 2))
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 방법 1: hidden input에서 KRI ID 추출 (가장 정확한 방법)
        kri_input = soup.find('input', {'id': 'citationBean.kriCretId'})
        if kri_input and kri_input.get('value'):
            kri_id = kri_input.get('value')
            if kri_id and kri_id.strip() and kri_id != '':
                return kri_id.strip()
        
        # 방법 2: name 속성으로도 시도
        kri_input = soup.find('input', {'name': 'citationBean.kriCretId'})
        if kri_input and kri_input.get('value'):
            kri_id = kri_input.get('value')
            if kri_id and kri_id.strip() and kri_id != '':
                return kri_id.strip()
        
        # 방법 3: type="hidden"인 모든 input 중에서 찾기
        hidden_inputs = soup.find_all('input', {'type': 'hidden'})
        for input_elem in hidden_inputs:
            input_id = input_elem.get('id', '')
            input_name = input_elem.get('name', '')
            if 'kriCretId' in input_id or 'kriCretId' in input_name:
                kri_id = input_elem.get('value', '')
                if kri_id and kri_id.strip() and kri_id != '':
                    return kri_id.strip()
        
        return None
        
    except Exception as e:
        return None


def get_author_kri_info_from_kci(driver, article_id):
    """
    KCI 논문 상세페이지에서 1저자의 이름과 KRI 연구자번호 추출
    
    작동 순서:
    1. 논문 상세페이지 접속
    2. 1저자 이름 클릭 (저자 프로필로 이동)
    3. 저자 프로필 URL에서 cretId, artiId 추출
    4. 저자정보 hidden input에서 KRI ID 추출
    """
    url = f'https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId={article_id}'
    
    try:
        # Step 1: 논문 상세페이지 접속
        driver.get(url)
        time.sleep(uniform(1, 2))
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 논문 제목 추출
        title_elem = soup.find('div', class_='tit-area')
        title = title_elem.get_text(strip=True) if title_elem else "제목 없음"
        
        # Step 2: 1저자 정보 찾기
        # <a href="/kciportal/po/citationindex/poCretDetail.kci?citationBean.cretId=CRT001613578&citationBean.artiId=ART003157803">
        author_elements = soup.find_all('a', href=lambda x: x and 'poCretDetail.kci' in x and 'cretId=' in x)
        
        if not author_elements:
            return {
                'cret_id': None,
                'arti_id': article_id,
                'author_name': None,
                'kri_id': None,
                'title': title,
                'status': '저자 정보 없음'
            }
        
        # 첫 번째 저자 (1저자)
        first_author = author_elements[0]
        author_name = first_author.get_text(strip=True)
        
        # Step 3: href에서 cretId와 artiId 추출
        href = first_author.get('href')
        cret_id = None
        extracted_arti_id = None
        
        if 'citationBean.cretId=' in href:
            # cretId 추출
            cret_id_match = re.search(r'cretId=([^&\'\"]+)', href)
            if cret_id_match:
                cret_id = cret_id_match.group(1)
            
            # artiId 추출 (href에 포함된 경우)
            arti_id_match = re.search(r'artiId=([^&\'\"]+)', href)
            if arti_id_match:
                extracted_arti_id = arti_id_match.group(1)
        
        # artiId는 원본 사용 (href에 없을 수 있음)
        final_arti_id = extracted_arti_id if extracted_arti_id else article_id
        
        # Step 4: 저자 프로필 페이지에서 KRI ID 추출
        kri_id = None
        if cret_id:
            kri_id = get_kri_id_from_author_profile(driver, cret_id, final_arti_id)
        
        status = 'KRI ID 있음' if kri_id else 'KRI ID 없음'
        
        return {
            'cret_id': cret_id,
            'arti_id': final_arti_id,
            'author_name': author_name,
            'kri_id': kri_id,
            'title': title,
            'status': status
        }
        
    except Exception as e:
        return {
            'cret_id': None,
            'arti_id': article_id,
            'author_name': None,
            'kri_id': None,
            'title': None,
            'status': f'오류: {str(e)}'
        }


def login_kci(driver):
    """KCI 사이트 로그인 (기존 kci_kri_full_scraper.py에서 가져옴)"""
    try:
        print("\n" + "="*60)
        print("KCI 사이트 로그인 중...")
        print("="*60)
        
        # 메인 페이지 접속
        print("→ 메인 페이지 접속...")
        driver.get("https://www.kci.go.kr/kciportal/main.kci")
        time.sleep(2)
        print(f"  현재 URL: {driver.current_url}")
        
        # 로그인 페이지로 직접 이동 (팝업 대신)
        print("→ 로그인 페이지로 직접 이동...")
        driver.get("https://www.kci.go.kr/kciportal/po/member/popup/loginForm.kci")
        time.sleep(2)
        
        print(f"  로그인 페이지 URL: {driver.current_url}")
        
        # ID/PW 입력
        print("→ ID/PW 입력 중...")
        try:
            # ID 입력란이 클릭 가능할 때까지 대기 (name="uid")
            id_input = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "uid"))
            )
            print(f"  ID 입력란 발견")
            
            # JavaScript로 직접 값 설정 (clear() 대신)
            driver.execute_script("arguments[0].value = '';", id_input)
            time.sleep(0.5)
            id_input.send_keys(KCI_LOGIN_INFO["loginBean.membId"])
            print(f"  ID 입력 완료: {KCI_LOGIN_INFO['loginBean.membId']}")
            
            # PW 입력란도 클릭 가능할 때까지 대기 (name="upw")
            pw_input = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "upw"))
            )
            print(f"  PW 입력란 발견")
            
            # JavaScript로 직접 값 설정
            driver.execute_script("arguments[0].value = '';", pw_input)
            time.sleep(0.5)
            pw_input.send_keys(KCI_LOGIN_INFO["loginBean.secrNo"])
            print(f"  PW 입력 완료")
            
        except Exception as e:
            print(f"  ID/PW 입력 실패: {e}")
            # 페이지 소스 저장
            with open('debug_kci_login.html', 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            print(f"  → 로그인 페이지 저장: debug_kci_login.html")
            return False
        
        # 로그인 버튼 클릭 (Enter 키 사용)
        print("→ 로그인 실행 중...")
        pw_input.send_keys(Keys.ENTER)
        time.sleep(4)
        
        print(f"  로그인 후 URL: {driver.current_url}")
        
        # 로그인 성공 확인
        page_text = driver.page_source
        if "로그아웃" in page_text or "logout" in page_text.lower():
            print("KCI 로그인 완료")
            return True
        elif "로그인" not in page_text or driver.current_url == "https://www.kci.go.kr/kciportal/main.kci":
            print("KCI 로그인 완료 (메인 페이지 이동)")
            return True
        else:
            print("KCI 로그인 상태 불확실, 일단 진행")
            return True
        
    except Exception as e:
        print(f"KCI 로그인 중 예외 발생: {e}")
        import traceback
        traceback.print_exc()
        return False


def login_kri(driver):
    """KRI 사이트 로그인 (기존 kci_kri_full_scraper.py 그대로)"""
    try:
        print("\n" + "="*60)
        print("KRI 사이트 로그인 중...")
        print("="*60)
        
        # 메인 페이지 접속
        print("→ KRI 메인 페이지 접속...")
        driver.get('https://www.kri.go.kr/kri2')
        time.sleep(2)
        print(f"  현재 URL: {driver.current_url}")
        
        # 로그인 버튼 클릭
        print("→ 로그인 버튼 찾는 중...")
        try:
            login_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@class='site-btn btn-point ico-user' and contains(text(), '로그인')]"))
            )
            print("  로그인 버튼 발견 (방법 1), 클릭...")
            login_btn.click()
            time.sleep(3)
        except:
            try:
                login_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(@onclick, 'openCPSWindow')]"))
                )
                print("  로그인 버튼 발견 (방법 2), 클릭...")
                driver.execute_script("arguments[0].click();", login_btn)
                time.sleep(3)
            except Exception as e:
                print(f"  로그인 버튼 클릭 실패: {e}")
                with open('debug_kri_main.html', 'w', encoding='utf-8') as f:
                    f.write(driver.page_source)
                print(f"  → 페이지 저장: debug_kri_main.html")
                return False, None
        
        print(f"  로그인 버튼 클릭 후 URL: {driver.current_url}")
        print(f"  창 개수: {len(driver.window_handles)}")
        
        # 공지사항 팝업 처리
        main_window = driver.current_window_handle
        if len(driver.window_handles) > 1:
            print(f"  ⚠ 팝업 창 감지됨! 창 개수: {len(driver.window_handles)}")
            for handle in driver.window_handles:
                if handle != main_window:
                    print(f"  → 팝업 창으로 전환하여 닫기: {handle}")
                    driver.switch_to.window(handle)
                    time.sleep(0.5)
                    popup_url = driver.current_url
                    print(f"  팝업 URL: {popup_url}")
                    
                    # 공지사항 팝업인 경우 닫기
                    if "공지" in driver.page_source or "notice" in popup_url.lower():
                        print("  공지사항 팝업 닫는 중...")
                        driver.close()
                        time.sleep(0.5)
                    else:
                        # 다른 팝업은 그대로 둠
                        print("  알 수 없는 팝업, 그대로 유지")
            
            # 메인 창으로 돌아가기
            driver.switch_to.window(main_window)
            print(f"  → 메인 창으로 복귀")
            time.sleep(1)
        
        # ID/PW 입력 (JavaScript)
        print("→ ID/PW 입력 중...")
        input_result = driver.execute_script("""
            var uidInput = document.querySelector('#uid');
            var upwInput = document.querySelector('#upw');
            
            if(uidInput && upwInput) {
                uidInput.value = arguments[0];
                upwInput.value = arguments[1];
                return 'success';
            } else {
                return 'inputs not found';
            }
        """, KRI_LOGIN_INFO['uid'], KRI_LOGIN_INFO['upw'])
        
        print(f"  ID/PW 입력 결과: {input_result}")
        if input_result != 'success':
            with open('debug_kri_login_form.html', 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            print(f"  → 페이지 저장: debug_kri_login_form.html")
            return False, None
        
        time.sleep(1)
        
        # 로그인 실행
        print("→ 로그인 실행 중...")
        try:
            login_submit_btn = driver.find_element(By.CSS_SELECTOR, '.btn-site-login')
            print("  로그인 버튼 발견, 클릭...")
            login_submit_btn.click()
        except:
            print("  로그인 버튼 찾기 실패, JavaScript로 클릭...")
            driver.execute_script("""
                var loginBtn = document.querySelector('.btn-site-login');
                if(loginBtn) loginBtn.click();
            """)
        
        time.sleep(5)
        print(f"  로그인 후 URL: {driver.current_url}")
        print(f"  창 개수: {len(driver.window_handles)}")
        
        # 비밀번호 변경 팝업 닫기
        print("→ 비밀번호 변경 팝업 확인...")
        try:
            next_pwd_btn = driver.find_element(By.ID, 'next_pwd')
            print("  비밀번호 변경 팝업 발견, 다음에 하기 클릭...")
            next_pwd_btn.click()
            time.sleep(1)
        except NoSuchElementException:
            print("  비밀번호 변경 팝업 없음")
        except Exception as e:
            print(f"  비밀번호 팝업 처리 중 오류: {e}")
        
        # 검색 메뉴로 이동
        print("→ 검색 메뉴로 이동 중...")
        try:
            search_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@class='dep1-item ico-search']"))
            )
            print("  검색 메뉴 버튼 발견, 클릭...")
            search_btn.click()
            time.sleep(1)
        except Exception as e:
            print(f"  검색 메뉴 클릭 실패: {e}")
            with open('debug_kri_after_login.html', 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            print(f"  → 로그인 후 페이지 저장: debug_kri_after_login.html")
            return False, None
        
        # 성명 검색 클릭
        print("→ 성명 검색 메뉴 클릭 중...")
        try:
            name_search_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@class='MNU_1103']"))
            )
            print("  성명 검색 메뉴 발견, 클릭...")
            name_search_btn.click()
            time.sleep(2)
        except Exception as e:
            print(f"  성명 검색 메뉴 클릭 실패: {e}")
            return False, None
        
        print(f"  검색 페이지 URL: {driver.current_url}")
        
        # iframe으로 전환
        print("→ iframe 전환 중...")
        iframes = driver.find_elements(By.TAG_NAME, 'iframe')
        print(f"  발견된 iframe 개수: {len(iframes)}")
        if iframes:
            driver.switch_to.frame(iframes[0])
            print("  iframe 전환 완료")
        else:
            print("  ⚠ iframe 없음")
        
        print("KRI 로그인 완료 및 검색 페이지 준비됨")
        return True, driver
        
    except Exception as e:
        print(f"  KRI 로그인 실패: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def search_researcher_by_kri_id(driver, kri_id, author_name=None, retry_count=0):
    """
    KRI 사이트에서 연구자번호와 성명으로 검색하여 인구사회학 정보 추출
    (기존 kci_kri_full_scraper.py에서 가져옴)
    
    Args:
        driver: Selenium WebDriver (iframe 내부에 있어야 함)
        kri_id: KRI 연구자번호
        author_name: 저자 이름 (필수, 성명 검색에 사용)
                     형식: "김용수\n/YONGSOO KIM" -> 한글 이름만 추출
        retry_count: 재시도 횟수 (내부 사용)
    
    Returns:
        dict: {'kri_id', 'name', 'birth', 'gender', 'univ', 'job', 'major', 'grad', 'diploma'}
    """
    try:
        # 검색 전 alert 처리
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            print(f"      Alert 발견 (검색 전): {alert_text}")
            alert.accept()
            time.sleep(1)
        except:
            pass
        
        # 성명에서 한글 이름만 추출
        korean_name = None
        if author_name and pd.notna(author_name) and str(author_name) != 'None':
            # "배경진\n\t\t\t\t\t\t\t\t\t/Kyungjin Bae" -> "배경진"
            korean_name = str(author_name).split('\n')[0].strip()
            korean_name = korean_name.split('/')[0].strip()
            print(f"      추출된 한글 이름: {korean_name}")
        else:
            print(f"      ⚠ 이름 없음 - KRI ID만으로 검색 시도")
        
        # 성명 입력란 찾기 및 입력 (name="txtKorNm")
        if korean_name:
            name_input_success = False
            
            # JavaScript로 직접 입력 (가장 확실한 방법)
            try:
                result = driver.execute_script(f"""
                    var inputs = document.getElementsByName('txtKorNm');
                    if (inputs.length > 0) {{
                        var input = inputs[0];
                        input.value = '{korean_name}';
                        input.focus();
                        
                        // 이벤트 발생
                        var inputEvent = new Event('input', {{ bubbles: true, cancelable: true }});
                        var changeEvent = new Event('change', {{ bubbles: true, cancelable: true }});
                        input.dispatchEvent(inputEvent);
                        input.dispatchEvent(changeEvent);
                        
                        return input.value;
                    }}
                    return null;
                """)
                
                if result == korean_name:
                    print(f"      성명 입력 완료: {korean_name}")
                    name_input_success = True
                elif result:
                    print(f"      성명 입력 불일치: 입력={korean_name}, 실제={result}")
                else:
                    print(f"      성명 입력란을 찾을 수 없음")
                
                time.sleep(0.5)
            except Exception as e:
                print(f"      성명 입력 실패 (JS): {e}")
            
            # JavaScript 실패 시 Selenium으로 시도
            if not name_input_success:
                try:
                    name_input = driver.find_element(By.NAME, 'txtKorNm')
                    
                    # Actions를 사용한 입력
                    actions = ActionChains(driver)
                    actions.move_to_element(name_input)
                    actions.click()
                    actions.pause(0.3)
                    actions.send_keys(Keys.CONTROL + 'a')  # 전체 선택
                    actions.send_keys(Keys.DELETE)  # 삭제
                    actions.pause(0.2)
                    actions.send_keys(korean_name)
                    actions.perform()
                    
                    time.sleep(0.3)
                    current_value = name_input.get_attribute('value')
                    if current_value == korean_name:
                        print(f"      성명 입력 완료 (Actions): {korean_name}")
                        name_input_success = True
                    else:
                        print(f"      Actions 입력 후 불일치: {current_value}")
                except Exception as e:
                    print(f"      성명 입력 최종 실패: {e}")
        
        # 연구자번호(국가연구자번호) 입력란 찾기 및 입력
        search_input = driver.find_element(By.ID, 'txtSearchRschrRegNo')
        search_input.clear()
        time.sleep(0.2)
        search_input.send_keys(str(kri_id))
        print(f"      국가연구자번호 입력: {kri_id}")
        time.sleep(0.3)
        
        # 검색 전 입력값 확인 (모든 txtKorNm 확인)
        all_name_values = driver.execute_script("""
            var inputs = document.getElementsByName('txtKorNm');
            var values = [];
            for(var i = 0; i < inputs.length; i++) {
                values.push({index: i, value: inputs[i].value, visible: inputs[i].offsetParent !== null});
            }
            return values;
        """)
        actual_kri_id = driver.execute_script("return document.getElementById('txtSearchRschrRegNo').value;")
        
        print(f"      [확인] txtKorNm 개수: {len(all_name_values)}")
        for info in all_name_values:
            print(f"        - [index {info['index']}] value='{info['value']}', visible={info['visible']}")
        print(f"      [확인] 국가연구자번호={actual_kri_id}")
        
        # 보이는(visible) 입력란 중에서 값이 제대로 들어간 것이 있는지 확인
        if korean_name:
            has_correct_name = any(info['visible'] and info['value'] == korean_name for info in all_name_values)
            
            if not has_correct_name:
                print(f"      보이는 입력란에 성명이 없음! send_keys()로 직접 입력...")
                # 보이는 입력란 찾기
                name_inputs = driver.find_elements(By.NAME, 'txtKorNm')
                for inp in name_inputs:
                    if inp.is_displayed():
                        # 기존 값 클리어
                        inp.clear()
                        time.sleep(0.2)
                        # 실제 키보드 입력처럼 입력
                        inp.send_keys(korean_name)
                        time.sleep(0.2)
                        print(f"        → 보이는 입력란에 '{korean_name}' 입력 완료")
                        break
                else:
                    # 보이는 입력란이 없으면 JavaScript로 강제 입력
                    print(f"        → 보이는 입력란 없음, JavaScript로 강제 입력")
                    driver.execute_script(f"""
                        var inputs = document.getElementsByName('txtKorNm');
                        for(var i = 0; i < inputs.length; i++) {{
                            inputs[i].value = '{korean_name}';
                        }}
                    """)
                time.sleep(0.5)
        else:
            print(f"      성명 없이 KRI ID만으로 검색 진행...")
        
        # 검색 실행
        print(f"      검색 실행 중...")
        driver.execute_script("doAction('SEARCH');")
        time.sleep(2)
        
        # 검색 직후 alert 처리
        try:
            WebDriverWait(driver, 3).until(EC.alert_is_present())
            alert = driver.switch_to.alert
            alert_text = alert.text
            print(f"      Alert 발견 (검색 후): {alert_text}")
            alert.accept()
            time.sleep(1)
            
            # alert 후 검색이 제대로 안 된 경우 재검색
            print(f"      → Alert 후 재검색 시도 (send_keys 사용)...")
            
            # 이름 다시 입력 (send_keys)
            if korean_name:
                name_inputs = driver.find_elements(By.NAME, 'txtKorNm')
                for inp in name_inputs:
                    if inp.is_displayed():
                        inp.clear()
                        time.sleep(0.2)
                        inp.send_keys(korean_name)
                        time.sleep(0.2)
                        break
            
            # KRI ID 다시 입력 (send_keys)
            kri_input = driver.find_element(By.ID, 'txtSearchRschrRegNo')
            kri_input.clear()
            time.sleep(0.2)
            kri_input.send_keys(kri_id)
            time.sleep(0.2)
            
            # 재검색
            driver.execute_script("doAction('SEARCH');")
            time.sleep(uniform(3, 4))
        except:
            # alert 없음, 정상
            time.sleep(uniform(2, 3))
        
        # 페이지 파싱
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 검색 결과 확인 (데이터 행이 있는지 체크)
        birth_cells_check = soup.find_all('td', class_=lambda x: x and 'HideCol0C3' in x)
        has_data = any(cell.get_text(strip=True) not in ['', '출생년도'] for cell in birth_cells_check)
        
        if not has_data and retry_count == 0:
            print(f"      [경고] 검색 결과 없음! 재검색 시도...")
            
            # 이름 다시 입력 (send_keys 사용)
            if korean_name:
                name_inputs = driver.find_elements(By.NAME, 'txtKorNm')
                for inp in name_inputs:
                    if inp.is_displayed():
                        inp.clear()
                        time.sleep(0.2)
                        inp.send_keys(korean_name)
                        time.sleep(0.2)
                        print(f"        → 재검색: 보이는 입력란에 '{korean_name}' 입력 완료")
                        break
            
            # KRI ID 다시 입력
            kri_input = driver.find_element(By.ID, 'txtSearchRschrRegNo')
            kri_input.clear()
            time.sleep(0.2)
            kri_input.send_keys(kri_id)
            time.sleep(0.2)
            print(f"        → 재검색: KRI ID '{kri_id}' 입력 완료")
            
            # 재검색
            driver.execute_script("doAction('SEARCH');")
            time.sleep(uniform(3, 4))
            
            # 재파싱
            soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 정보 추출 (IBSheet 테이블 구조)
        result = {'kri_id': kri_id}
        
        # 성명 (헤더가 아닌 데이터 셀 찾기)
        name_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C6' in x)
        result['name'] = name_cells[-1].get_text(strip=True) if name_cells else None
        
        # 생년 (헤더가 아닌 데이터 셀 찾기)
        birth_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C3' in x)
        # 헤더 제외하고 실제 데이터만 ("출생년도"가 아닌 숫자 값)
        print(f"      [DEBUG] birth_cells 개수: {len(birth_cells)}")
        for i, cell in enumerate(birth_cells):
            text = cell.get_text(strip=True)
            print(f"        - [index {i}] text='{text}', isdigit={text.isdigit() if text else False}")
            if text and text != '출생년도' and text.isdigit():
                result['birth'] = text
                print(f"      [DEBUG] birth 설정됨: {text}")
                break
        else:
            result['birth'] = None
            print(f"      [DEBUG] birth를 찾지 못함")
        
        # 성별 (헤더가 아닌 데이터 셀 찾기)
        gender_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C7' in x)
        # 헤더 제외하고 실제 데이터만 ("성별"이 아닌 남/여 값)
        print(f"      [DEBUG] gender_cells 개수: {len(gender_cells)}")
        for i, cell in enumerate(gender_cells):
            text = cell.get_text(strip=True)
            print(f"        - [index {i}] text='{text}', in남여={text in ['남', '여']}")
            if text and text != '성별' and text in ['남', '여']:
                result['gender'] = text
                print(f"      [DEBUG] gender 설정됨: {text}")
                break
        else:
            result['gender'] = None
            print(f"      [DEBUG] gender를 찾지 못함")
        
        # 소속대학/기관 (헤더 제외)
        univ_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C8' in x)
        for cell in univ_cells:
            text = cell.get_text(strip=True)
            if text and text != '소속대학/기관':
                result['univ'] = text
                break
        else:
            result['univ'] = None
        
        # 부서 (헤더 제외)
        department_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C9' in x)
        for cell in department_cells:
            text = cell.get_text(strip=True)
            if text and text != '부서':
                result['department'] = text
                break
        else:
            result['department'] = None
        
        # 직급 (헤더 제외)
        job_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C10' in x)
        for cell in job_cells:
            text = cell.get_text(strip=True)
            if text and text != '직급':
                result['job'] = text
                break
        else:
            result['job'] = None
        
        # 전공분야 (헤더 제외)
        major_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C11' in x)
        for cell in major_cells:
            text = cell.get_text(strip=True)
            if text and text != '전공분야':
                result['major'] = text
                break
        else:
            result['major'] = None
        
        # 출신학교 (헤더 제외)
        grad_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C12' in x)
        for cell in grad_cells:
            text = cell.get_text(strip=True)
            if text and text != '출신학교':
                result['grad'] = text
                break
        else:
            result['grad'] = None
        
        # 취득학위 (헤더 제외)
        diploma_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C13' in x)
        for cell in diploma_cells:
            text = cell.get_text(strip=True)
            if text and text != '취득학위':
                result['diploma'] = text
                break
        else:
            result['diploma'] = None
        
        return result
        
    except UnexpectedAlertPresentException as e:
        print(f"    KRI ID {kri_id} 검색 중 예상치 못한 alert 발생")
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            print(f"       Alert 내용: {alert_text}")
            alert.accept()
            time.sleep(1)
        except:
            pass
        
        if retry_count < 1:  # 1번만 재시도
            print(f"    → 재시도 중...")
            time.sleep(2)
            return search_researcher_by_kri_id(driver, kri_id, author_name, retry_count + 1)
        else:
            print(f"    KRI ID {kri_id} - alert 재시도 초과, 건너뜀")
            return None
        
    except Exception as e:
        print(f"    KRI ID {kri_id} 검색 중 오류: {e}")
        return None


def fill_missing_korean_lit():
    """한국현대문학 데이터의 누락된 정보 채우기"""
    print("\n" + "="*70)
    print("한국현대문학 데이터 누락 정보 채우기")
    print("="*70)
    
    # 데이터 로드 - PKL 파일 우선 사용
    pkl_path = 'data/250519_2008_2024_한국현대문학_202324_현대문학_임시_토큰화.pkl'
    csv_path = 'data/250519_2008_2024_한국현대문학_202324_현대문학_임시_토큰화.csv'
    
    if os.path.exists(pkl_path):
        print(f"PKL 파일 로드: {pkl_path}")
        df = pd.read_pickle(pkl_path)
    else:
        print(f"CSV 파일 로드: {csv_path}")
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
    
    print(f"\n전체 행 수: {len(df)}")
    print(f"kri_num 누락: {df['kri_num'].isna().sum()}개")
    print(f"gender 누락: {df['gender'].isna().sum()}개")
    print(f"birth 누락: {df['birth'].isna().sum()}개")
    
    # 누락된 행만 필터링 (kri_num, gender, birth 중 하나라도 누락된 경우)
    missing_df = df[df['kri_num'].isna() | df['gender'].isna() | df['birth'].isna()].copy()
    
    # 실제로 처리할 행 카운트 (이미 완료된 건 제외)
    needs_processing = missing_df[
        ~(missing_df['kri_num'].notna() & missing_df['birth'].notna() & missing_df['gender'].notna())
    ]
    
    print(f"\n처리할 행 수: {len(needs_processing)}개 (전체 결측치: {len(missing_df)}개)")
    
    # 드라이버 설정
    driver = setup_driver()  # KRI용
    kci_driver = None  # KCI용 별도 드라이버
    
    try:
        # KCI 로그인 (별도 드라이버)
        print("\n" + "="*70)
        print("KCI 드라이버 설정 및 로그인 중...")
        print("="*70)
        kci_driver = setup_driver()
        if not login_kci(kci_driver):
            print("KCI 로그인 실패")
            kci_driver.quit()
            driver.quit()
            return
        
        # KRI 로그인 및 팝업창(iframe) 준비
        login_success, kri_driver = login_kri(driver)
        if not login_success:
            print("KRI 로그인 실패")
            if kci_driver:
                kci_driver.quit()
            driver.quit()
            return
        
        # 결과 저장용
        results = []
        processed_count = 0  # 실제 처리한 개수
        
        # 각 article-id 처리
        for idx, row in tqdm(missing_df.iterrows(), total=len(missing_df), desc=f"데이터 수집 (실제 처리 대상: ~{len(needs_processing)}개)"):
            article_id = row['article-id']
            current_kri = row['kri_num']
            current_birth = row['birth']
            current_gender = row['gender']
            
            # 이미 모든 정보가 채워진 경우 건너뛰기 (CSV에 기록하지 않음)
            if pd.notna(current_kri) and pd.notna(current_birth) and pd.notna(current_gender):
                continue
            
            processed_count += 1
            
            result_row = {
                'article-id': article_id,
                'original_kri_num': current_kri,
                'new_kri_num': None,
                'crt_id': None,
                'author_name': None,
                'birth': None,
                'gender': None,
                'status': 'pending'
            }
            
            try:
                # 1. KCI에서 저자 정보 및 KRI ID 가져오기 (KRI ID가 없는 경우만)
                if pd.isna(current_kri):
                    print(f"\n[{processed_count}] Article {article_id}: KCI에서 저자 정보 수집 중...")
                    author_info = get_author_kri_info_from_kci(kci_driver, article_id)
                    
                    if author_info['status'] == '저자 정보 없음':
                        print(f"    Article {article_id}: 저자 정보 없음")
                        result_row['status'] = 'no_author'
                        results.append(result_row)
                        continue
                    
                    result_row['crt_id'] = author_info['cret_id']
                    result_row['author_name'] = author_info['author_name']
                    
                    if not author_info['kri_id']:
                        print(f"    Article {article_id}: KRI ID 없음")
                        
                        # KRI ID가 없어도 CRT ID와 한글 이름은 저장
                        author_name = author_info['author_name']
                        if author_name and pd.notna(author_name) and str(author_name) != 'None':
                            # "배경진\n\t\t\t\t\t\t\t\t\t/Kyungjin Bae" -> "배경진"
                            korean_name = str(author_name).split('\n')[0].strip()
                            korean_name = korean_name.split('/')[0].strip()
                        else:
                            korean_name = None
                        
                        # 원본 PKL에 CRT ID와 한글 이름 즉시 저장
                        article_id_to_update = result_row['article-id']
                        idx_to_update = df[df['article-id'] == article_id_to_update].index
                        if len(idx_to_update) > 0:
                            idx_to_update = idx_to_update[0]
                            if 'crt_id' not in df.columns:
                                df['crt_id'] = None
                            if 'author_name_kor' not in df.columns:
                                df['author_name_kor'] = None
                            
                            df.loc[idx_to_update, 'crt_id'] = author_info['cret_id']
                            df.loc[idx_to_update, 'author_name_kor'] = korean_name
                            
                            # 즉시 저장
                            df.to_pickle(pkl_path)
                            print(f"    ✅ CRT ID와 이름 저장 완료 (KRI ID 없음): crt_id={author_info['cret_id']}, name={korean_name}")
                        
                        result_row['status'] = 'no_kri_id'
                        results.append(result_row)
                        continue
                    
                    kri_id = author_info['kri_id']
                    result_row['new_kri_num'] = kri_id
                    print(f"    CRT={author_info['cret_id']}, 저자={author_info['author_name']}, KRI={kri_id}")
                else:
                    # 이미 kri_num이 있는 경우 - 저자 이름만 가져오기
                    kri_id = str(int(current_kri))
                    result_row['new_kri_num'] = kri_id
                    print(f"\n[{processed_count}] Article {article_id}: 기존 KRI ID={kri_id} 사용")
                    
                    # 저자 이름 가져오기 (KRI 검색에 필요)
                    print(f"    KCI에서 저자 이름 수집 중...")
                    author_info = get_author_kri_info_from_kci(kci_driver, article_id)
                    if author_info.get('author_name'):
                        result_row['author_name'] = author_info['author_name']
                        result_row['crt_id'] = author_info.get('cret_id')
                        print(f"    저자={author_info['author_name']}")
                
                # 3. KRI에서 연구자 정보 수집
                print(f"    KRI ID {kri_id}로 생년/성별 수집 중...")
                researcher_info = search_researcher_by_kri_id(driver, kri_id, result_row.get('author_name'))
                
                if researcher_info:
                    result_row['birth'] = researcher_info.get('birth')
                    result_row['gender'] = researcher_info.get('gender')
                    result_row['univ'] = researcher_info.get('univ')
                    result_row['department'] = researcher_info.get('department')
                    result_row['job'] = researcher_info.get('job')
                    result_row['major'] = researcher_info.get('major')
                    result_row['grad'] = researcher_info.get('grad')
                    result_row['diploma'] = researcher_info.get('diploma')
                    result_row['status'] = 'success'
                else:
                    result_row['status'] = 'no_researcher_info'
                
                results.append(result_row)
                
                # 바로바로 원본 PKL 파일 업데이트 (모든 필드)
                if result_row['status'] == 'success':
                    article_id_to_update = result_row['article-id']
                    idx_to_update = df[df['article-id'] == article_id_to_update].index
                    if len(idx_to_update) > 0:
                        idx_to_update = idx_to_update[0]
                        
                        # 필요한 컬럼이 없으면 추가
                        for col in ['kri_num', 'crt_id', 'author_name_kor', 'birth', 'gender', 
                                    'univ', 'department', 'job', 'major', 'grad', 'diploma']:
                            if col not in df.columns:
                                df[col] = None
                        
                        # 한글 이름 추출
                        author_name = result_row.get('author_name')
                        if author_name and pd.notna(author_name) and str(author_name) != 'None':
                            korean_name = str(author_name).split('\n')[0].strip()
                            korean_name = korean_name.split('/')[0].strip()
                        else:
                            korean_name = None
                        
                        # 모든 필드 저장
                        if pd.notna(result_row['new_kri_num']):
                            df.loc[idx_to_update, 'kri_num'] = float(result_row['new_kri_num'])
                        if pd.notna(result_row['crt_id']):
                            df.loc[idx_to_update, 'crt_id'] = result_row['crt_id']
                        if korean_name:
                            df.loc[idx_to_update, 'author_name_kor'] = korean_name
                        if pd.notna(result_row['birth']):
                            df.loc[idx_to_update, 'birth'] = result_row['birth']
                        if pd.notna(result_row['gender']):
                            df.loc[idx_to_update, 'gender'] = result_row['gender']
                        if pd.notna(result_row['univ']):
                            df.loc[idx_to_update, 'univ'] = result_row['univ']
                        if pd.notna(result_row['department']):
                            df.loc[idx_to_update, 'department'] = result_row['department']
                        if pd.notna(result_row['job']):
                            df.loc[idx_to_update, 'job'] = result_row['job']
                        if pd.notna(result_row['major']):
                            df.loc[idx_to_update, 'major'] = result_row['major']
                        if pd.notna(result_row['grad']):
                            df.loc[idx_to_update, 'grad'] = result_row['grad']
                        if pd.notna(result_row['diploma']):
                            df.loc[idx_to_update, 'diploma'] = result_row['diploma']
                        
                        # 원본 PKL 파일 즉시 저장
                        df.to_pickle(pkl_path)
                        print(f"    ✅ 원본 PKL 즉시 저장 완료: 모든 필드 업데이트")
                
                # 10개마다 중간 결과 CSV 저장
                if len(results) % 10 == 0:
                    os.makedirs('revise_data', exist_ok=True)
                    temp_df = pd.DataFrame(results)
                    temp_df.to_csv('revise_data/fill_missing_temp_korean_lit.csv', index=False, encoding='utf-8-sig')
                    print(f"\n  → 중간 결과 CSV 저장: {len(results)}개 처리")
                
                time.sleep(uniform(2, 3))
                
            except Exception as e:
                print(f"    오류 발생: {e}")
                result_row['status'] = f'error: {str(e)}'
                results.append(result_row)
                continue
        
        # 최종 결과 저장
        os.makedirs('revise_data', exist_ok=True)
        results_df = pd.DataFrame(results)
        results_df.to_csv('revise_data/fill_missing_results_korean_lit.csv', index=False, encoding='utf-8-sig')
        print(f"\n최종 결과 저장: revise_data/fill_missing_results_korean_lit.csv")
        
        # 원본 데이터에 병합하여 새 버전 저장
        print("\n원본 데이터에 결과 병합 중...")
        # article-id를 키로 병합
        df_merged = df.copy()
        for _, result_row in results_df.iterrows():
            article_id = result_row['article-id']
            idx = df_merged[df_merged['article-id'] == article_id].index
            if len(idx) > 0:
                idx = idx[0]
                if result_row['status'] == 'success':
                    if pd.notna(result_row['new_kri_num']):
                        df_merged.loc[idx, 'kri_num'] = result_row['new_kri_num']
                    if pd.notna(result_row['birth']):
                        df_merged.loc[idx, 'birth'] = result_row['birth']
                    if pd.notna(result_row['gender']):
                        df_merged.loc[idx, 'gender'] = result_row['gender']
        
        # PKL 파일 업데이트 (원본)
        df_merged.to_pickle(pkl_path)
        print(f"\n원본 PKL 파일 업데이트 완료: {pkl_path}")
        
        # CSV 파일도 업데이트
        if os.path.exists(csv_path):
            df_merged.to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"원본 CSV 파일 업데이트 완료: {csv_path}")
        
        # 백업본 저장
        backup_csv = 'revise_data/250519_2008_2024_한국현대문학_revised.csv'
        backup_pkl = 'revise_data/250519_2008_2024_한국현대문학_revised.pkl'
        df_merged.to_csv(backup_csv, index=False, encoding='utf-8-sig')
        df_merged.to_pickle(backup_pkl)
        print(f"백업 파일 저장: {backup_csv}")
        print(f"백업 파일 저장: {backup_pkl}")
        
        # 통계 출력
        print("\n" + "="*70)
        print("수집 결과 통계")
        print("="*70)
        print(results_df['status'].value_counts())
        
    finally:
        driver.quit()
        if kci_driver:
            kci_driver.quit()


def fill_missing_english_lit():
    """영어영문 데이터의 CRT ID 및 KRI 정보 수집"""
    print("\n" + "="*70)
    print("영어영문학 데이터 CRT ID 및 KRI 정보 수집")
    print("="*70)
    
    # 데이터 로드 (pkl 파일)
    pkl_path = 'data/250602_영어영문_토큰화.pkl'
    df = pd.read_pickle(pkl_path)
    
    print(f"\n전체 행 수: {len(df)}")
    print(f"컬럼: {df.columns.tolist()}")
    print(f"\n샘플 데이터:")
    print(df.head())
    
    # article-id 컬럼 확인
    if 'article-id' not in df.columns and 'artid' in df.columns:
        df.rename(columns={'artid': 'article-id'}, inplace=True)
    
    # 드라이버 설정
    driver = setup_driver()  # KRI용
    kci_driver = None  # KCI용 별도 드라이버
    
    try:
        # KCI 로그인 (별도 드라이버)
        print("\n" + "="*70)
        print("KCI 드라이버 설정 및 로그인 중...")
        print("="*70)
        kci_driver = setup_driver()
        if not login_kci(kci_driver):
            print("KCI 로그인 실패")
            kci_driver.quit()
            driver.quit()
            return
        
        # KRI 로그인 및 팝업창(iframe) 준비
        login_success, kri_driver = login_kri(driver)
        if not login_success:
            print("KRI 로그인 실패")
            if kci_driver:
                kci_driver.quit()
            driver.quit()
            return
        
        results = []
        
        # 각 article-id 처리
        for idx, row in tqdm(df.iterrows(), total=len(df), desc="영문학 데이터 수집"):
            article_id = row['article-id']
            
            # 기존 데이터 확인
            existing_author = row.get('author_name') if 'author_name' in df.columns else None
            existing_kri = row.get('kri_num') if 'kri_num' in df.columns else None
            existing_crt = row.get('crt_id') if 'crt_id' in df.columns else None
            
            result_row = {
                'article-id': article_id,
                'crt_id': existing_crt,
                'author_name': existing_author,
                'kri_num': existing_kri,
                'birth': None,
                'gender': None,
                'status': 'pending'
            }
            
            try:
                # 1. 저자 이름이나 KRI ID가 없으면 KCI에서 가져오기
                if pd.isna(existing_author) or pd.isna(existing_kri) or pd.isna(existing_crt):
                    print(f"\n[{idx}] Article {article_id}: KCI에서 저자 정보 수집 중...")
                    author_info = get_author_kri_info_from_kci(kci_driver, article_id)
                    
                    if author_info['status'] == '저자 정보 없음':
                        print(f"    Article {article_id}: 저자 정보 없음")
                        result_row['status'] = 'no_author'
                        results.append(result_row)
                        continue
                    
                    # 없는 정보만 업데이트
                    if pd.isna(existing_crt):
                        result_row['crt_id'] = author_info['cret_id']
                    if pd.isna(existing_author):
                        result_row['author_name'] = author_info['author_name']
                    if pd.isna(existing_kri):
                        result_row['kri_num'] = author_info['kri_id']
                    
                    if not result_row['kri_num']:
                        print(f"    Article {article_id}: KRI ID 없음")
                        result_row['status'] = 'no_kri_id'
                        results.append(result_row)
                        continue
                    
                    kri_id = result_row['kri_num']
                    print(f"    CRT={result_row['crt_id']}, 저자={result_row['author_name']}, KRI={kri_id}")
                else:
                    # 기존 정보 사용
                    kri_id = str(int(existing_kri))
                    result_row['kri_num'] = kri_id
                    print(f"\n[{idx}] Article {article_id}: 기존 정보 사용 (저자={existing_author}, KRI={kri_id})")
                
                # 2. KRI에서 연구자 정보 수집
                print(f"    KRI ID {kri_id}로 생년/성별 수집 중...")
                researcher_info = search_researcher_by_kri_id(driver, kri_id, result_row['author_name'])
                
                if researcher_info:
                    result_row['birth'] = researcher_info.get('birth')
                    result_row['gender'] = researcher_info.get('gender')
                    result_row['status'] = 'success'
                else:
                    result_row['status'] = 'no_researcher_info'
                
                results.append(result_row)
                
                # 10개마다 중간 저장
                if len(results) % 10 == 0:
                    os.makedirs('revise_data', exist_ok=True)
                    temp_df = pd.DataFrame(results)
                    temp_df.to_csv('revise_data/fill_missing_temp_english_lit.csv', index=False, encoding='utf-8-sig')
                    print(f"\n  → 중간 저장 완료: {len(results)}개 처리")
                
                time.sleep(uniform(2, 3))
                
            except Exception as e:
                print(f"    오류 발생: {e}")
                result_row['status'] = f'error: {str(e)}'
                results.append(result_row)
                continue
        
        # 최종 결과 저장
        os.makedirs('revise_data', exist_ok=True)
        results_df = pd.DataFrame(results)
        results_df.to_csv('revise_data/fill_missing_results_english_lit.csv', index=False, encoding='utf-8-sig')
        print(f"\n최종 결과 저장: revise_data/fill_missing_results_english_lit.csv")
        
        # 원본 데이터에 병합하여 새 버전 저장
        print("\n원본 데이터에 결과 병합 중...")
        # article-id를 키로 병합
        df_merged = df.copy()
        for _, result_row in results_df.iterrows():
            article_id = result_row['article-id']
            idx = df_merged[df_merged['article-id'] == article_id].index
            if len(idx) > 0:
                idx = idx[0]
                # 성공 여부와 관계없이 수집된 정보는 모두 업데이트
                if pd.notna(result_row['crt_id']):
                    # crt_id 컬럼이 없으면 추가
                    if 'crt_id' not in df_merged.columns:
                        df_merged['crt_id'] = None
                    df_merged.loc[idx, 'crt_id'] = result_row['crt_id']
                if pd.notna(result_row['author_name']):
                    if 'author_name' not in df_merged.columns:
                        df_merged['author_name'] = None
                    df_merged.loc[idx, 'author_name'] = result_row['author_name']
                if pd.notna(result_row['kri_num']):
                    if 'kri_num' not in df_merged.columns:
                        df_merged['kri_num'] = None
                    df_merged.loc[idx, 'kri_num'] = result_row['kri_num']
                if pd.notna(result_row['birth']):
                    if 'birth' not in df_merged.columns:
                        df_merged['birth'] = None
                    df_merged.loc[idx, 'birth'] = result_row['birth']
                if pd.notna(result_row['gender']):
                    if 'gender' not in df_merged.columns:
                        df_merged['gender'] = None
                    df_merged.loc[idx, 'gender'] = result_row['gender']
        
        # 원본 PKL 파일 직접 업데이트
        df_merged.to_pickle(pkl_path)
        print(f"\n원본 파일 업데이트 완료: {pkl_path}")
        
        # 백업본도 저장
        df_merged.to_pickle('revise_data/250602_영어영문_revised.pkl')
        print(f"백업 파일 저장: revise_data/250602_영어영문_revised.pkl")
        
        # 통계 출력
        print("\n" + "="*70)
        print("수집 결과 통계")
        print("="*70)
        print(results_df['status'].value_counts())
        
    finally:
        driver.quit()
        if kci_driver:
            kci_driver.quit()


def process_pkl_file(pkl_path):
    """PKL 파일의 누락된 정보 채우기 (통합 함수)"""
    print("\n" + "="*70)
    print(f"파일 처리 중: {pkl_path}")
    print("="*70)
    
    # 데이터 로드 (pkl 파일)
    df = pd.read_pickle(pkl_path)
    
    print(f"\n전체 행 수: {len(df)}")
    print(f"컬럼: {df.columns.tolist()}")
    
    # article-id 또는 author-id 컬럼 확인
    if 'article-id' not in df.columns and 'artid' in df.columns:
        df.rename(columns={'artid': 'article-id'}, inplace=True)
    
    # article-id가 없으면 author-id 기반 파일인지 확인
    is_author_based = False
    if 'article-id' not in df.columns:
        if 'author-id' in df.columns and 'kri_num' in df.columns:
            print("→ author-id 기반 파일입니다. kri_num을 이용해 누락된 birth/gender 채우기")
            is_author_based = True
        else:
            print(f"⚠ 'article-id' 또는 'author-id' 컬럼을 찾을 수 없습니다. 건너뜁니다.")
            return
    
    # 드라이버 설정
    driver = setup_driver()  # KRI용
    kci_driver = None  # KCI용 별도 드라이버
    
    try:
        # KCI 로그인 (별도 드라이버)
        print("\n" + "="*70)
        print("KCI 드라이버 설정 및 로그인 중...")
        print("="*70)
        kci_driver = setup_driver()
        if not login_kci(kci_driver):
            print("KCI 로그인 실패")
            kci_driver.quit()
            driver.quit()
            return
        
        # KRI 로그인 및 팝업창(iframe) 준비
        login_success, kri_driver = login_kri(driver)
        if not login_success:
            print("KRI 로그인 실패")
            if kci_driver:
                kci_driver.quit()
            driver.quit()
            return
        
        results = []
        
        # author-id 기반 파일 처리 (kri_num이 이미 있는 경우)
        if is_author_based:
            print("\n→ author-id 기반 파일: kri_num으로 누락된 birth/gender만 수집")
            
            # 처리할 행 수 미리 계산
            needs_processing = df[
                (df['kri_num'].notna()) & 
                ((df.get('birth').isna()) | (df.get('gender').isna()))
            ]
            total_needs_processing = len(needs_processing)
            print(f"처리 대상: {total_needs_processing}개 / 전체: {len(df)}개")
            
            processed_count = 0
            for idx, row in tqdm(df.iterrows(), total=len(df), desc=f"실제 처리: {processed_count}/{total_needs_processing}"):
                existing_kri = row.get('kri_num')
                existing_birth = row.get('birth') if 'birth' in df.columns else None
                existing_gender = row.get('gender') if 'gender' in df.columns else None
                existing_name = row.get('name') if 'name' in df.columns else None
                author_id = row.get('author-id')  # CRT ID로 사용 가능
                
                # birth와 gender가 모두 있으면 건너뛰기
                if pd.notna(existing_birth) and pd.notna(existing_gender):
                    continue
                
                # kri_num이 없으면 건너뛰기
                if pd.isna(existing_kri):
                    continue
                
                processed_count += 1
                processed_count += 1
                
                kri_id = str(int(existing_kri))
                
                result_row = {
                    'author-id': author_id,
                    'kri_num': kri_id,
                    'name': existing_name,
                    'birth': existing_birth,
                    'gender': existing_gender,
                    'status': 'pending'
                }
                
                data_updated = False  # 데이터 업데이트 추적
                
                try:
                    # 이름이 없으면 KCI에서 가져오기 (author-id = CRT ID)
                    if pd.isna(existing_name) or str(existing_name) == 'None':
                        print(f"\n[{processed_count}/{total_needs_processing}] Author ID {author_id}: 이름 없음, KCI에서 이름 수집 중...")
                        # KCI 저자 프로필에서 이름 추출 (임시 article ID 사용)
                        # author-id가 CRT ID이므로 직접 프로필 페이지 접근
                        try:
                            profile_url = f'https://www.kci.go.kr/kciportal/po/citationindex/poCretDetail.kci?citationBean.cretId={author_id}'
                            kci_driver.get(profile_url)
                            time.sleep(uniform(1, 1.5))
                            
                            soup = BeautifulSoup(kci_driver.page_source, 'html.parser')
                            # 이름 추출 (페이지 상단의 저자명)
                            name_elem = soup.find('h3', class_='name')
                            if not name_elem:
                                name_elem = soup.find('strong', class_='name')
                            if name_elem:
                                author_name = name_elem.get_text(strip=True)
                                result_row['name'] = author_name
                                existing_name = author_name
                                
                                # 즉시 PKL 파일 업데이트
                                if 'name' not in df.columns:
                                    df['name'] = None
                                df.at[idx, 'name'] = author_name
                                data_updated = True
                                print(f"    KCI에서 이름 수집 완료: {author_name}")
                        except Exception as e:
                            print(f"    KCI에서 이름 수집 실패: {e}")
                    
                    # KRI에서 생년/성별 수집
                    if pd.isna(existing_birth) or pd.isna(existing_gender):
                        print(f"\n[{processed_count}/{total_needs_processing}] KRI ID {kri_id} (이름: {existing_name}): 생년/성별 수집 중...")
                        researcher_info = search_researcher_by_kri_id(driver, kri_id, existing_name)
                        
                        if researcher_info:
                            if pd.isna(existing_birth):
                                result_row['birth'] = researcher_info.get('birth')
                                # 즉시 PKL 파일 업데이트
                                if 'birth' not in df.columns:
                                    df['birth'] = None
                                df.at[idx, 'birth'] = researcher_info.get('birth')
                                data_updated = True
                            if pd.isna(existing_gender):
                                result_row['gender'] = researcher_info.get('gender')
                                # 즉시 PKL 파일 업데이트
                                if 'gender' not in df.columns:
                                    df['gender'] = None
                                df.at[idx, 'gender'] = researcher_info.get('gender')
                                data_updated = True
                            result_row['status'] = 'success'
                            print(f"    수집 완료: birth={result_row['birth']}, gender={result_row['gender']}")
                        else:
                            result_row['status'] = 'no_researcher_info'
                    
                    # 데이터가 업데이트되었으면 즉시 PKL 파일 저장
                    if data_updated:
                        df.to_pickle(pkl_path)
                        print(f"    → PKL 파일 즉시 업데이트 완료")
                    
                    results.append(result_row)
                    
                    # 10개마다 중간 저장
                    if len(results) % 10 == 0:
                        os.makedirs('revise_data', exist_ok=True)
                        temp_df = pd.DataFrame(results)
                        temp_filename = f"fill_missing_temp_{os.path.basename(pkl_path).replace('.pkl', '.csv')}"
                        temp_df.to_csv(f'revise_data/{temp_filename}', index=False, encoding='utf-8-sig')
                        print(f"\n  → 중간 저장 완료: {len(results)}개 처리")
                    
                    time.sleep(uniform(2, 3))
                    
                except Exception as e:
                    print(f"    오류 발생: {e}")
                    result_row['status'] = f'error: {str(e)}'
                    results.append(result_row)
                    continue
            
            # author-id 기반 파일의 병합 처리
            if results:
                os.makedirs('revise_data', exist_ok=True)
                results_df = pd.DataFrame(results)
                result_filename = f"fill_missing_results_{os.path.basename(pkl_path).replace('.pkl', '.csv')}"
                results_df.to_csv(f'revise_data/{result_filename}', index=False, encoding='utf-8-sig')
                print(f"\n최종 결과 저장: revise_data/{result_filename}")
                
                # 원본 데이터에 병합
                print("\n원본 데이터에 결과 병합 중...")
                df_merged = df.copy()
                for _, result_row in results_df.iterrows():
                    author_id = result_row['author-id']
                    idx = df_merged[df_merged['author-id'] == author_id].index
                    if len(idx) > 0:
                        idx = idx[0]
                        if pd.notna(result_row['name']):
                            if 'name' not in df_merged.columns:
                                df_merged['name'] = None
                            df_merged.loc[idx, 'name'] = result_row['name']
                        if pd.notna(result_row['birth']):
                            df_merged.loc[idx, 'birth'] = result_row['birth']
                        if pd.notna(result_row['gender']):
                            df_merged.loc[idx, 'gender'] = result_row['gender']
                
                # 원본 파일 업데이트
                df_merged.to_pickle(pkl_path)
                print(f"\n원본 파일 업데이트 완료: {pkl_path}")
                
                # 백업본 저장
                backup_filename = f"{os.path.basename(pkl_path).replace('.pkl', '_revised.pkl')}"
                df_merged.to_pickle(f'revise_data/{backup_filename}')
                print(f"백업 파일 저장: revise_data/{backup_filename}")
                
                # 통계 출력
                print("\n" + "="*70)
                print("수집 결과 통계")
                print("="*70)
                print(results_df['status'].value_counts())
            else:
                print("\n→ 처리할 누락 데이터가 없습니다.")
            
            return
        
        # article-id 기반 파일 처리
        # 처리할 행 수 미리 계산 (kri_num, birth, gender만 체크)
        mask = pd.Series([False] * len(df), index=df.index)
        if 'kri_num' in df.columns:
            mask |= df['kri_num'].isna()
        if 'birth' in df.columns:
            mask |= df['birth'].isna()
        if 'gender' in df.columns:
            mask |= df['gender'].isna()
        
        needs_processing = df[mask]
        total_needs_processing = len(needs_processing)
        print(f"\n처리 대상: {total_needs_processing}개 / 전체: {len(df)}개")
        
        processed_count = 0
        for idx, row in tqdm(df.iterrows(), total=len(df), desc=f"실제 처리: {processed_count}/{total_needs_processing}"):
            article_id = row['article-id']
            
            # 기존 데이터 확인
            existing_author = row.get('author_name') if 'author_name' in df.columns else None
            existing_kri = row.get('kri_num') if 'kri_num' in df.columns else None
            existing_crt = row.get('crt_id') if 'crt_id' in df.columns else None
            existing_birth = row.get('birth') if 'birth' in df.columns else None
            existing_gender = row.get('gender') if 'gender' in df.columns else None
            
            # kri_num, birth, gender가 모두 있으면 건너뛰기
            if all(pd.notna(x) for x in [existing_kri, existing_birth, existing_gender]):
                continue
            
            processed_count += 1
            
            result_row = {
                'article-id': article_id,
                'crt_id': existing_crt,
                'author_name': existing_author,
                'kri_num': existing_kri,
                'birth': existing_birth,
                'gender': existing_gender,
                'status': 'pending'
            }
            
            data_updated = False  # 데이터 업데이트 추적
            
            try:
                # 1. 저자 이름이나 KRI ID가 없으면 KCI에서 가져오기
                if pd.isna(existing_author) or pd.isna(existing_kri) or pd.isna(existing_crt):
                    print(f"\n[{processed_count}/{total_needs_processing}] Article {article_id}: KCI에서 저자 정보 수집 중...")
                    author_info = get_author_kri_info_from_kci(kci_driver, article_id)
                    
                    if author_info['status'] == '저자 정보 없음':
                        print(f"    Article {article_id}: 저자 정보 없음")
                        result_row['status'] = 'no_author'
                        results.append(result_row)
                        continue
                    
                    # 없는 정보만 업데이트
                    if pd.isna(existing_crt):
                        result_row['crt_id'] = author_info['cret_id']
                        if 'crt_id' not in df.columns:
                            df['crt_id'] = None
                        df.at[idx, 'crt_id'] = author_info['cret_id']
                        data_updated = True
                    if pd.isna(existing_author):
                        result_row['author_name'] = author_info['author_name']
                        if 'author_name' not in df.columns:
                            df['author_name'] = None
                        df.at[idx, 'author_name'] = author_info['author_name']
                        data_updated = True
                    if pd.isna(existing_kri):
                        result_row['kri_num'] = author_info['kri_id']
                        if 'kri_num' not in df.columns:
                            df['kri_num'] = None
                        df.at[idx, 'kri_num'] = author_info['kri_id']
                        data_updated = True
                    
                    if not result_row['kri_num']:
                        print(f"    Article {article_id}: KRI ID 없음")
                        
                        # KRI ID가 없어도 CRT ID와 한글 이름은 저장
                        author_name = result_row['author_name']
                        if author_name and pd.notna(author_name) and str(author_name) != 'None':
                            korean_name = str(author_name).split('\n')[0].strip()
                            korean_name = korean_name.split('/')[0].strip()
                        else:
                            korean_name = None
                        
                        if 'author_name_kor' not in df.columns:
                            df['author_name_kor'] = None
                        if korean_name:
                            df.at[idx, 'author_name_kor'] = korean_name
                            data_updated = True
                        
                        result_row['status'] = 'no_kri_id'
                        results.append(result_row)
                        
                        # 데이터가 업데이트되었으면 즉시 PKL 파일 저장
                        if data_updated:
                            df.to_pickle(pkl_path)
                            print(f"    ✅ CRT ID와 이름 저장 완료 (KRI ID 없음)")
                        continue
                    
                    kri_id = result_row['kri_num']
                    print(f"    CRT={result_row['crt_id']}, 저자={result_row['author_name']}, KRI={kri_id}")
                else:
                    # 기존 정보 사용
                    kri_id = str(int(existing_kri))
                    result_row['kri_num'] = kri_id
                    print(f"\n[{processed_count}/{total_needs_processing}] Article {article_id}: 기존 정보 사용 (저자={existing_author}, KRI={kri_id})")
                
                # 2. KRI에서 연구자 정보 수집 (모든 필드)
                print(f"    KRI ID {kri_id}로 연구자 정보 수집 중...")
                researcher_info = search_researcher_by_kri_id(driver, kri_id, result_row['author_name'])
                
                if researcher_info:
                    # 모든 필드를 result_row에 저장
                    result_row['birth'] = researcher_info.get('birth')
                    result_row['gender'] = researcher_info.get('gender')
                    result_row['univ'] = researcher_info.get('univ')
                    result_row['department'] = researcher_info.get('department')
                    result_row['job'] = researcher_info.get('job')
                    result_row['major'] = researcher_info.get('major')
                    result_row['grad'] = researcher_info.get('grad')
                    result_row['diploma'] = researcher_info.get('diploma')
                    
                    # 즉시 PKL 파일에 모든 필드 업데이트
                    for col in ['birth', 'gender', 'univ', 'department', 'job', 'major', 'grad', 'diploma']:
                        if col not in df.columns:
                            df[col] = None
                        if pd.notna(researcher_info.get(col)):
                            df.at[idx, col] = researcher_info.get(col)
                            data_updated = True
                    
                    # 한글 이름 추출 및 저장
                    author_name = result_row['author_name']
                    if author_name and pd.notna(author_name) and str(author_name) != 'None':
                        korean_name = str(author_name).split('\n')[0].strip()
                        korean_name = korean_name.split('/')[0].strip()
                        if 'author_name_kor' not in df.columns:
                            df['author_name_kor'] = None
                        df.at[idx, 'author_name_kor'] = korean_name
                        data_updated = True
                    
                    result_row['status'] = 'success'
                else:
                    result_row['status'] = 'no_researcher_info'
                
                # 데이터가 업데이트되었으면 즉시 PKL 파일 저장
                if data_updated:
                    df.to_pickle(pkl_path)
                    print(f"    → PKL 파일 즉시 업데이트 완료")
                
                results.append(result_row)
                
                # 10개마다 중간 저장
                if len(results) % 10 == 0:
                    os.makedirs('revise_data', exist_ok=True)
                    temp_df = pd.DataFrame(results)
                    temp_filename = f"fill_missing_temp_{os.path.basename(pkl_path).replace('.pkl', '.csv')}"
                    temp_df.to_csv(f'revise_data/{temp_filename}', index=False, encoding='utf-8-sig')
                    print(f"\n  → 중간 저장 완료: {len(results)}개 처리")
                
                time.sleep(uniform(2, 3))
                
            except Exception as e:
                print(f"    오류 발생: {e}")
                result_row['status'] = f'error: {str(e)}'
                results.append(result_row)
                continue
        
        # 최종 결과 저장
        os.makedirs('revise_data', exist_ok=True)
        results_df = pd.DataFrame(results)
        result_filename = f"fill_missing_results_{os.path.basename(pkl_path).replace('.pkl', '.csv')}"
        results_df.to_csv(f'revise_data/{result_filename}', index=False, encoding='utf-8-sig')
        print(f"\n최종 결과 저장: revise_data/{result_filename}")
        
        # 원본 데이터에 병합
        print("\n원본 데이터에 결과 병합 중...")
        df_merged = df.copy()
        for _, result_row in results_df.iterrows():
            article_id = result_row['article-id']
            idx = df_merged[df_merged['article-id'] == article_id].index
            if len(idx) > 0:
                idx = idx[0]
                # 수집된 정보는 모두 업데이트
                if pd.notna(result_row['crt_id']):
                    if 'crt_id' not in df_merged.columns:
                        df_merged['crt_id'] = None
                    df_merged.loc[idx, 'crt_id'] = result_row['crt_id']
                if pd.notna(result_row['author_name']):
                    if 'author_name' not in df_merged.columns:
                        df_merged['author_name'] = None
                    df_merged.loc[idx, 'author_name'] = result_row['author_name']
                if pd.notna(result_row['kri_num']):
                    if 'kri_num' not in df_merged.columns:
                        df_merged['kri_num'] = None
                    df_merged.loc[idx, 'kri_num'] = result_row['kri_num']
                if pd.notna(result_row['birth']):
                    if 'birth' not in df_merged.columns:
                        df_merged['birth'] = None
                    df_merged.loc[idx, 'birth'] = result_row['birth']
                if pd.notna(result_row['gender']):
                    if 'gender' not in df_merged.columns:
                        df_merged['gender'] = None
                    df_merged.loc[idx, 'gender'] = result_row['gender']
        
        # 원본 PKL 파일 직접 업데이트
        df_merged.to_pickle(pkl_path)
        print(f"\n원본 파일 업데이트 완료: {pkl_path}")
        
        # 백업본도 저장
        backup_filename = f"{os.path.basename(pkl_path).replace('.pkl', '_revised.pkl')}"
        df_merged.to_pickle(f'revise_data/{backup_filename}')
        print(f"백업 파일 저장: revise_data/{backup_filename}")
        
        # 통계 출력
        print("\n" + "="*70)
        print("수집 결과 통계")
        print("="*70)
        print(results_df['status'].value_counts())
        
    finally:
        driver.quit()
        if kci_driver:
            kci_driver.quit()


if __name__ == "__main__":
    import sys
    
    # 처리할 파일 목록
    PKL_FILES = [
        'data/250519_2008_2024_한국현대문학_202324_현대문학_임시_토큰화.pkl'
    ]
    
    CSV_FILES = [
        'data/250519_2008_2024_한국현대문학_202324_현대문학_임시_토큰화.csv'
    ]
    
    print(f"[DEBUG] sys.argv = {sys.argv}")
    print(f"[DEBUG] len(sys.argv) = {len(sys.argv)}")
    
    # 기본값은 pkl
    if len(sys.argv) < 2:
        print("모드 미지정, 기본값 'pkl' 사용")
        print("사용법:")
        print("  python fill_missing_data.py          # PKL 파일 처리 (기본값)")
        print("  python fill_missing_data.py korean   # 한국현대문학 CSV 처리")
        print("  python fill_missing_data.py pkl      # PKL 파일 처리")
        print("  python fill_missing_data.py all      # 모두 처리")
        mode = 'pkl'
    else:
        mode = sys.argv[1].lower()
    
    if mode == 'korean':
        fill_missing_korean_lit()
    elif mode == 'pkl':
        # 한국현대문학 PKL 파일만 처리
        target_file = r"data\250519_2008_2024_한국현대문학_202324_현대문학_임시_토큰화.pkl"
        
        if os.path.exists(target_file):
            print(f"\n{'='*80}")
            print(f"처리 대상 파일: {target_file}")
            print(f"{'='*80}")
            process_pkl_file(target_file)
        else:
            print(f"⚠ 파일을 찾을 수 없습니다: {target_file}")
    elif mode == 'all':
        # CSV 파일 처리
        fill_missing_korean_lit()
        
        # PKL 파일들 처리
        for pkl_file in PKL_FILES:
            if os.path.exists(pkl_file):
                print(f"\n{'='*80}")
                print(f"처리 시작: {pkl_file}")
                print(f"{'='*80}")
                process_pkl_file(pkl_file)
            else:
                print(f"⚠ 파일을 찾을 수 없습니다: {pkl_file}")
    else:
        print(f"알 수 없는 모드: {mode}")
        sys.exit(1)
