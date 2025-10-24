from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

app = Flask(__name__)
CORS(app)

@app.route('/health', methods=['GET'])
def health():
    """서버 상태 확인"""
    return jsonify({
        'status': 'ok', 
        'message': '네이버 블로그 트래커 API 서버가 정상 작동 중입니다.',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/visitor-stats/<blog_id>', methods=['GET'])
def get_visitor_stats(blog_id):
    """
    네이버 블로그의 방문자 통계 가져오기
    NVisitorgp4Ajax.nhn API 사용
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': f'https://blog.naver.com/{blog_id}',
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        # 네이버 방문자 통계 Ajax API
        visitor_url = f'https://blog.naver.com/NVisitorgp4Ajax.nhn?blogId={blog_id}'
        
        response = requests.get(visitor_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # HTML 파싱
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 방문자 데이터 추출
        visitor_stats = []
        
        # 방법 1: JavaScript 변수에서 데이터 추출 (가장 확실)
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # aVisitor 배열 찾기 - 네이버 블로그가 사용하는 변수명
                match = re.search(r'aVisitor\s*=\s*\[([^\]]+)\]', script.string)
                if match:
                    try:
                        numbers_str = match.group(1)
                        # 쉼표로 구분된 숫자들 파싱
                        numbers = [int(x.strip()) for x in numbers_str.split(',') if x.strip().replace('-', '').isdigit()]
                        
                        if numbers:
                            visitor_stats = format_visitor_array(numbers)
                            break
                    except Exception as e:
                        print(f"aVisitor 파싱 실패: {e}")
                        continue
                
                # 다른 변수명 시도 (visitor, visitorCnt 등)
                match = re.search(r'var\s+(visitor\w*|aVisit\w*)\s*=\s*\[([^\]]+)\]', script.string, re.IGNORECASE)
                if match and not visitor_stats:
                    try:
                        numbers_str = match.group(2)
                        numbers = [int(x.strip()) for x in numbers_str.split(',') if x.strip().replace('-', '').isdigit()]
                        
                        if numbers:
                            visitor_stats = format_visitor_array(numbers)
                            break
                    except:
                        continue
        
        # 방법 2: HTML에서 직접 숫자 추출 (fallback)
        if not visitor_stats:
            # 모든 텍스트에서 숫자 패턴 찾기
            all_text = soup.get_text()
            number_pattern = re.findall(r'\d+', all_text)
            if number_pattern:
                # 방문자 수로 보이는 숫자들 (보통 0~10000 사이)
                numbers = [int(n) for n in number_pattern if 0 <= int(n) <= 10000]
                if len(numbers) >= 5:
                    visitor_stats = format_visitor_array(numbers[-5:])
        
        if visitor_stats:
            return jsonify({
                'blog_id': blog_id,
                'stats': visitor_stats,
                'success': True
            })
        else:
            return jsonify({
                'blog_id': blog_id,
                'stats': [],
                'success': False,
                'message': '방문자 데이터를 찾을 수 없습니다. 방문자 그래프 위젯이 활성화되어 있는지 확인하세요.'
            })
        
    except requests.exceptions.RequestException as e:
        return jsonify({
            'error': f'네트워크 오류: {str(e)}',
            'blog_id': blog_id,
            'stats': [],
            'success': False
        }), 500
    except Exception as e:
        return jsonify({
            'error': f'방문자 통계를 가져올 수 없습니다: {str(e)}',
            'blog_id': blog_id,
            'stats': [],
            'success': False
        }), 500


def format_visitor_array(numbers):
    """숫자 배열을 방문자 통계 포맷으로 변환"""
    stats = []
    today = datetime.now()
    
    # 최근 5개 데이터 사용 (또는 전체)
    recent_numbers = numbers[-5:] if len(numbers) > 5 else numbers
    
    for i, count in enumerate(recent_numbers):
        # 오늘부터 역순으로 날짜 계산
        days_ago = len(recent_numbers) - 1 - i
        date = (today - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        
        stats.append({
            'date': date,
            'visitors': int(count) if isinstance(count, (int, float)) else 0
        })
    
    return stats


@app.route('/api/recent-posts/<blog_id>', methods=['GET'])
def get_recent_posts(blog_id):
    """네이버 블로그의 최신 게시글 가져오기 (RSS 피드 사용)"""
    try:
        limit = request.args.get('limit', 5, type=int)
        limit = min(limit, 20)
        
        rss_url = f'https://rss.blog.naver.com/{blog_id}.xml'
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(rss_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        
        posts = []
        items = root.findall('.//item')[:limit]
        
        if not items:
            return jsonify({
                'blog_id': blog_id,
                'posts': [],
                'message': 'RSS 피드에서 게시글을 찾을 수 없습니다.',
                'success': False
            }), 404
        
        for item in items:
            try:
                title_elem = item.find('title')
                link_elem = item.find('link')
                date_elem = item.find('pubDate')
                
                if title_elem is not None and link_elem is not None:
                    title = title_elem.text or ''
                    url = link_elem.text or ''
                    
                    if date_elem is not None and date_elem.text:
                        try:
                            date_str = date_elem.text
                            date_parts = date_str.split()
                            if len(date_parts) >= 4:
                                date_formatted = f"{date_parts[1]} {date_parts[2]} {date_parts[3]}"
                            else:
                                date_formatted = date_str[:16]
                        except:
                            date_formatted = date_elem.text[:16]
                    else:
                        date_formatted = 'Unknown'
                    
                    posts.append({
                        'title': title,
                        'url': url,
                        'date': date_formatted
                    })
            except Exception as e:
                continue
        
        return jsonify({
            'blog_id': blog_id,
            'posts': posts,
            'success': True
        })
        
    except requests.exceptions.RequestException as e:
        return jsonify({
            'error': f'네트워크 오류: {str(e)}',
            'blog_id': blog_id,
            'success': False
        }), 500
    except Exception as e:
        return jsonify({
            'error': f'게시글을 가져올 수 없습니다: {str(e)}',
            'blog_id': blog_id,
            'success': False
        }), 500


@app.route('/api/check-exposure', methods=['POST'])
def check_exposure():
    """
    게시글이 네이버 VIEW 탭에 노출되는지 확인
    section.blog.naver.com에서 정확한 제목 매칭으로 확인
    """
    try:
        data = request.get_json()
        blog_id = data.get('blog_id')
        post_title = data.get('post_title')
        post_url = data.get('post_url')
        
        if not all([blog_id, post_title, post_url]):
            return jsonify({'error': '필수 파라미터가 누락되었습니다.'}), 400
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9',
            'Referer': 'https://section.blog.naver.com/'
        }
        
        exposed = False
        post_title_clean = post_title.strip()
        post_number = post_url.split('/')[-1]
        
        # 방법 1: section.blog.naver.com VIEW 탭 전체 목록에서 확인
        try:
            view_url = 'https://section.blog.naver.com/BlogHome.naver?directoryNo=0&currentPage=1&groupId=0'
            
            response = requests.get(view_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 모든 링크와 텍스트에서 제목 찾기
            all_elements = soup.find_all(['a', 'div', 'span', 'h3', 'h4', 'p', 'strong'])
            
            for element in all_elements:
                element_text = element.get_text(strip=True)
                
                # 정확한 제목 매칭
                if element_text == post_title_clean:
                    # 해당 요소나 부모에서 링크 확인
                    link = element if element.name == 'a' else element.find_parent('a')
                    if link:
                        href = link.get('href', '')
                        # 블로그 ID와 게시글 번호 확인
                        if blog_id in href and post_number in href:
                            exposed = True
                            print(f"✓ VIEW 탭에서 발견: {post_title[:30]}...")
                            break
                
                # 부분 매칭 (제목이 포함되고 너무 길지 않은 경우)
                elif post_title_clean in element_text:
                    # 제목 길이의 1.5배를 넘지 않으면 같은 글로 판단
                    if len(element_text) <= len(post_title_clean) * 1.5:
                        link = element if element.name == 'a' else element.find_parent('a')
                        if link:
                            href = link.get('href', '')
                            if blog_id in href and post_number in href:
                                exposed = True
                                print(f"✓ VIEW 탭에서 발견 (부분매칭): {post_title[:30]}...")
                                break
        
        except Exception as e:
            print(f"VIEW 탭 확인 중 오류: {e}")
        
        # 방법 2: 네이버 VIEW 탭 검색으로 확인 (백업)
        if not exposed:
            try:
                # 제목과 블로그 ID로 검색
                search_query = f"{post_title} {blog_id}"
                search_url = f"https://search.naver.com/search.naver?where=view&query={requests.utils.quote(search_query)}"
                
                search_response = requests.get(search_url, headers=headers, timeout=10)
                search_soup = BeautifulSoup(search_response.text, 'html.parser')
                
                # 검색 결과의 모든 요소 확인
                all_elements = search_soup.find_all(['a', 'div', 'span', 'strong'])
                
                for element in all_elements:
                    href = element.get('href', '') if element.name == 'a' else ''
                    text = element.get_text(strip=True)
                    
                    # URL에 블로그 ID와 게시글 번호가 모두 있는 경우
                    if blog_id in href and post_number in href:
                        exposed = True
                        print(f"✓ VIEW 검색에서 발견: {post_title[:30]}...")
                        break
                    
                    # 제목이 정확히 일치하고 관련 링크가 있는 경우
                    if text == post_title_clean:
                        parent = element.find_parent('a')
                        if parent:
                            parent_href = parent.get('href', '')
                            if blog_id in parent_href:
                                exposed = True
                                print(f"✓ VIEW 검색에서 발견 (제목매칭): {post_title[:30]}...")
                                break
            
            except Exception as e:
                print(f"VIEW 검색 중 오류: {e}")
        
        # 결과 반환
        if not exposed:
            print(f"✗ 누락됨: {post_title[:30]}...")
        
        return jsonify({
            'blog_id': blog_id,
            'post_title': post_title,
            'post_url': post_url,
            'exposed': exposed,
            'checked_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"검색 확인 중 치명적 오류: {e}")
        return jsonify({
            'error': f'검색 확인 중 오류: {str(e)}',
            'exposed': None
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
