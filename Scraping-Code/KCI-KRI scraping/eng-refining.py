"""
결측치만 채우기 스크립트
- PKL 파일에서 kri_num, gender, birth가 누락된 행만 찾기
- KCI에서 article-id로 CRT ID와 KRI ID 추출
- KRI에서 연구자 정보 (생년, 성별) 수집
- 기존에 채워진 데이터는 건드리지 않음
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
    """
    profile_url = f'https://www.kci.go.kr/kciportal/po/citationindex/poCretDetail.kci?citationBean.cretId={cret_id}&citationBean.artiId={arti_id}'
    
    try:
        driver.get(profile_url)
        time.sleep(uniform(1.5, 2))
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # hidden input에서 KRI ID 추출
        kri_input = soup.find('input', {'id': 'citationBean.kriCretId'})
        if kri_input and kri_input.get('value'):
            kri_id = kri_input.get('value')
            if kri_id and kri_id.strip() and kri_id != '':
                return kri_id.strip()
        
        kri_input = soup.find('input', {'name': 'citationBean.kriCretId'})
        if kri_input and kri_input.get('value'):
            kri_id = kri_input.get('value')
            if kri_id and kri_id.strip() and kri_id != '':
                return kri_id.strip()
        
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
    KCI 논문 상세페이지에서 1저자의 CRT ID와 KRI 연구자번호 추출
    """
    url = f'https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId={article_id}'
    
    try:
        driver.get(url)
        time.sleep(uniform(1, 2))
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        title_elem = soup.find('div', class_='tit-area')
        title = title_elem.get_text(strip=True) if title_elem else "제목 없음"
        
        # 1저자 정보 찾기
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
        
        first_author = author_elements[0]
        author_name = first_author.get_text(strip=True)
        
        href = first_author.get('href')
        cret_id = None
        extracted_arti_id = None
        
        if 'citationBean.cretId=' in href:
            cret_id_match = re.search(r'cretId=([^&\'\"]+)', href)
            if cret_id_match:
                cret_id = cret_id_match.group(1)
            
            arti_id_match = re.search(r'artiId=([^&\'\"]+)', href)
            if arti_id_match:
                extracted_arti_id = arti_id_match.group(1)
        
        final_arti_id = extracted_arti_id if extracted_arti_id else article_id
        
        # 저자 프로필에서 KRI ID 추출
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
    """KCI 사이트 로그인"""
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
            # ID 입력란이 클릭 가능할 때까지 대기
            id_input = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "uid"))
            )
            print(f"  ID 입력란 발견")
            
            # JavaScript로 직접 값 설정
            driver.execute_script("arguments[0].value = '';", id_input)
            time.sleep(0.5)
            id_input.send_keys(KCI_LOGIN_INFO["loginBean.membId"])
            print(f"  ID 입력 완료: {KCI_LOGIN_INFO['loginBean.membId']}")
            
            # PW 입력란도 클릭 가능할 때까지 대기
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
    """KRI 사이트 로그인 및 iframe 준비"""
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
        
        # 검색 전 입력값 확인
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
                        inp.clear()
                        time.sleep(0.2)
                        inp.send_keys(korean_name)
                        time.sleep(0.2)
                        print(f"        → 보이는 입력란에 '{korean_name}' 입력 완료")
                        break
                else:
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
        
        # 소속대학/기관 (HideCol0C8) - 헤더 제외하고 데이터만
        univ_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C8' in x)
        for cell in univ_cells:
            text = cell.get_text(strip=True)
            if text and text != '소속대학/기관':
                result['univ'] = text
                break
        else:
            result['univ'] = None
        
        # 부서 (HideCol0C9) - 헤더 제외하고 데이터만
        department_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C9' in x)
        for cell in department_cells:
            text = cell.get_text(strip=True)
            if text and text != '소속학과':
                result['department'] = text
                break
        else:
            result['department'] = None
        
        # 직급 (HideCol0C10) - 헤더 제외하고 데이터만
        job_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C10' in x)
        for cell in job_cells:
            text = cell.get_text(strip=True)
            if text and text != '직급':
                result['job'] = text
                break
        else:
            result['job'] = None
        
        # 전공분야 (HideCol0C11) - 헤더 제외하고 데이터만
        major_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C11' in x)
        for cell in major_cells:
            text = cell.get_text(strip=True)
            if text and text != '전공분야(세부전공명)':
                result['major'] = text
                break
        else:
            result['major'] = None
        
        # 출신학교 (HideCol0C12) - 헤더 제외하고 데이터만
        grad_cells = soup.find_all('td', class_=lambda x: x and 'HideCol0C12' in x)
        for cell in grad_cells:
            text = cell.get_text(strip=True)
            if text and text != '출신학교':
                result['grad'] = text
                break
        else:
            result['grad'] = None
        
        # 취득학위 (HideCol0C13) - 헤더 제외하고 데이터만
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


def fill_missing_data():
    """결측치만 채우기"""
    print("\n" + "="*70)
    print("결측치 데이터 채우기")
    print("="*70)
    
    # PKL 파일 로드
    pkl_path = 'data/250602_영어영문_토큰화.pkl'
    
    if not os.path.exists(pkl_path):
        print(f"파일을 찾을 수 없습니다: {pkl_path}")
        return
    
    print(f"PKL 파일 로드: {pkl_path}")
    df = pd.read_pickle(pkl_path)
    
    # 필요한 컬럼이 없으면 생성
    if 'kri_num' not in df.columns:
        df['kri_num'] = None
    if 'crt_id' not in df.columns:
        df['crt_id'] = None
    if 'author_name_kor' not in df.columns:
        df['author_name_kor'] = None
    if 'gender' not in df.columns:
        df['gender'] = None
    if 'birth' not in df.columns:
        df['birth'] = None
    if 'univ' not in df.columns:
        df['univ'] = None
    if 'department' not in df.columns:
        df['department'] = None
    if 'job' not in df.columns:
        df['job'] = None
    if 'major' not in df.columns:
        df['major'] = None
    if 'grad' not in df.columns:
        df['grad'] = None
    if 'diploma' not in df.columns:
        df['diploma'] = None
    
    print(f"\n전체 행 수: {len(df)}")
    print(f"kri_num 누락: {df['kri_num'].isna().sum()}개")
    print(f"gender 누락: {df['gender'].isna().sum()}개")
    print(f"birth 누락: {df['birth'].isna().sum()}개")
    
    # 결측치만 필터링 (모두 비어있으므로 전체 처리)
    missing_df = df[df['kri_num'].isna() | df['gender'].isna() | df['birth'].isna()].copy()
    print(f"\n처리할 행 수: {len(missing_df)}개")
    
    if len(missing_df) == 0:
        print("처리할 결측치가 없습니다!")
        return
    
    # 드라이버 설정
    driver = setup_driver()  # KRI용
    kci_driver = None  # KCI용
    
    try:
        # KCI 로그인
        kci_driver = setup_driver()
        if not login_kci(kci_driver):
            print("KCI 로그인 실패")
            kci_driver.quit()
            driver.quit()
            return
        
        # KRI 로그인
        login_success, kri_driver = login_kri(driver)
        if not login_success:
            print("KRI 로그인 실패")
            if kci_driver:
                kci_driver.quit()
            driver.quit()
            return
        
        results = []
        
        # 각 결측치 처리
        for idx, row in tqdm(missing_df.iterrows(), total=len(missing_df), desc="데이터 수집"):
            article_id = row['article-id']
            current_kri = row['kri_num']
            
            result_row = {
                'article-id': article_id,
                'original_kri_num': current_kri,
                'new_kri_num': None,
                'crt_id': None,
                'author_name': None,
                'author_name_kor': None,
                'birth': None,
                'gender': None,
                'univ': None,
                'department': None,
                'job': None,
                'major': None,
                'grad': None,
                'diploma': None,
                'status': 'pending'
            }
            
            try:
                # KRI ID가 없는 경우만 KCI에서 가져오기
                if pd.isna(current_kri):
                    print(f"\n[{idx}] Article {article_id}: CRT ID 및 KRI ID 수집 중...")
                    author_info = get_author_kri_info_from_kci(kci_driver, article_id)
                    
                    if author_info['status'] == '저자 정보 없음':
                        print(f"    저자 정보 없음")
                        result_row['status'] = 'no_author'
                        results.append(result_row)
                        continue
                    
                    result_row['crt_id'] = author_info['cret_id']
                    result_row['author_name'] = author_info['author_name']
                    
                    # KCI에서 가져온 이름을 한글만 추출
                    if author_info['author_name']:
                        korean_name = author_info['author_name'].split('\n')[0].strip()
                        korean_name = korean_name.split('/')[0].strip()
                        result_row['author_name_kor'] = korean_name
                    
                    if not author_info['kri_id']:
                        print(f"    KRI ID 없음 (CRT ID와 이름만 저장)")
                        result_row['status'] = 'no_kri_id'
                        
                        # CRT ID와 이름 저장
                        if pd.notna(result_row['crt_id']):
                            df.loc[idx, 'crt_id'] = result_row['crt_id']
                        if pd.notna(result_row['author_name_kor']):
                            df.loc[idx, 'author_name_kor'] = result_row['author_name_kor']
                        
                        if pd.notna(result_row['crt_id']) or pd.notna(result_row['author_name_kor']):
                            df.to_pickle(pkl_path)
                            print(f"    ✅ CRT ID와 이름 저장 완료 (idx={idx})")
                        
                        results.append(result_row)
                        time.sleep(uniform(2, 3))
                        continue
                    
                    kri_id = author_info['kri_id']
                    result_row['new_kri_num'] = kri_id
                    print(f"    CRT={author_info['cret_id']}, 저자={author_info['author_name']}, KRI={kri_id}")
                else:
                    # 이미 kri_num이 있는 경우
                    kri_id = str(int(current_kri))
                    result_row['new_kri_num'] = kri_id
                    print(f"\n[{idx}] Article {article_id}: 기존 KRI ID={kri_id} 사용")
                
                # KRI에서 연구자 정보 수집
                print(f"    KRI ID {kri_id}로 생년/성별 수집 중...")
                researcher_info = search_researcher_by_kri_id(driver, kri_id, result_row.get('author_name'))
                
                if researcher_info:
                    # 한글 이름만 추출 (영어 표기 제외)
                    if researcher_info.get('name'):
                        korean_name = researcher_info['name'].split('\n')[0].strip()
                        korean_name = korean_name.split('/')[0].strip()
                        result_row['author_name_kor'] = korean_name
                    
                    result_row['birth'] = researcher_info.get('birth')
                    result_row['gender'] = researcher_info.get('gender')
                    result_row['univ'] = researcher_info.get('univ')
                    result_row['department'] = researcher_info.get('department')
                    result_row['job'] = researcher_info.get('job')
                    result_row['major'] = researcher_info.get('major')
                    result_row['grad'] = researcher_info.get('grad')
                    result_row['diploma'] = researcher_info.get('diploma')
                    result_row['status'] = 'success'
                    
                    # 즉시 원본 DataFrame에 반영
                    if pd.notna(result_row['new_kri_num']):
                        df.loc[idx, 'kri_num'] = result_row['new_kri_num']
                    if pd.notna(result_row['crt_id']):
                        df.loc[idx, 'crt_id'] = result_row['crt_id']
                    if pd.notna(result_row['author_name_kor']):
                        df.loc[idx, 'author_name_kor'] = result_row['author_name_kor']
                    if pd.notna(result_row['birth']):
                        df.loc[idx, 'birth'] = result_row['birth']
                    if pd.notna(result_row['gender']):
                        df.loc[idx, 'gender'] = result_row['gender']
                    if pd.notna(result_row['univ']):
                        df.loc[idx, 'univ'] = result_row['univ']
                    if pd.notna(result_row['department']):
                        df.loc[idx, 'department'] = result_row['department']
                    if pd.notna(result_row['job']):
                        df.loc[idx, 'job'] = result_row['job']
                    if pd.notna(result_row['major']):
                        df.loc[idx, 'major'] = result_row['major']
                    if pd.notna(result_row['grad']):
                        df.loc[idx, 'grad'] = result_row['grad']
                    if pd.notna(result_row['diploma']):
                        df.loc[idx, 'diploma'] = result_row['diploma']
                    
                    # 즉시 PKL 파일에 저장
                    df.to_pickle(pkl_path)
                    print(f"    ✅ 즉시 저장 완료 (idx={idx})")
                else:
                    result_row['status'] = 'no_researcher_info'
                
                results.append(result_row)
                
                # 10개마다 중간 CSV 저장 및 백업
                if len(results) % 10 == 0:
                    os.makedirs('revise_data', exist_ok=True)
                    temp_df = pd.DataFrame(results)
                    temp_df.to_csv(f'revise_data/fill_missing_temp_{len(results)}.csv', index=False, encoding='utf-8-sig')
                    
                    # 백업 PKL도 저장
                    backup_pkl = f'revise_data/backup_진행중_{len(results)}.pkl'
                    df.to_pickle(backup_pkl)
                    print(f"\n  → 중간 저장 완료: {len(results)}개 처리, 백업: {backup_pkl}")
                
                time.sleep(uniform(2, 3))
                
            except Exception as e:
                print(f"    오류 발생: {e}")
                result_row['status'] = f'error: {str(e)}'
                results.append(result_row)
                continue
        
        # 최종 결과 저장
        os.makedirs('revise_data', exist_ok=True)
        results_df = pd.DataFrame(results)
        results_df.to_csv('revise_data/fill_missing_results.csv', index=False, encoding='utf-8-sig')
        print(f"\n최종 결과 CSV 저장: revise_data/fill_missing_results.csv")
        
        # 최종 PKL 파일도 저장 (이미 즉시 저장되었지만 확실하게)
        print(f"\n최종 PKL 파일 저장: {pkl_path}")
        df.to_pickle(pkl_path)
        
        # CSV도 업데이트
        csv_path = pkl_path.replace('.pkl', '.csv')
        if os.path.exists(csv_path):
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"최종 CSV 파일 저장: {csv_path}")
        
        # 백업 저장
        backup_pkl = 'revise_data/250602_영어영문_filled.pkl'
        backup_csv = 'revise_data/250602_영어영문_filled.csv'
        df.to_pickle(backup_pkl)
        df.to_csv(backup_csv, index=False, encoding='utf-8-sig')
        print(f"백업 파일 저장: {backup_pkl}")
        print(f"백업 파일 저장: {backup_csv}")
        
        # 통계 출력
        print("\n" + "="*70)
        print("수집 결과 통계")
        print("="*70)
        print(results_df['status'].value_counts())
        
        print("\n" + "="*70)
        print("최종 결측치 현황")
        print("="*70)
        print(f"kri_num 누락: {df['kri_num'].isna().sum()}개")
        print(f"birth 누락: {df['birth'].isna().sum()}개")
        print(f"gender 누락: {df['gender'].isna().sum()}개")
        
    finally:
        driver.quit()
        if kci_driver:
            kci_driver.quit()


if __name__ == "__main__":
    fill_missing_data()
