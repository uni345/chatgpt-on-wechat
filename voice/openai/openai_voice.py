"""
google voice service
"""
import json

import openai

from bot.baidu.baidu_wenxin_session import BaiduWenxinSession
from bot.bot_factory import create_bot
from bridge.context import Context, ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from config import conf
from voice.voice import Voice
import requests
from common import const
import datetime, random
import re


class OpenaiVoice(Voice):
    def __init__(self):
        openai.api_key = conf().get("open_ai_api_key")

    def voiceToText(self, voice_file):
        logger.debug("[Openai] voice file name={}".format(voice_file))
        try:
            file = open(voice_file, "rb")
            result = openai.Audio.transcribe("whisper-1", file)
            text = result["text"]
            reply = Reply(ReplyType.TEXT, text)
            logger.info("[Openai] voiceToText text={} voice file name={}".format(text, voice_file))
        except Exception as e:
            reply = Reply(ReplyType.ERROR, "我暂时还无法听清您的语音，请稍后再试吧~")
        finally:
            return reply

    def textToVoice(self, text):
        try:
            url = 'https://api.openai.com/v1/audio/speech'
            headers = {
                'Authorization': 'Bearer ' + conf().get("open_ai_api_key"),
                'Content-Type': 'application/json'
            }
            data = {
                'model': conf().get("text_to_voice_model") or const.TTS_1,
                'input': text,
                'voice': conf().get("tts_voice_id") or "alloy"
            }
            proxy = conf().get("proxy")
            proxies = {
                'http': proxy,
                'https': proxy,
            } if proxy else {}

            response = requests.post(url, headers=headers, json=data, proxies=proxies)
            gen_file_name = self.generate_file_name(text)
            pre_title = re.split(r'([.。,，;；!！?？\n])', gen_file_name)[0]
            file_name = "tmp/" + re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", "", pre_title).replace(" ","-")[:16] + ".mp3"
            logger.debug(f"[OPENAI] text_to_Voice file_name={file_name}, input={text}")
            with open(file_name, 'wb') as f:
                f.write(response.content)
            logger.info(f"[OPENAI] text_to_Voice success")
            reply = Reply(ReplyType.VOICE, file_name)
        except Exception as e:
            logger.error(e)
            reply = Reply(ReplyType.TEXT, "哦,遇到了一点小问题，请换个内容或者再试一次吧")
        return reply

    def generate_file_name(self, text):
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {conf().get("open_ai_api_key")}'  # 使用你的OpenAI API密钥
            }
            data = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "将下面内容生成标题,16字以内"},
                    {"role": "user", "content": text}
                ]
            }
            proxy = conf().get("proxy")
            proxies = {
                'http': proxy,
                'https': proxy,
            } if proxy else {}
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers,
                                     data=json.dumps(data), proxies=proxies)
            response.raise_for_status()

            # 处理响应数据
            response_data = response.json()
            # 这里可以根据你的需要处理响应数据
            # 解析 JSON 并获取 content
            if "choices" in response_data and len(response_data["choices"]) > 0:
                first_choice = response_data["choices"][0]
                if "message" in first_choice and "content" in first_choice["message"]:
                    content = first_choice["message"]["content"]
                    return content
                else:
                    print("Content not found in the response")
            else:
                print("No choices available in the response")
        except requests.exceptions.RequestException as e:
            # 处理可能出现的错误
            logger.error(f"Error calling OpenAI API: {e}")

        return text[:16]
