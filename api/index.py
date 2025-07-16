from flask import Flask, render_template, request, redirect, url_for, jsonify
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import requests
import logging
import os
from pymongo import MongoClient
from bson.objectid import ObjectId
from bson.errors import InvalidId


mongo_uri = "mongodb+srv://jtube0825:O6U6y8Jho2OZgv7C@cluster0.coc1ywm.mongodb.net/"
client = MongoClient(mongo_uri)
db = client["schoolmate"]
posts_collection = db["community_posts"]

def getMeal(date):
    """
    특정 날짜의 급식 정보를 가져오는 함수
    Args:
        date (str): YYYYMMDD 형식의 날짜
    Returns:
        list: 급식 메뉴 리스트 (첫 번째 요소는 날짜)
    """
    try:
        # NEIS API를 통해 급식 정보 조회
        response = requests.get(
            f"https://open.neis.go.kr/hub/mealServiceDietInfo?KEY=417cfd38cd41410091cd4bb11ee814d2&ATPT_OFCDC_SC_CODE=D10&SD_SCHUL_CODE=7240394&MLSV_YMD={date}",
            timeout=10
        )
        
        if response.status_code != 200:
            return ['급식 없음']
        
        # HTML 파싱하여 메뉴 추출
        soup = BeautifulSoup(response.text, 'html.parser')
        dish_element = soup.find("ddish_nm")
        
        if not dish_element:
            return ['급식 없음']
        
        # 메뉴 리스트 생성
        menuList = dish_element.text.split('<br/>')
        menuList2 = [i.split('(')[0].strip() for i in menuList if i.strip()]
        menuList2.insert(0, date)
        
        return menuList2
        
    except requests.exceptions.RequestException as e:
        logging.error(f"네트워크 요청 오류: {str(e)}")
        return ['급식 없음']
    except Exception as e:
        logging.error(f"급식 정보 파싱 오류: {str(e)}")
        return ['급식 없음']

def search_school(school_name):
    """
    학교명으로 학교 정보를 검색하는 함수
    Args:
        school_name (str): 검색할 학교명
    Returns:
        list: 학교 정보 리스트
    """
    try:
        response = requests.get(
            f"https://open.neis.go.kr/hub/schoolInfo?Type=json&SCHUL_NM={school_name}",
            timeout=10
        )
        
        if response.status_code != 200:
            return []
        
        data = response.json()
        
        if 'schoolInfo' not in data or len(data['schoolInfo']) < 2:
            return []
        
        schools = data['schoolInfo'][1].get('row', [])
        return schools
        
    except Exception as e:
        logging.error(f"학교 검색 오류: {str(e)}")
        return []

def get_week_range(date_str):
    """
    주어진 날짜의 주 범위 (월요일-금요일)를 반환하는 함수
    Args:
        date_str (str): YYYYMMDD 형식의 날짜
    Returns:
        tuple: (월요일, 금요일) YYYYMMDD 형식
    """
    try:
        date = datetime.strptime(date_str, '%Y%m%d')
        
        # 해당 주의 월요일 구하기
        monday = date - timedelta(days=date.weekday())
        
        # 해당 주의 금요일 구하기
        friday = monday + timedelta(days=4)
        
        return monday.strftime('%Y%m%d'), friday.strftime('%Y%m%d')
        
    except Exception as e:
        logging.error(f"주 범위 계산 오류: {str(e)}")
        return None, None

def get_timetable(atpt_code, school_code, grade, class_nm, semester, date_str):
    try:
        monday, friday = get_week_range(date_str)
        
        if not monday or not friday:
            return {'success': False, 'error': '날짜 처리 중 오류가 발생했습니다.'}
        
        response = requests.get(
            f"https://open.neis.go.kr/hub/hisTimetable?KEY=417cfd38cd41410091cd4bb11ee814d2&Type=json&pIndex=1&pSize=100&ATPT_OFCDC_SC_CODE={atpt_code}&SD_SCHUL_CODE={school_code}&TI_FROM_YMD={monday}&TI_TO_YMD={friday}&GRADE={grade}&CLASS_NM={class_nm}&SEM={semester}",
            timeout=10
        )
        
        if response.status_code != 200:
            return {'success': False, 'error': '시간표 조회에 실패했습니다.'}
        
        data = response.json()
        
        if 'hisTimetable' not in data or len(data['hisTimetable']) < 2:
            return {'success': False, 'error': '시간표 데이터를 찾을 수 없습니다.'}
        
        timetable_data = data['hisTimetable'][1].get('row', [])
        
        # 요일별로 시간표 정리
        organized_timetable = {}
        days = ['월', '화', '수', '목', '금']
        
        for item in timetable_data:
            date = item['ALL_TI_YMD']
            period = int(item['PERIO'])
            subject = item['ITRT_CNTNT']
            
            # 날짜를 요일로 변환
            date_obj = datetime.strptime(date, '%Y%m%d')
            day_index = date_obj.weekday()
            
            if day_index < 5:  # 월-금만 처리
                day_name = days[day_index]
                
                if day_name not in organized_timetable:
                    organized_timetable[day_name] = {}
                
                organized_timetable[day_name][period] = subject
        
        return {
            'success': True,
            'timetable': organized_timetable,
            'week_range': f"{monday[:4]}.{monday[4:6]}.{monday[6:8]} - {friday[:4]}.{friday[4:6]}.{friday[6:8]}"
        }
        
    except Exception as e:
        logging.error(f"시간표 조회 오류: {str(e)}")
        return {'success': False, 'error': f'시간표 조회 중 오류가 발생했습니다: {str(e)}'}

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# 로깅 설정
logging.basicConfig(level=logging.INFO)

# 기존 라우트들...
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/community', methods=['GET', 'POST'])
def community():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if title and content:
            post = {
                'title': title,
                'content': content,
                'timestamp': datetime.now()
            }
            posts_collection.insert_one(post)
            return redirect(url_for('community'))

    # 글 상세보기 (안전하게 처리)
    post_id = request.args.get('post_id')
    detail_post = None
    if post_id:
        try:
            detail_post = posts_collection.find_one({'_id': ObjectId(post_id)})
        except (InvalidId, Exception) as e:
            logging.error(f"Invalid ObjectId: {post_id} / {e}")
            detail_post = None

    posts = list(posts_collection.find().sort("timestamp", -1))
    return render_template('community.html', posts=posts, detail_post=detail_post)
@app.route('/get_meal', methods=['POST'])
def get_meal_api():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': '요청 데이터가 없습니다.'
            }), 400
        
        date = data.get('date')
        
        if not date:
            return jsonify({
                'success': False,
                'error': '날짜가 제공되지 않았습니다.'
            }), 400
        
        # 날짜 형식 검증 (YYYYMMDD)
        if len(date) != 8 or not date.isdigit():
            return jsonify({
                'success': False,
                'error': '올바른 날짜 형식이 아닙니다. (YYYYMMDD)'
            }), 400
        
        # 날짜 유효성 검증
        try:
            datetime.strptime(date, '%Y%m%d')
        except ValueError:
            return jsonify({
                'success': False,
                'error': '유효하지 않은 날짜입니다.'
            }), 400
        
        # getMeal 함수 호출
        meal_data = getMeal(date)
        
        if not meal_data or meal_data == ['급식 없음']:
            return jsonify({
                'success': True,
                'meal_data': [],
                'date': date,
                'message': '해당 날짜에는 급식이 제공되지 않습니다.'
            })
        
        return jsonify({
            'success': True,
            'meal_data': meal_data,
            'date': date
        })
        
    except Exception as e:
        logging.error(f"급식 조회 중 오류 발생: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'서버 오류가 발생했습니다: {str(e)}'
        }), 500

@app.route('/meal')
def meal():
    return render_template('meal.html')

@app.route('/resources')
def resources():
    return render_template('resources.html')

@app.route('/schedule')
def schedule():
    return render_template('schedule.html')

@app.route('/groups')
def groups():
    return render_template('groups.html')

@app.route('/seating')
def seating():
    return render_template('seating.html')

@app.route('/lottery')
def lottery():
    return render_template('lottery.html')

# 새로운 시간표 관련 라우트들
@app.route('/search_school', methods=['POST'])
def search_school_api():
    """학교 검색 API"""
    try:
        data = request.get_json()
        school_name = data.get('school_name', '').strip()
        
        if not school_name:
            return jsonify({
                'success': False,
                'error': '학교명을 입력해주세요.'
            }), 400
        
        schools = search_school(school_name)
        
        return jsonify({
            'success': True,
            'schools': schools
        })
        
    except Exception as e:
        logging.error(f"학교 검색 중 오류 발생: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'학교 검색 중 오류가 발생했습니다: {str(e)}'
        }), 500

@app.route('/get_timetable', methods=['POST'])
def get_timetable_api():
    """시간표 조회 API"""
    try:
        data = request.get_json()
        
        required_fields = ['atpt_code', 'school_code', 'grade', 'class_nm', 'semester', 'date']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'{field}이(가) 누락되었습니다.'
                }), 400
        
        result = get_timetable(
            data['atpt_code'],
            data['school_code'],
            data['grade'],
            data['class_nm'],
            data['semester'],
            data['date']
        )
        
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"시간표 조회 중 오류 발생: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'시간표 조회 중 오류가 발생했습니다: {str(e)}'
        }), 500
