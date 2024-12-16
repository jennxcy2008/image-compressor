from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
import re
import os
from datetime import timedelta

app = FastAPI()

# 静态文件和模板配置
app.mount("/static", StaticFiles(directory="static_files"), name="static")
app.mount("/videos", StaticFiles(directory="videos"), name="videos")
templates = Jinja2Templates(directory="templates")

# 视频保存目录
VIDEOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'videos')
os.makedirs(VIDEOS_DIR, exist_ok=True)

class VideoURL(BaseModel):
    url: str

def get_real_url(short_url):
    """解析B站短链接获取真实URL"""
    response = requests.get(short_url, allow_redirects=True)
    return response.url

def get_bili_video_info(bv_id):
    """获取B站视频信息"""
    api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    response = requests.get(api_url, headers=headers)
    data = response.json()
    
    if data['code'] != 0:
        raise Exception(f"获取视频信息失败：{data['message']}")
    
    video_data = data['data']
    return {
        'title': video_data['title'],
        'author': video_data['owner']['name'],
        'description': video_data['desc'],
        'duration': video_data['duration'],
        'cid': video_data['cid']  # 添加cid
    }

def download_bili_video(bv_id, output_path, video_info):
    """下载B站视频"""
    try:
        # 获取视频下载地址
        api_url = f"https://api.bilibili.com/x/player/playurl?bvid={bv_id}&cid={video_info['cid']}&qn=80"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': f'https://www.bilibili.com/video/{bv_id}'
        }
        response = requests.get(api_url, headers=headers)
        data = response.json()
        
        if data['code'] != 0:
            raise Exception(f"获取下载地址失败：{data['message']}")
        
        # 获取视频URL
        video_url = data['data']['durl'][0]['url']
        
        # 下载视频
        print(f"开始下载视频: {video_info['title']}")
        video_response = requests.get(video_url, headers=headers, stream=True)
        file_path = os.path.join(output_path, f"{video_info['title']}.mp4")
        
        with open(file_path, 'wb') as f:
            for chunk in video_response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        print(f"视频下载完成: {file_path}")
        return True
        
    except Exception as e:
        print(f"下载出错: {str(e)}")
        raise Exception(f"下载出错: {str(e)}")

@app.get("/")
async def home(request: Request):
    # 获取已下载视频列表
    videos = []
    for filename in os.listdir(VIDEOS_DIR):
        if filename.endswith(('.mp4', '.flv')):
            video_path = os.path.join(VIDEOS_DIR, filename)
            video_size = os.path.getsize(video_path) / (1024*1024)
            videos.append({
                'filename': filename,
                'path': video_path,
                'size': f"{video_size:.2f} MB"
            })
    return templates.TemplateResponse("index.html", {"request": request, "videos": videos})

@app.post("/download")
async def download_video(video: VideoURL):
    try:
        print(f"尝试下载视频: {video.url}")
        
        # 处理短链接
        if 'b23.tv' in video.url:
            real_url = get_real_url(video.url)
            print(f"解析短链接: {real_url}")
        else:
            real_url = video.url
        
        # 从URL中提取BV号
        bv_match = re.search(r'BV\w+', real_url)
        if not bv_match:
            raise Exception("请输入正确的B站视频链接")
        
        bv_id = bv_match.group()
        print(f"识别到BV号: {bv_id}")
        
        # 获取视频信息
        video_info = get_bili_video_info(bv_id)
        print(f"获取到视频信息: {video_info}")
        
        # 下载视频
        print(f"开始下载到: {VIDEOS_DIR}")
        download_bili_video(bv_id, VIDEOS_DIR, video_info)
        
        # 获取文件大小
        output_path = os.path.join(VIDEOS_DIR, f"{video_info['title']}.mp4")
        file_size = os.path.getsize(output_path) / (1024*1024)
        video_info['size'] = f"{file_size:.2f} MB"
        
        return JSONResponse({
            'success': True,
            'video_info': video_info,
            'message': '下载成功！'
        })
    except Exception as e:
        error_message = str(e)
        print(f"下载失败: {error_message}")
        raise HTTPException(status_code=400, detail=error_message)