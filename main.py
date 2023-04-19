from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage, AudioMessage
)
import os
import uuid
import time

from src.models import OpenAIModel
from src.memory import Memory
from src.logger import logger
from src.storage import Storage, MongoStorage
from src.utils import get_role_and_content
from src.service.youtube import Youtube, YoutubeTranscriptReader
from src.service.website import Website, WebsiteReader
from src.mongodb import mongodb

load_dotenv('.env')

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
storage = None
youtube = Youtube(step=4)
website = Website()
last_message_time = {}
question_count = {}


memory = Memory(system_message=os.getenv('SYSTEM_MESSAGE'), memory_message_count=2)
model_management = {}
api_keys = {}


@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)
    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    logger.info(f'{user_id}: {text}')

    try:
        #使用者第一次註冊，給一個隨機key用來註冊會員
        if not storage.IsInDatabase(user_id):
            #logger.info('FirstTimeUse')
            api_key = str(uuid.uuid4())
            logger.info(f'{user_id}: {api_key}')
            storage.save({
                user_id: api_key
            })
        #限制非會員的訊息頻率
        if not storage.GetMember(user_id):
            #logger.info('Not Member')
            # 檢查使用者問題數量
            if user_id not in question_count:
                question_count[user_id] = 0
            if question_count[user_id] < 5:
                question_count[user_id] += 1
                if question_count[user_id] == 5:
                    last_message_time[user_id] = time.time()
            else:
                if user_id in last_message_time and time.time() - last_message_time[user_id] < 60:
                    raise Exception('您已經問了5個問題，請一分鐘後再試，加入會員以享用無限制使用體驗')
                else:
                    question_count[user_id] = 1

        #升級為付費會員
        if text.startswith('/註冊'):
            logger.info('註冊')
            key = text.strip()
            if storage.GetMember(user_id):
                raise Exception("已註冊會員")
            if key == storage.GetUserAPIKey(user_id):
                storage.SetMember(user_id)
            else:
                raise ValueError("Invalid token")
            msg = TextSendMessage(text='Token 有效，註冊成功')

        #取得會員的註冊key
        elif text.startswith('/GetKey'):
            logger.info('/GetKey')
            if user_id == os.getenv('ADMIN'):
                find_user = text.strip(" ")[1]
                userKey = storage.GetUserAPIKey(find_user)
                logger.info("Enter: "+find_user)
                logger.info("Key: "+userKey)
                if userKey != "Error":
                    return_message = userKey
                else:
                    return_message = 'User not found'
            else:
                raise KeyError('User auth error')
            msg = TextSendMessage(text=return_message)
        
        elif text.startswith('/我的id'):
            msg = TextSendMessage(text=user_id)
        #刪除會員   
        elif text.startswith('/DeleteUser'):
            logger.info('DeleteUser')
            if user_id == os.getenv('ADMIN'):
                user = text.strip()
                if storage.GetMember(user):
                    storage.DeleteMember(user)
                else:
                    raise Exception('Member not found')
            else:
                
                raise KeyError('User auth error')

        elif text.startswith('/指令說明'):
            #logger.info('指令說明')
            msg = TextSendMessage(text="指令：\n/註冊 + API Token\n👉 API Token 請先到 https://platform.openai.com/ 註冊登入後取得\n\n/系統訊息 + Prompt\n👉 Prompt 可以命令機器人扮演某個角色，例如：請你扮演擅長做總結的人\n\n/清除\n👉 當前每一次都會紀錄最後兩筆歷史紀錄，這個指令能夠清除歷史訊息\n\n/圖像 + Prompt\n👉 會調用 DALL∙E 2 Model，以文字生成圖像\n\n語音輸入\n👉 會調用 Whisper 模型，先將語音轉換成文字，再調用 ChatGPT 以文字回覆\n\n其他文字輸入\n👉 調用 ChatGPT 以文字回覆")
        
        #elif text.startswith('/系統訊息'):
            #logger.info('系統訊息')
            #memory.change_system_message(user_id, text[5:].strip())
            #msg = TextSendMessage(text='輸入成功')

        elif text.startswith('/清除'):
            #logger.info('清除')
            memory.remove(user_id)
            msg = TextSendMessage(text='歷史訊息清除成功')
        

        #elif text.startswith('/圖像'):
        #    prompt = text[3:].strip()
        #    memory.append(user_id, 'user', prompt)
        #    is_successful, response, error_message = model_management[0].image_generations(prompt)
        #    if not is_successful:
        #        raise Exception(error_message)
        #    url = response['data'][0]['url']
        #    msg = ImageSendMessage(
        #        original_content_url=url,
        #        preview_image_url=url
        #    )
        #    memory.append(user_id, 'assistant', url)

        else:
            #logger.info('else')
            user_model = model_management[0]
            memory.append(user_id, 'user', text)
            url = website.get_url_from_text(text)
            if url:
                if youtube.retrieve_video_id(text):
                    is_successful, chunks, error_message = youtube.get_transcript_chunks(youtube.retrieve_video_id(text))
                    if not is_successful:
                        raise Exception(error_message)
                    youtube_transcript_reader = YoutubeTranscriptReader(user_model, os.getenv('OPENAI_MODEL_ENGINE'))
                    is_successful, response, error_message = youtube_transcript_reader.summarize(chunks)
                    if not is_successful:
                        raise Exception(error_message)
                    role, response = get_role_and_content(response)
                    msg = TextSendMessage(text=response)
                else:
                    chunks = website.get_content_from_url(url)
                    if len(chunks) == 0:
                        raise Exception('無法撈取此網站文字')
                    website_reader = WebsiteReader(user_model, os.getenv('OPENAI_MODEL_ENGINE'))
                    is_successful, response, error_message = website_reader.summarize(chunks)
                    if not is_successful:
                        raise Exception(error_message)
                    role, response = get_role_and_content(response)
                    msg = TextSendMessage(text=response)
            else:
                is_successful, response, error_message = user_model.chat_completions(memory.get(user_id), os.getenv('OPENAI_MODEL_ENGINE'))
                if not is_successful:
                    raise Exception(error_message)
                role, response = get_role_and_content(response)
                msg = TextSendMessage(text=response)
            memory.append(user_id, role, response)
    except ValueError:
        msg = TextSendMessage(text='Token 無效，請重新輸入')
    except KeyError:
        msg = TextSendMessage(text='權限無效')
    except Exception as e:
        memory.remove(user_id)
        if str(e).startswith('Incorrect API key provided'):
            msg = TextSendMessage(text='OpenAI API Token 有誤，請重新註冊。')
        elif str(e).startswith('That model is currently overloaded with other requests.'):
            msg = TextSendMessage(text='已超過負荷，請稍後再試')
        else:
            msg = TextSendMessage(text='伺服器發生問題，請稍後再試，或聯繫管理員')
    line_bot_api.reply_message(event.reply_token, msg)

'''
@handler.add(MessageEvent, message=AudioMessage)
def handle_audio_message(event):
    user_id = event.source.user_id
    audio_content = line_bot_api.get_message_content(event.message.id)
    input_audio_path = f'{str(uuid.uuid4())}.m4a'
    with open(input_audio_path, 'wb') as fd:
        for chunk in audio_content.iter_content():
            fd.write(chunk)

    try:
        if not model_management.get(0):
            raise ValueError('Invalid API token')
        else:
            is_successful, response, error_message = model_management[0].audio_transcriptions(input_audio_path, 'whisper-1')
            if not is_successful:
                raise Exception(error_message)
            memory.append(user_id, 'user', response['text'])
            is_successful, response, error_message = model_management[0].chat_completions(memory.get(user_id), 'gpt-3.5-turbo')
            if not is_successful:
                raise Exception(error_message)
            role, response = get_role_and_content(response)
            memory.append(user_id, role, response)
            msg = TextSendMessage(text=response)
    except ValueError:
        msg = TextSendMessage(text='請先註冊你的 API Token，格式為 /註冊 [API TOKEN]')
    except KeyError:
        msg = TextSendMessage(text='請先註冊 Token，格式為 /註冊 sk-xxxxx')
    except Exception as e:
        memory.remove(user_id)
        if str(e).startswith('Incorrect API key provided'):
            msg = TextSendMessage(text='OpenAI API Token 有誤，請重新註冊。')
        else:
            msg = TextSendMessage(text=str(e))
    os.remove(input_audio_path)
    line_bot_api.reply_message(event.reply_token, msg)
'''

@app.route("/", methods=['GET'])
def home():
    return 'Hello World'


if __name__ == "__main__":
    mongodb.connect_to_database()
    storage = Storage(MongoStorage(mongodb.db))
    try:
        data = storage.load()
        #註冊open AI model
        model = OpenAIModel(api_key=os.getenv('OPENAI_API_KEY'))
        is_successful, _, _ = model.check_token_valid()
        if not is_successful:
            print('Invalid API token')
        model_management[0] = model

    except FileNotFoundError:
        pass
    app.run(host='0.0.0.0', port=8080)
